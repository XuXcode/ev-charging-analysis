"""Append-only adaptive polygon collection. Historical pages and canonical POIs stay intact."""

import argparse
import copy
import json
import logging
import uuid
from collections import Counter
from pathlib import Path

from shapely.geometry import box, shape
from sqlalchemy import func, select, text

from app.core.config import Settings
from app.db.session import create_db_engine, create_session_factory
from app.models import (
    AnalysisBoundary,
    AnalysisScopeQuality,
    ChargingStation,
    CollectionPage,
    CollectionRun,
    PoiQuality,
)
from app.models.entities import utc_now
from app.services.collector.client import AMapClient, CollectionError
from app.services.collector.runner import fail_run, persist_page
from app.services.governance import classify_poi, latest_province_run

logger = logging.getLogger("collector")


def split_bounds(bounds):
    west, south, east, north = bounds
    x, y = (west + east) / 2, (south + north) / 2
    return [(west, south, x, y), (x, south, east, y), (west, y, x, north), (x, y, east, north)]


def counts(session):
    return dict(
        session.execute(
            select(ChargingStation.adcode, func.count())
            .where(ChargingStation.source == "amap")
            .group_by(ChargingStation.adcode)
        ).all()
    )


def create_supplement(session):
    parent = latest_province_run(session)
    scopes = list(
        session.scalars(
            select(AnalysisScopeQuality)
            .where(AnalysisScopeQuality.completeness_warning.is_(True))
            .order_by(AnalysisScopeQuality.adcode)
        )
    )
    before = counts(session)
    targets, shards = [], []
    for row in scopes:
        boundary = session.get(AnalysisBoundary, row.adcode)
        if not boundary or boundary.coordinate_system != "GCJ-02":
            raise CollectionError("补采缺少已验证GCJ-02区县边界")
        targets.append(
            {
                "adcode": row.adcode,
                "name": row.name,
                "cityCode": row.city_code,
                "cityName": next(
                    city["name"]
                    for city in parent.manifest["cities"]
                    if city["code"] == row.city_code
                ),
                "beforeCount": before.get(row.adcode, 0),
                "boundaryHash": boundary.content_hash,
            }
        )
        shards.append(
            {
                "index": len(shards),
                "adcode": row.adcode,
                "bounds": list(shape(boundary.geometry).bounds),
                "depth": 0,
                "status": "pending",
            }
        )
    if not targets:
        raise CollectionError("没有触及上限的区县")
    run = CollectionRun(
        id=uuid.uuid4().hex,
        status="pending",
        manifest={
            "version": 2,
            "strategy": "adaptive_polygon_v1",
            "parentRunId": parent.id,
            "interval": 1.0,
            "retries": 2,
            "maxDepth": 5,
            "minSpanDegrees": 0.002,
            "keyword": "充电站",
            "types": "011100",
            "pageSize": 25,
            "maxPages": 8,
            "coordinateSystem": "GCJ-02",
            "targets": targets,
            "shards": shards,
            "notice": "分片扩大可检索样本，不能证明官方设施全量；原始记录与历史批次保留。",
        },
    )
    session.add(run)
    session.flush()
    return run.id


def supplement_report(session, run):
    pages = list(session.scalars(select(CollectionPage).where(CollectionPage.run_id == run.id)))
    outcomes = Counter(outcome["status"] for page in pages for outcome in page.outcomes)
    inserted = Counter(
        page.adcode
        for page in pages
        for outcome in page.outcomes
        if outcome["status"] == "inserted"
    )
    # Completed reports are reconstructed from committed batch evidence, never from
    # the mutable current database counts (which may include later collections).
    current = (
        {
            target["adcode"]: target["beforeCount"] + inserted[target["adcode"]]
            for target in run.manifest["targets"]
        }
        if run.status in {"completed", "completed_with_limits"}
        else counts(session)
    )
    shards = run.manifest["shards"]
    targets = []
    for target in run.manifest["targets"]:
        leaf = [s for s in shards if s["adcode"] == target["adcode"] and s["status"] != "split"]
        pending = sum(s["status"] == "pending" for s in leaf)
        capped = sum(s["status"] == "capped" for s in leaf)
        targets.append(
            {
                **target,
                "afterCount": current.get(target["adcode"], 0),
                "addedCount": current.get(target["adcode"], 0) - target["beforeCount"],
                "pendingShards": pending,
                "cappedLeafShards": capped,
                "completenessStatus": "补采未完成"
                if pending
                else "分片仍触及上限"
                if capped
                else "计划分片已耗尽；不证明全量",
            }
        )
    return {
        "id": run.id,
        "status": run.status,
        "parentRunId": run.manifest["parentRunId"],
        "strategy": run.manifest["strategy"],
        "startedAt": run.started_at.isoformat() + "Z",
        "updatedAt": run.updated_at.isoformat() + "Z",
        "lastError": run.last_error,
        "districts": targets,
        "shardCount": len(shards),
        "quality": {
            "pageCount": len(pages),
            "rawCount": sum(len(page.raw_pois) for page in pages),
            "insertedCount": outcomes["inserted"],
            "retainedDuplicateCount": outcomes["retained"],
            "rejectedCount": outcomes["rejected"],
            "rejectionReasons": dict(
                Counter(
                    outcome["reason"]
                    for page in pages
                    for outcome in page.outcomes
                    if outcome["status"] == "rejected"
                )
            ),
            "countBasis": "按该批次已提交页面的inserted记录还原，不随后续批次变化",
            "queryDifference": "原批次为行政区关键词搜索；补采为矩形关键词+011100分类搜索，范围和检索条件均有变化",
        },
        "manifest": run.manifest,
        "notice": run.manifest["notice"],
    }


def execute_supplement(factory, run_id, client):
    with factory.begin() as session:
        run = session.get(CollectionRun, run_id)
        if not run or run.manifest.get("version") != 2:
            raise CollectionError("不是可续跑补采批次")
        if run.status in {"completed", "completed_with_limits"}:
            return
        manifest = copy.deepcopy(run.manifest)
        run.status, run.last_error = "running", None
    targets = {row["adcode"]: row for row in manifest["targets"]}
    try:
        index = 0
        while index < len(manifest["shards"]):
            shard = manifest["shards"][index]
            index += 1
            if shard["status"] != "pending":
                continue
            target = targets[shard["adcode"]]
            with factory() as session:
                boundary = session.get(AnalysisBoundary, target["adcode"])
                if boundary.content_hash != target["boundaryHash"]:
                    raise CollectionError("补采边界已变化，不能沿用旧计划")
                geometry = shape(boundary.geometry)
                if not geometry.intersects(box(*shard["bounds"])):
                    shard["status"] = "outside"
            capped = False
            if shard["status"] == "pending":
                for page in range(1, 9):
                    slot = shard["index"] * 8 + page
                    with factory() as session:
                        saved = session.scalar(
                            select(CollectionPage).where(
                                CollectionPage.run_id == run_id,
                                CollectionPage.adcode == target["adcode"],
                                CollectionPage.page == slot,
                            )
                        )
                        terminal = saved.terminal if saved else False
                        capped = saved.capped if saved else False
                    if saved:
                        if terminal:
                            break
                        continue
                    pois, attempts = client.polygon_pois(shard["bounds"], page)
                    terminal = len(pois) < 25 or page == 8
                    capped = page == 8 and len(pois) == 25
                    with factory.begin() as session:
                        record = persist_page(
                            session,
                            run_id,
                            target,
                            target["cityName"],
                            slot,
                            pois,
                            attempts,
                            preserve_existing=True,
                            terminal_override=terminal,
                            capped_override=capped,
                        )
                        # Existing governance is never overwritten; only new stations need evidence.
                        for outcome in record.outcomes:
                            if outcome["status"] != "inserted":
                                continue
                            station = session.get(ChargingStation, outcome["stationId"])
                            raw = pois[outcome["index"]]
                            decision = classify_poi(station.name, raw)
                            session.add(
                                PoiQuality(
                                    station_id=station.id,
                                    **decision,
                                    review_status="unreviewed",
                                    run_id=run_id,
                                )
                            )
                    logger.info(
                        "supplement run=%s district=%s shard=%d page=%d raw=%d capped=%s",
                        run_id,
                        target["adcode"],
                        shard["index"],
                        page,
                        len(pois),
                        capped,
                    )
                    if terminal:
                        break
                west, south, east, north = shard["bounds"]
                subdivide = (
                    capped
                    and shard["depth"] < manifest["maxDepth"]
                    and min(east - west, north - south) > manifest["minSpanDegrees"]
                )
                if subdivide:
                    shard["status"] = "split"
                    for bounds in split_bounds(shard["bounds"]):
                        manifest["shards"].append(
                            {
                                "index": len(manifest["shards"]),
                                "adcode": shard["adcode"],
                                "bounds": list(bounds),
                                "depth": shard["depth"] + 1,
                                "status": "pending",
                            }
                        )
                else:
                    shard["status"] = "capped" if capped else "exhausted"
            with factory.begin() as session:
                run = session.get(CollectionRun, run_id)
                run.manifest = copy.deepcopy(manifest)
                run.updated_at = utc_now()
        with factory.begin() as session:
            run = session.get(CollectionRun, run_id)
            manifest["afterCounts"] = counts(session)
            run.manifest = copy.deepcopy(manifest)
            run.status = (
                "completed_with_limits"
                if any(s["status"] == "capped" for s in manifest["shards"])
                else "completed"
            )
            run.finished_at = run.updated_at = utc_now()
    except CollectionError as failure:
        fail_run(factory, run_id, str(failure))
        raise
    except KeyboardInterrupt:
        fail_run(factory, run_id, "已提交补采页面保留，可续跑", status="interrupted")
        raise
    except Exception:
        fail_run(factory, run_id, "补采本地运行失败；已提交记录保留")
        raise


def main():
    parser = argparse.ArgumentParser(description="17区县自适应网格补采，保留历史")
    parser.add_argument("--resume")
    parser.add_argument("--report", help="只读导出已有补采批次的当前报告")
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
                run = session.get(CollectionRun, args.report)
                if not run or run.manifest.get("version") != 2:
                    raise CollectionError("未找到补采批次")
                report = supplement_report(session, run)
            destination = Path(__file__).resolve().parents[4] / "docs/SUPPLEMENT_REPORT.json"
            destination.write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(
                json.dumps(
                    {
                        "id": run.id,
                        "status": run.status,
                        "shardCount": report["shardCount"],
                        "districtCount": len(report["districts"]),
                        "addedCount": sum(row["addedCount"] for row in report["districts"]),
                    },
                    ensure_ascii=True,
                )
            )
            return
        with engine.connect() as lock:
            if lock.scalar(text("SELECT GET_LOCK('ev_amap_collector',0)")) != 1:
                raise CollectionError("已有采集任务运行")
            try:
                with factory.begin() as session:
                    run_id = args.resume or create_supplement(session)
                print(json.dumps({"supplementRunId": run_id}), flush=True)
                client = AMapClient(settings, interval=1.0, retries=2)
                execute_supplement(factory, run_id, client)
                with factory() as session:
                    report = supplement_report(session, session.get(CollectionRun, run_id))
                print(json.dumps(report, ensure_ascii=True), flush=True)
            finally:
                lock.execute(text("SELECT RELEASE_LOCK('ev_amap_collector')"))
    finally:
        if client:
            client.close()
        engine.dispose()


if __name__ == "__main__":
    main()
