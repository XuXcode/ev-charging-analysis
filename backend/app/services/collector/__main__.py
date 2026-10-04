"""python -m app.services.collector {verify,collect,report} (from backend)."""

import argparse
import json
import logging
import sys
from math import isfinite
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import BACKEND_ROOT, get_settings
from app.core.logging import configure_logging
from app.db.session import create_db_engine, create_session_factory
from app.models import CollectionRun
from app.services.collector.client import AMapClient, CollectionError
from app.services.collector.runner import create_run, execute, fail_run, report_run


def save_report(run_id, data):
    directory = BACKEND_ROOT / ".runtime" / "collector"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{run_id}.json"
    temporary = Path(str(destination) + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(destination)


def main():
    # Keep Chinese diagnostics readable in Windows terminals and redirected UTF-8 logs.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="湖南14市州充电站POI采集；没有全量统计含义")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("verify", help="验证Web服务Key及地点、行政区权限；不入库")
    collect = commands.add_parser("collect", help="创建批次或续跑；默认全部14市州")
    collect.add_argument("--city", action="append", help="可重复指定湖南市州六位编码")
    collect.add_argument("--resume", help="原批次ID；沿用原批次参数")
    collect.add_argument("--interval", type=float, default=1.0)
    collect.add_argument("--retries", type=int, default=3)
    report = commands.add_parser("report", help="导出质量报告，不发起高德请求")
    report.add_argument("run_id")
    args = parser.parse_args()
    settings = get_settings()
    configure_logging(settings.log_level)
    if args.command == "verify":
        try:
            client = AMapClient(settings)
            try:
                client.districts("430100")
                pois, _ = client.pois("430102", 1)
                print(
                    json.dumps(
                        {
                            "webServiceVerified": True,
                            "sampleReturnedCount": len(pois),
                            "jsApiVerified": False,
                            "note": "JS API须在浏览器验证；本命令不保存站点",
                        },
                        ensure_ascii=False,
                    )
                )
            finally:
                client.close()
            return 0
        except CollectionError as exc:
            print(
                json.dumps(
                    {"webServiceVerified": False, "jsApiVerified": False, "error": str(exc)},
                    ensure_ascii=False,
                )
            )
            return 2
    if args.command == "collect" and (
        not isfinite(args.interval)
        or args.interval < 0.2
        or not 0 <= args.retries <= 5
        or args.resume
        and args.city
    ):
        parser.error("间隔至少0.2秒、重试0–5次；续跑不可更改市州范围")
    engine = create_db_engine(settings)
    factory = create_session_factory(engine)
    run_id, client, log_handler = None, None, None
    logger = logging.getLogger("collector")
    try:
        with engine.connect() as lock:
            acquired = False
            try:
                if args.command == "collect":
                    acquired = lock.scalar(text("SELECT GET_LOCK('ev_amap_collector', 0)")) == 1
                    if not acquired:
                        raise CollectionError("已有采集进程运行，请等待其结束")
                    if args.resume:
                        run_id = args.resume
                    else:
                        with factory.begin() as session:
                            run_id = create_run(
                                session,
                                city_codes=args.city,
                                interval=args.interval,
                                retries=args.retries,
                            )
                    with factory() as session:
                        run = session.get(CollectionRun, run_id)
                        if run is None:
                            raise CollectionError("未找到续跑批次")
                        manifest, status = run.manifest, run.status
                    print(f"采集批次：{run_id}", flush=True)
                    log_directory = BACKEND_ROOT / ".runtime" / "collector"
                    log_directory.mkdir(parents=True, exist_ok=True)
                    log_handler = logging.FileHandler(
                        log_directory / f"{run_id}.log", encoding="utf-8"
                    )
                    log_handler.setFormatter(
                        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
                    )
                    logger.addHandler(log_handler)
                    logger.info(
                        "run=%s command=collect resume=%s status=%s",
                        run_id,
                        bool(args.resume),
                        status,
                    )
                    if status not in {"completed", "completed_with_limits"}:
                        try:
                            client = AMapClient(
                                settings, interval=manifest["interval"], retries=manifest["retries"]
                            )
                        except CollectionError as exc:
                            fail_run(factory, run_id, str(exc), status="blocked")
                            raise
                        execute(factory, run_id, client)
                else:
                    run_id = args.run_id
                with factory() as session:
                    run = session.get(CollectionRun, run_id)
                    if run is None:
                        raise CollectionError("未找到采集批次")
                    report_data = report_run(session, run)
                save_report(run_id, report_data)
                print(json.dumps(report_data, ensure_ascii=False, indent=2))
                return 0
            finally:
                if acquired:
                    lock.execute(text("SELECT RELEASE_LOCK('ev_amap_collector')"))
    except (CollectionError, SQLAlchemyError, KeyboardInterrupt) as exc:
        message = (
            str(exc)
            if isinstance(exc, CollectionError)
            else "数据库连接/迁移失败"
            if isinstance(exc, SQLAlchemyError)
            else "采集已中断"
        )
        print(json.dumps({"runId": run_id, "error": message}, ensure_ascii=False), flush=True)
        logger.error("run=%s error=%s", run_id, message)
        if run_id:
            try:
                with factory() as session:
                    run = session.get(CollectionRun, run_id)
                    if run:
                        save_report(run_id, report_run(session, run))
            except SQLAlchemyError:
                pass
        return 2
    finally:
        if log_handler:
            logger.removeHandler(log_handler)
            log_handler.close()
        if client:
            client.close()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
