"""Demand-side POI collection for planning-reference scoring.

Collects five demand categories (shopping / hospital / office / parking /
residential) per Hunan district as bounded retrieval evidence. The keyword
searches have the same 8-page cap as the station collector, so results are a
retrievable sample, never a census. A single facility can legitimately appear
under several categories (e.g. a hospital parking lot), so rows are keyed by
(poi_id, demand_type), not by poi_id alone.

Nothing here is a construction recommendation: it only feeds the descriptive
planning-reference score shown on the frontend.
"""

import argparse
import json
import logging
import sys
import uuid
from decimal import Decimal, InvalidOperation
from math import isfinite

from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.db.session import create_db_engine, create_session_factory
from app.models import AnalysisScopeQuality, DataSource, DemandPoi, DemandRun, Region
from app.models.demand import utc_now
from app.services.collector.client import AMapClient, CollectionError

logger = logging.getLogger("collector")

NOTICE = (
    "需求POI样本：按5类需求关键词逐区县检索，每区县每类最多200条；"
    "POI样本不代表官方总量，也不作为建设决策依据。坐标为GCJ-02。"
)

DEMAND_TYPES = [
    {"key": "shopping", "label": "购物中心", "keywords": "购物中心"},
    {"key": "hospital", "label": "医院", "keywords": "医院"},
    {"key": "office", "label": "写字楼", "keywords": "写字楼"},
    {"key": "parking", "label": "停车场", "keywords": "停车场"},
    {"key": "residential", "label": "住宅小区", "keywords": "住宅小区"},
]


class DemandPoiCreate(BaseModel):
    poi_id: str
    name: str
    demand_type: str
    city: str
    adcode: str
    longitude: float
    latitude: float
    collected_at: object
    data_source_id: int


def create_demand_run(session, *, interval=1.0, retries=3, district_codes=None):
    scopes = list(
        session.scalars(
            select(AnalysisScopeQuality).order_by(AnalysisScopeQuality.adcode)
        )
    )
    if len(scopes) != 122:
        raise CollectionError("需要122个真实区县元信息；请先执行区县治理任务")
    city_map = {
        code: name
        for code, name in session.execute(
            select(Region.adcode, Region.name).where(
                Region.level == "city",
                Region.parent_adcode == "430000",
                Region.is_demo.is_(False),
            )
        )
    }
    if len(city_map) != 14:
        raise CollectionError("需要14个真实市州元信息")
    selected = set(district_codes or [s.adcode for s in scopes])
    if not selected or selected - {s.adcode for s in scopes}:
        raise CollectionError("需求采集范围必须为湖南省区县编码")
    selected_scopes = [s for s in scopes if s.adcode in selected]
    run = DemandRun(
        id=uuid.uuid4().hex,
        status="pending",
        manifest={
            "version": 1,
            "demandTypes": [dict(item) for item in DEMAND_TYPES],
            "pageSize": 25,
            "maxPages": 8,
            "coordinateSystem": "GCJ-02",
            "interval": interval,
            "retries": retries,
            "districts": [
                {
                    "adcode": s.adcode,
                    "name": s.name,
                    "cityCode": s.city_code,
                    "cityName": city_map.get(s.city_code, ""),
                }
                for s in selected_scopes
            ],
            "progress": {},
            "notice": NOTICE,
        },
    )
    session.add(run)
    session.flush()
    return run.id


def source_record(session):
    name = "高德需求POI（行政区关键词检索）"
    row = session.scalar(select(DataSource).where(DataSource.name == name))
    if row is None:
        row = DataSource(
            name=name,
            source_type="amap_poi",
            source_url="https://restapi.amap.com/v5/place/text",
            description=NOTICE,
            is_demo=False,
        )
        session.add(row)
        session.flush()
    if row.is_demo or row.source_type != "amap_poi":
        raise CollectionError("需求采集来源元数据与真实POI来源冲突")
    return row


def clean_demand_poi(poi, district, demand_type, source_id, collected_at):
    if not isinstance(poi, dict):
        return None, "invalid_record"
    name, poi_id = poi.get("name"), poi.get("id")
    if (
        not isinstance(name, str)
        or not name.strip()
        or not isinstance(poi_id, str)
        or not poi_id.strip()
    ):
        return None, "missing_identity"
    adcode = str(poi.get("adcode", ""))
    if adcode != district["adcode"] or adcode[:4] != district["cityCode"][:4]:
        return None, "outside_requested_district"
    try:
        parts = poi["location"].split(",")
        if len(parts) != 2:
            raise ValueError
        lng, lat = (Decimal(value) for value in parts)
        if not lng.is_finite() or not lat.is_finite() or lng == 0 or lat == 0:
            raise ValueError
        if not (Decimal("108") < lng < Decimal("115") and Decimal("24") < lat < Decimal("31")):
            return None, "implausible_hunan_coordinates"
        payload = DemandPoiCreate(
            poi_id=poi_id.strip(),
            name=name.strip(),
            demand_type=demand_type,
            city=district["cityName"],
            adcode=adcode,
            longitude=float(lng),
            latitude=float(lat),
            collected_at=collected_at,
            data_source_id=source_id,
        )
    except (KeyError, AttributeError, TypeError, ValueError, InvalidOperation):
        return None, "invalid_fields_or_coordinates"
    return payload, None


def persist_demand_page(session, run_id, district, demand_type, page, pois, attempts):
    now = utc_now()
    source = source_record(session)
    outcomes = []
    for index, poi in enumerate(pois):
        payload, reason = clean_demand_poi(poi, district, demand_type, source.id, now)
        if reason:
            outcomes.append({"index": index, "status": "rejected", "reason": reason})
            continue
        existing = session.scalar(
            select(DemandPoi).where(
                DemandPoi.poi_id == payload.poi_id,
                DemandPoi.demand_type == payload.demand_type,
            )
        )
        if existing:
            outcomes.append({"index": index, "status": "retained", "poiId": payload.poi_id})
            continue
        row = DemandPoi(**payload.model_dump())
        session.add(row)
        session.flush()
        outcomes.append({"index": index, "status": "inserted", "poiId": payload.poi_id})
    session.flush()
    return outcomes


def fail_demand_run(factory, run_id, message, *, status="failed"):
    with factory.begin() as session:
        run = session.get(DemandRun, run_id)
        if run:
            run.status, run.last_error = status, message[:500]


def execute_demand_collection(factory, run_id, client):
    with factory.begin() as session:
        run = session.get(DemandRun, run_id)
        if run is None:
            raise CollectionError("未找到需求采集批次")
        if run.manifest.get("version") != 1:
            raise CollectionError("不支持该断点版本")
        if run.status in {"completed", "completed_with_limits"}:
            return
        manifest = run.manifest
        run.status, run.last_error, run.finished_at = "running", None, None
    current_request = "需求采集准备"
    try:
        progress = manifest.get("progress", {})
        for district in manifest["districts"]:
            for demand in manifest["demandTypes"]:
                type_key = demand["key"]
                done = set(progress.get(f"{district['adcode']}:{type_key}", []))
                for page in range(1, manifest["maxPages"] + 1):
                    if page in done:
                        continue
                    current_request = (
                        f"district={district['adcode']} type={type_key} page={page}"
                    )
                    pois, attempts = client.demand_pois(
                        district["adcode"], demand["keywords"], page
                    )
                    with factory.begin() as session:
                        outcomes = persist_demand_page(
                            session,
                            run_id,
                            district,
                            type_key,
                            page,
                            pois,
                            attempts,
                        )
                    progress.setdefault(f"{district['adcode']}:{type_key}", []).append(page)
                    with factory.begin() as session:
                        run = session.get(DemandRun, run_id)
                        run.manifest = {**manifest, "progress": progress}
                    logger.info(
                        "demand run=%s district=%s type=%s page=%d raw=%d",
                        run_id,
                        district["adcode"],
                        type_key,
                        page,
                        len(pois),
                    )
                    if len(pois) < 25:
                        break
        with factory.begin() as session:
            run = session.get(DemandRun, run_id)
            run.manifest = {**manifest, "progress": progress}
            run.status = "completed"
            run.finished_at = utc_now()
    except CollectionError as exc:
        fail_demand_run(factory, run_id, f"{current_request}: {exc}")
        logger.error("run=%s %s error=%s", run_id, current_request, str(exc))
        raise
    except KeyboardInterrupt:
        fail_demand_run(factory, run_id, "用户中断；已提交记录保留，可断点续跑", status="interrupted")
        raise
    except Exception:
        fail_demand_run(factory, run_id, "需求采集本地失败；已提交记录保留")
        raise CollectionError("需求采集本地失败，请检查数据库") from None


def demand_report(session, run):
    type_counts = dict(
        session.execute(
            select(DemandPoi.demand_type, func.count()).group_by(DemandPoi.demand_type)
        ).all()
    )
    district_counts = dict(
        session.execute(
            select(DemandPoi.adcode, func.count()).group_by(DemandPoi.adcode)
        ).all()
    )
    return {
        "id": run.id,
        "status": run.status,
        "startedAt": run.started_at.isoformat() + "Z",
        "finishedAt": run.finished_at.isoformat() + "Z" if run.finished_at else None,
        "lastError": run.last_error,
        "typeCounts": type_counts,
        "districtCount": len(district_counts),
        "totalCount": sum(type_counts.values()),
        "notice": NOTICE,
    }


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="湖南需求POI采集；仅规划参考")
    parser.add_argument("--resume", help="原批次ID续跑")
    parser.add_argument("--district", action="append", help="可重复指定区县六位编码")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--report", help="只读导出指定批次报告")
    args = parser.parse_args()
    settings = Settings()
    engine = create_db_engine(settings)
    factory = create_session_factory(engine)
    client = None
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    try:
        if args.report:
            with factory() as session:
                run = session.get(DemandRun, args.report)
                if run is None:
                    raise CollectionError("未找到需求采集批次")
                print(json.dumps(demand_report(session, run), ensure_ascii=False, indent=2))
            return 0
        with engine.connect() as lock:
            if lock.scalar(text("SELECT GET_LOCK('ev_amap_collector',0)")) != 1:
                raise CollectionError("已有采集任务运行")
            try:
                with factory.begin() as session:
                    run_id = args.resume or create_demand_run(
                        session,
                        interval=args.interval,
                        retries=args.retries,
                        district_codes=args.district,
                    )
                print(json.dumps({"demandRunId": run_id}), flush=True)
                client = AMapClient(settings, interval=args.interval, retries=args.retries)
                execute_demand_collection(factory, run_id, client)
                with factory() as session:
                    report = demand_report(session, session.get(DemandRun, run_id))
                print(json.dumps(report, ensure_ascii=True), flush=True)
                return 0
            finally:
                lock.execute(text("SELECT RELEASE_LOCK('ev_amap_collector')"))
    except (CollectionError, SQLAlchemyError, KeyboardInterrupt) as exc:
        message = (
            str(exc)
            if isinstance(exc, CollectionError)
            else "数据库连接/迁移失败"
            if isinstance(exc, SQLAlchemyError)
            else "采集已中断"
        )
        print(json.dumps({"error": message}, ensure_ascii=False), flush=True)
        return 2
    finally:
        if client:
            client.close()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())