"""Install a verified complete county boundary version, preserving every predecessor."""

import argparse
import json
from datetime import datetime
from pathlib import Path

from shapely import STRtree
from shapely.geometry import Point
from sqlalchemy import select

from app.core.config import Settings
from app.db.session import create_db_engine, create_session_factory
from app.models import AnalysisBoundary, BoundaryRevision, ChargingStation, RoadAccessibilityRun
from app.models.entities import utc_now
from app.services.analysis.geometry import prepare_boundary, to_metric
from app.services.analysis.job import digest
from app.services.poi_review import append_event


def assignment(rows, boundaries):
    codes = list(boundaries)
    tree = STRtree(list(boundaries.values()))
    records = []
    mismatch = outside = ambiguous = 0
    for row in rows:
        point = to_metric(Point(float(row.longitude), float(row.latitude)))
        hits = [codes[int(i)] for i in tree.query(point, predicate="intersects")]
        mismatch += row.adcode not in hits
        outside += not hits
        ambiguous += len(hits) > 1
        if row.adcode not in hits or len(hits) != 1:
            records.append(
                {
                    "stationId": row.id,
                    "poiId": row.poi_id,
                    "sourceAdcode": row.adcode,
                    "geometryAdcodes": hits,
                }
            )
    return {"mismatch": mismatch, "outside": outside, "ambiguous": ambiguous, "records": records}


def preserve_revision(session, row, reason):
    identity = digest({"adcode": row.adcode, "hash": row.content_hash, "source": row.source_url})
    if session.get(BoundaryRevision, identity) is None:
        session.add(
            BoundaryRevision(
                id=identity,
                adcode=row.adcode,
                content_hash=row.content_hash,
                geometry=row.geometry,
                source_url=row.source_url,
                coordinate_system=row.coordinate_system,
                fetched_at=row.fetched_at,
                reason=reason,
            )
        )


def install(session, report, *, apply=False):
    current = list(
        session.scalars(
            select(AnalysisBoundary)
            .where(AnalysisBoundary.level == "district")
            .order_by(AnalysisBoundary.adcode)
        )
    )
    records = report["records"]
    if len(current) != 122 or set(records) != {r.adcode for r in current}:
        raise ValueError("必须提供与当前122区县完全对应的统一边界版本")
    if report["endpoint"] != "https://restapi.amap.com/v3/config/district":
        raise ValueError("来源不是本轮核验的高德行政区接口")
    for record in records.values():
        if (
            record.get("coordinateSystem") != "GCJ-02"
            or record.get("sourceUrl") != report["endpoint"]
        ):
            raise ValueError("区县边界坐标系或来源不一致")
    old_geometry = {r.adcode: prepare_boundary(r.geometry)[0] for r in current}
    new_geometry = {code: prepare_boundary(r["geometry"])[0] for code, r in records.items()}
    rows = session.execute(
        select(
            ChargingStation.id,
            ChargingStation.poi_id,
            ChargingStation.adcode,
            ChargingStation.longitude,
            ChargingStation.latitude,
        )
        .where(ChargingStation.source == "amap")
        .order_by(ChargingStation.id)
    ).all()
    before, after = assignment(rows, old_geometry), assignment(rows, new_geometry)
    if after["mismatch"] or after["outside"] or after["ambiguous"]:
        raise ValueError("新边界仍有站点归属异常，停止覆盖，先复核证据")
    old_road_id = session.scalar(
        select(RoadAccessibilityRun.id)
        .where(RoadAccessibilityRun.status == "completed")
        .order_by(RoadAccessibilityRun.updated_at.desc())
        .limit(1)
    )
    old_road = (
        session.scalar(
            select(RoadAccessibilityRun.inputs).where(RoadAccessibilityRun.id == old_road_id)
        )
        if old_road_id
        else None
    )
    origins_outside = []
    if old_road:
        origins_outside = [
            r["adcode"]
            for r in old_road["origins"]
            if not new_geometry[r["adcode"]].covers(to_metric(Point(r["position"])))
        ]
    changes = []
    for row in current:
        record = records[row.adcode]
        new_hash = digest(
            {
                "geometry": record["geometry"],
                "sourceUrl": report["endpoint"],
                "coordinateSystem": "GCJ-02",
            }
        )
        if row.content_hash == new_hash:
            continue
        change = {
            "adcode": row.adcode,
            "name": row.name,
            "beforeHash": row.content_hash,
            "afterHash": new_hash,
            "beforeSource": row.source_url,
            "afterSource": report["endpoint"],
            "reason": "以统一高德行政区多边形替换DataV展示图形；逆地理编码与原始POI一致，不修改站点编码或坐标。",
        }
        changes.append(change)
        if apply:
            preserve_revision(session, row, "修正前原始展示边界，完整保留用于历史重放")
            row.geometry = record["geometry"]
            row.content_hash = new_hash
            row.source_url = report["endpoint"]
            row.fetched_at = datetime.fromisoformat(record["observedAt"]).replace(tzinfo=None)
            preserve_revision(session, row, change["reason"])
    if apply:
        by_id = {r.id: r for r in rows}
        for issue in before["records"]:
            station = by_id[issue["stationId"]]
            append_event(
                session,
                station.id,
                "boundary_version_reconciled",
                issue,
                {
                    "sourceAdcode": station.adcode,
                    "geometryAdcodes": [station.adcode],
                    "stationModified": False,
                },
                {
                    "sourceUrl": report["endpoint"],
                    "boundaryHash": next(
                        r.content_hash for r in current if r.adcode == station.adcode
                    ),
                },
                "高德逆地理与原始POI编码一致；更新行政边界版本后几何归属一致。原始站点不改址。",
            )
        session.flush()
    return {
        "createdAt": utc_now().isoformat() + "Z",
        "applied": apply,
        "sampleCount": len(rows),
        "before": before,
        "after": after,
        "boundaryChanges": changes,
        "existingRoadOriginsOutsideNewBoundary": origins_outside,
        "notice": "商业地图行政区数据交叉核验，非法律确界或实地测量；历史边界、原始POI及冻结快照保留。",
    }


def main():
    parser = argparse.ArgumentParser(description="安装核验后的122区县边界，原始POI保持不变")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    report = json.loads(
        (root / "backend/.runtime/boundaries/amap-review.json").read_text(encoding="utf-8")
    )
    engine = create_db_engine(Settings())
    try:
        with create_session_factory(engine)() as session, session.begin():
            result = install(session, report, apply=args.apply)
        path = root / (
            "docs/BOUNDARY_REVIEW_APPLIED.json" if args.apply else "docs/BOUNDARY_REVIEW_PLAN.json"
        )
        if path.exists():
            path = path.with_name(f"{path.stem}_{utc_now():%Y%m%d%H%M%S}.json")
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            {
                "applied": args.apply,
                "before": {k: v for k, v in result["before"].items() if k != "records"},
                "after": {k: v for k, v in result["after"].items() if k != "records"},
                "boundariesChanged": len(result["boundaryChanges"]),
                "roadOriginsOutside": len(result["existingRoadOriginsOutsideNewBoundary"]),
                "report": path.name,
            }
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
