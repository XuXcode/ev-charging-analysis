"""Independent sequential collector; page data and checkpoint commit together."""

import hashlib
import json
import logging
import uuid

from sqlalchemy import func, select

from app.models import ChargingStation, CollectionPage, CollectionRun, DataSource, Region
from app.models.entities import utc_now
from app.services.collector.cleaning import clean_poi, identity_hash
from app.services.collector.client import CollectionError

logger = logging.getLogger("collector")
NOTICE = "已采集POI清单，不代表全省设施总量；每区县同一搜索条件最多200条。坐标为GCJ-02。桩数、历史趋势及空间分析暂无数据。"


def create_run(session, *, city_codes=None, interval=1.0, retries=3):
    cities = list(
        session.scalars(
            select(Region)
            .where(
                Region.level == "city",
                Region.parent_adcode == "430000",
                Region.is_demo.is_(False),
            )
            .order_by(Region.adcode)
        )
    )
    if len(cities) != 14:
        raise CollectionError("需要14个真实市州元信息；请先运行 app.db.import_regions")
    selected = set(city_codes or [c.adcode for c in cities])
    if not selected or selected - {c.adcode for c in cities}:
        raise CollectionError("采集范围必须为湖南省市州编码")
    run = CollectionRun(
        id=uuid.uuid4().hex,
        status="pending",
        manifest={
            "version": 1,
            "keyword": "充电站",
            "pageSize": 25,
            "maxPages": 8,
            "coordinateSystem": "GCJ-02",
            "interval": interval,
            "retries": retries,
            "cities": [{"code": c.adcode, "name": c.name} for c in cities if c.adcode in selected],
            "scopes": {},
            "notice": NOTICE,
        },
    )
    session.add(run)
    session.flush()
    return run.id


def source_record(session, *, polygon=False):
    name = "高德充电站 POI（矩形分片补采）" if polygon else "高德充电站 POI（行政区采集）"
    row = session.scalar(select(DataSource).where(DataSource.name == name))
    if row is None:
        row = DataSource(
            name=name,
            source_type="amap_poi",
            source_url="https://restapi.amap.com/v5/place/polygon"
            if polygon
            else "https://restapi.amap.com/v5/place/text",
            description="关键词充电站+011100分类矩形分片补采；仅为可检索样本，不证明全量。"
            if polygon
            else NOTICE,
            is_demo=False,
        )
        session.add(row)
        session.flush()
    if row.is_demo or row.source_type != "amap_poi":
        raise CollectionError("采集来源元数据与真实POI来源冲突")
    return row


def persist_page(
    session,
    run_id,
    scope,
    city_name,
    page,
    pois,
    attempts,
    *,
    preserve_existing=False,
    terminal_override=None,
    capped_override=None,
):
    existing_page = session.scalar(
        select(CollectionPage).where(
            CollectionPage.run_id == run_id,
            CollectionPage.adcode == scope["adcode"],
            CollectionPage.page == page,
        )
    )
    if existing_page:
        return existing_page
    now = utc_now()
    source = source_record(session, polygon=preserve_existing)
    outcomes = []
    for index, poi in enumerate(pois):
        payload, reason = clean_poi(poi, scope, city_name, source.id, now)
        if reason:
            outcomes.append({"index": index, "status": "rejected", "reason": reason})
            continue
        fingerprint = identity_hash(payload.name, payload.longitude, payload.latitude)
        by_id = session.scalar(
            select(ChargingStation).where(ChargingStation.poi_id == payload.poi_id)
        )
        by_identity = session.scalar(
            select(ChargingStation).where(ChargingStation.identity_hash == fingerprint)
        )
        if by_id is not None and by_identity is not None and by_id.id != by_identity.id:
            outcomes.append({"index": index, "status": "rejected", "reason": "identity_conflict"})
            continue
        row = by_id or by_identity
        if row is None:
            # Also compare legacy records which predate the identity_hash migration.
            candidates = session.scalars(
                select(ChargingStation).where(
                    ChargingStation.source == "amap",
                    ChargingStation.adcode == payload.adcode,
                    ChargingStation.identity_hash.is_(None),
                )
            )
            row = next(
                (
                    r
                    for r in candidates
                    if identity_hash(r.name, r.longitude, r.latitude) == fingerprint
                ),
                None,
            )
        if row is not None:
            old_source = session.get(DataSource, row.data_source_id)
            if old_source is None or old_source.is_demo or row.source != "amap":
                outcomes.append({"index": index, "status": "rejected", "reason": "source_conflict"})
                continue
            if row.adcode[:4] != payload.adcode[:4]:
                outcomes.append(
                    {"index": index, "status": "rejected", "reason": "existing_city_conflict"}
                )
                continue
        status = (
            "retained"
            if row is not None and preserve_existing
            else "inserted"
            if row is None
            else "updated"
            if by_id is not None
            else "merged"
        )
        if row is None:
            row = ChargingStation(**payload.model_dump(), identity_hash=fingerprint)
            session.add(row)
        elif not preserve_existing:
            # Different POI IDs with identical name/position retain the canonical ID.
            for key, value in payload.model_dump(exclude={"poi_id"}).items():
                setattr(row, key, value)
            row.identity_hash = fingerprint
        session.flush()
        outcomes.append(
            {"index": index, "status": status, "stationId": row.id, "poiId": payload.poi_id}
        )
    raw_json = json.dumps(pois, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    record = CollectionPage(
        run_id=run_id,
        city_code=scope["cityCode"],
        adcode=scope["adcode"],
        page=page,
        collected_at=now,
        attempts=attempts,
        raw_pois=pois,
        response_hash=hashlib.sha256(raw_json.encode()).hexdigest(),
        outcomes=outcomes,
        terminal=terminal_override
        if terminal_override is not None
        else len(pois) < 25 or page == 8,
        capped=capped_override if capped_override is not None else page == 8 and len(pois) == 25,
    )
    session.add(record)
    source.updated_at = now
    run = session.get(CollectionRun, run_id)
    run.updated_at = now
    session.flush()
    return record


def fail_run(factory, run_id, message, *, status="failed"):
    with factory.begin() as session:
        run = session.get(CollectionRun, run_id)
        if run:
            run.status, run.last_error, run.updated_at = status, message[:500], utc_now()


def execute(factory, run_id, client):
    """CLI owns a MySQL advisory lock. Each transaction is short and resumable."""
    with factory.begin() as session:
        run = session.get(CollectionRun, run_id)
        if run is None:
            raise CollectionError("未找到采集批次")
        if run.manifest.get("version") != 1:
            raise CollectionError("不支持该断点版本")
        if run.status in {"completed", "completed_with_limits"}:
            return
        manifest = run.manifest
        run.status, run.last_error, run.finished_at = "running", None, None
        run.updated_at = utc_now()
    current_request = "行政区发现"
    try:
        for city in manifest["cities"]:
            current_request = f"city={city['code']} 行政区发现"
            if city["code"] not in manifest["scopes"]:
                scopes = client.districts(city["code"])
                manifest = {**manifest, "scopes": {**manifest["scopes"], city["code"]: scopes}}
                with factory.begin() as session:
                    session.get(CollectionRun, run_id).manifest = manifest
            for scope in manifest["scopes"][city["code"]]:
                for page in range(1, 9):
                    with factory() as session:
                        saved = session.scalar(
                            select(CollectionPage).where(
                                CollectionPage.run_id == run_id,
                                CollectionPage.adcode == scope["adcode"],
                                CollectionPage.page == page,
                            )
                        )
                        if saved and saved.terminal:
                            break
                        if saved:
                            continue
                    current_request = f"city={city['code']} district={scope['adcode']} page={page}"
                    pois, attempts = client.pois(scope["adcode"], page)
                    with factory.begin() as session:
                        record = persist_page(
                            session, run_id, scope, city["name"], page, pois, attempts
                        )
                        terminal, capped = record.terminal, record.capped
                    logger.info(
                        "run=%s city=%s district=%s page=%d raw=%d attempts=%d capped=%s",
                        run_id,
                        city["code"],
                        scope["adcode"],
                        page,
                        len(pois),
                        attempts,
                        capped,
                    )
                    if terminal:
                        break
        with factory.begin() as session:
            capped = session.scalar(
                select(func.count())
                .select_from(CollectionPage)
                .where(
                    CollectionPage.run_id == run_id,
                    CollectionPage.capped.is_(True),
                )
            )
            run = session.get(CollectionRun, run_id)
            run.status = "completed_with_limits" if capped else "completed"
            run.finished_at = run.updated_at = utc_now()
    except CollectionError as exc:
        fail_run(factory, run_id, f"{current_request}: {exc}")
        logger.error("run=%s %s error=%s", run_id, current_request, str(exc))
        raise
    except KeyboardInterrupt:
        fail_run(factory, run_id, "用户中断；已提交页面保留，可断点续跑", status="interrupted")
        raise
    except Exception:
        fail_run(factory, run_id, "本地存储或运行失败；当前未提交页面已回滚，可断点续跑")
        raise CollectionError("本地存储或运行失败，请检查数据库和迁移状态") from None


def report_run(session, run):
    if run.manifest.get("version") == 2:
        from app.services.collector.supplement import supplement_report

        return supplement_report(session, run)
    cities = {
        c["code"]: {
            "cityCode": c["code"],
            "name": c["name"],
            "rawCount": 0,
            "uniqueCount": 0,
            "duplicateCount": 0,
            "rejectedCount": 0,
            "insertedCount": 0,
            "updatedCount": 0,
            "mergedCount": 0,
            "committedPages": 0,
            "cappedDistricts": [],
            "rejectionReasons": {},
        }
        for c in run.manifest["cities"]
    }
    seen = {code: set() for code in cities}
    pages = session.scalars(
        select(CollectionPage).where(CollectionPage.run_id == run.id).order_by(CollectionPage.id)
    )
    for page in pages:
        stats = cities[page.city_code]
        stats["rawCount"] += len(page.raw_pois)
        stats["committedPages"] += 1
        if page.capped:
            stats["cappedDistricts"].append(page.adcode)
        for item in page.outcomes:
            status = item["status"]
            if status == "rejected":
                stats["rejectedCount"] += 1
                reasons = stats["rejectionReasons"]
                reasons[item["reason"]] = reasons.get(item["reason"], 0) + 1
            else:
                seen[page.city_code].add(item["stationId"])
                stats[f"{status}Count"] += 1
    for code, stats in cities.items():
        stats["uniqueCount"] = len(seen[code])
        stats["duplicateCount"] = stats["rawCount"] - stats["rejectedCount"] - stats["uniqueCount"]
    totals = {
        key: sum(c[key] for c in cities.values())
        for key in (
            "rawCount",
            "uniqueCount",
            "duplicateCount",
            "rejectedCount",
            "insertedCount",
            "updatedCount",
            "mergedCount",
            "committedPages",
        )
    }
    scopes = [s for group in run.manifest["scopes"].values() for s in group]
    terminal_codes = set(
        session.scalars(
            select(CollectionPage.adcode).where(
                CollectionPage.run_id == run.id,
                CollectionPage.terminal.is_(True),
            )
        )
    )
    return {
        "id": run.id,
        "status": run.status,
        "startedAt": run.started_at.isoformat() + "Z",
        "updatedAt": run.updated_at.isoformat() + "Z",
        "finishedAt": run.finished_at.isoformat() + "Z" if run.finished_at else None,
        "lastError": run.last_error,
        "manifest": run.manifest,
        "totals": totals,
        "cities": list(cities.values()),
        "discoveredDistricts": len(scopes),
        "finishedDistricts": len(terminal_codes),
        "cappedDistricts": [code for city in cities.values() for code in city["cappedDistricts"]],
        "notice": NOTICE,
    }


def collection_summary(session):
    rows = list(
        session.execute(
            select(
                func.substr(ChargingStation.adcode, 1, 4).label("prefix"),
                func.count(),
                func.max(ChargingStation.collected_at),
            )
            .join(DataSource, DataSource.id == ChargingStation.data_source_id)
            .where(
                ChargingStation.source == "amap",
                DataSource.is_demo.is_(False),
                ChargingStation.adcode.startswith("43"),
            )
            .group_by("prefix")
        )
    )
    counts = {prefix + "00": count for prefix, count, _ in rows}
    cities = list(
        session.scalars(
            select(Region)
            .where(
                Region.parent_adcode == "430000",
                Region.level == "city",
                Region.is_demo.is_(False),
            )
            .order_by(Region.adcode)
        )
    )
    latest = session.scalar(
        select(CollectionRun)
        # A resumed older batch may contain the most recent collection activity.
        .order_by(
            CollectionRun.updated_at.desc(),
            CollectionRun.started_at.desc(),
            CollectionRun.id.desc(),
        )
        .limit(1)
    )
    updated = max((stamp for _, _, stamp in rows), default=None)
    supplement = None
    if latest and latest.manifest.get("version") == 2:
        supplement = report_run(session, latest)
        supplement.pop("manifest", None)  # Detailed shard checkpoints belong to the offline report.
        latest = session.get(CollectionRun, latest.manifest["parentRunId"])
    return {
        "source": "高德地图 Web Service API",
        "coordinateSystem": "GCJ-02",
        "simulated": False,
        "storedCount": sum(counts.values()),
        "updatedAt": updated.isoformat() + "Z" if updated else None,
        "cities": [
            {"cityCode": c.adcode, "name": c.name, "storedCount": counts.get(c.adcode, 0)}
            for c in cities
        ],
        "latestRun": report_run(session, latest) if latest else None,
        "latestSupplement": supplement,
        "notice": NOTICE,
    }
