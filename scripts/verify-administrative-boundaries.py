"""Checkpoint real AMap administrative polylines; no database overwrite."""

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from shapely import make_valid, union_all
from shapely.geometry import Point, Polygon, mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from sqlalchemy import select  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.db.session import create_db_engine, create_session_factory  # noqa: E402
from app.models import AnalysisBoundary  # noqa: E402
from app.services.collector.client import DISTRICT_URL, AMapClient, CollectionError  # noqa: E402


def parse_polyline(polyline):
    if not isinstance(polyline, str) or not polyline:
        raise ValueError("缺少行政区多边形")
    rings = []
    for part in polyline.split("|"):
        coordinates = [tuple(map(float, point.split(","))) for point in part.split(";") if point]
        if len(coordinates) < 3 or any(
            len(p) != 2 or not (108 < p[0] < 115 and 24 < p[1] < 31) for p in coordinates
        ):
            raise ValueError("非湖南范围有效行政区坐标")
        rings.append(make_valid(Polygon(coordinates)))
    # AMap supplies disconnected outer rings; retain raw polyline for later hole review.
    geometry = union_all(rings)
    if geometry.is_empty or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError("行政区响应无法形成面")
    return mapping(geometry)


def write(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description="核验高德行政边界，不自动替换分析输入")
    parser.add_argument("--all-counties", action="store_true")
    parser.add_argument("--limit", type=int, default=18)
    args = parser.parse_args()
    if not 1 <= args.limit <= 122:
        parser.error("区县核验额度须在1至122之间")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    baseline = json.loads(
        (ROOT / "docs/reports/ADMIN_REVIEW_BASELINE.json").read_text(encoding="utf-8")
    )["records"]
    codes = sorted({r["sourceAdcode"] for r in baseline})
    settings = Settings()
    if args.all_counties:
        engine = create_db_engine(settings)
        with create_session_factory(engine)() as session:
            codes = list(
                session.scalars(
                    select(AnalysisBoundary.adcode)
                    .where(AnalysisBoundary.level == "district")
                    .order_by(AnalysisBoundary.adcode)
                )
            )
        engine.dispose()
    path = ROOT / "backend/.runtime/boundaries/amap-review.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    report = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.exists()
        else {"endpoint": DISTRICT_URL, "reservedCalls": 0, "records": {}}
    )
    client = AMapClient(settings, interval=1, retries=0)
    try:
        for code in codes:
            if code in report["records"]:
                continue
            if report["reservedCalls"] >= args.limit:
                break
            report["reservedCalls"] += 1
            write(path, report)
            body = client.request(
                DISTRICT_URL, {"keywords": code, "extensions": "all", "subdistrict": 0}
            ).body
            root = next(
                (
                    r
                    for r in body.get("districts", [])
                    if r.get("adcode") == code and r.get("level") == "district"
                ),
                None,
            )
            if root is None:
                raise CollectionError("高德边界行政编码或级别不匹配")
            geometry = parse_polyline(root.get("polyline"))
            report["records"][code] = {
                "name": root["name"],
                "geometry": geometry,
                "polyline": root["polyline"],
                "coordinateSystem": "GCJ-02",
                "observedAt": datetime.now(UTC).isoformat(),
                "sourceUrl": DISTRICT_URL,
            }
            write(path, report)
    finally:
        client.http.close()
    from shapely.geometry import shape

    verified = [r for r in baseline if r["sourceAdcode"] in report["records"]]
    contained = sum(
        shape(report["records"][r["sourceAdcode"]]["geometry"]).covers(Point(r["position"]))
        for r in verified
    )
    print(
        {
            "boundaries": len(report["records"]),
            "reservedCalls": report["reservedCalls"],
            "baselineChecked": len(verified),
            "baselineInsideSourceAMapBoundary": contained,
        }
    )


if __name__ == "__main__":
    main()
