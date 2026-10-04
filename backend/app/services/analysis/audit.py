"""Read-only audit of the real database and running local API; no collection or writes."""

import argparse
import gzip
import json
import math
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

from shapely.geometry import shape
from sqlalchemy import func, select, text

from app.core.config import Settings
from app.db.session import create_db_engine, create_session_factory
from app.models import (
    AnalysisBoundary,
    AnalysisScopeQuality,
    AnalysisSnapshot,
    ChargingStation,
    PoiQuality,
    PublicStatistic,
)
from app.repositories.data import StationRepository


def request_json(path, repetitions=1):
    times = []
    for _ in range(repetitions):
        started = time.perf_counter()
        with urlopen(
            Request("http://127.0.0.1:8000/api/v1" + path, headers={"Accept-Encoding": "gzip"}),
            timeout=30,
        ) as response:
            wire = response.read()
            raw = (
                gzip.decompress(wire)
                if response.headers.get("Content-Encoding") == "gzip"
                else wire
            )
        result = json.loads(raw)["data"]
        times.append((time.perf_counter() - started) * 1000)
    return result, {
        "endpoint": path,
        "requests": repetitions,
        "medianMs": round(statistics.median(times), 2),
        "maxMs": round(max(times), 2),
        "wireBytes": len(wire),
        "jsonBytes": len(raw),
    }


def audit():
    snapshot, timing = request_json("/analysis/latest", 5)
    assert not snapshot["stale"], "分析快照与当前输入不一致"
    assert len(snapshot["cities"]) == 14 and len(snapshot["districts"]) == 122
    count = snapshot["province"]["count"]
    assert sum(r["count"] for r in snapshot["cities"]) == count
    assert sum(r["count"] for r in snapshot["districts"]) == count
    assert math.isclose(sum(r["sharePercent"] for r in snapshot["districts"]), 100)
    for region in [snapshot["province"], *snapshot["cities"], *snapshot["districts"]]:
        assert region["areaKm2"] > 0 and 0 <= region["coveragePercent"] <= 100
        assert math.isclose(region["density"], region["count"] / region["areaKm2"])
        assert math.isclose(
            region["coveredAreaKm2"] + region["uncoveredAreaKm2"], region["areaKm2"]
        )
    engine = create_db_engine(Settings())
    report = {
        "checkedAt": datetime.now(UTC).isoformat(),
        "snapshotId": snapshot["snapshotId"],
        "algorithmVersion": snapshot["metadata"]["algorithmVersion"],
        "runId": snapshot["metadata"]["runId"],
        "province": snapshot["province"],
        "timings": [timing],
    }
    try:
        with create_session_factory(engine)() as session:
            stored = session.get(AnalysisSnapshot, snapshot["snapshotId"])
            grid = stored.result["layers"]["grid"]["features"]
            assert len(grid) == snapshot["metadata"]["grid"]["cellCount"]
            assert (
                sum(f["properties"]["count"] for f in grid)
                == snapshot["metadata"]["grid"]["assignedCount"]
            )
            assert (
                sum(f["properties"]["count"] for f in grid)
                + snapshot["metadata"]["grid"]["outsideBoundaryCount"]
                == count
            )
            assert len(stored.result["layers"]["coverage"]["features"]) == 122
            assert len(stored.result["layers"]["uncovered"]["features"]) == 122
            classifications = dict(
                session.execute(
                    select(PoiQuality.classification, func.count()).group_by(
                        PoiQuality.classification
                    )
                ).all()
            )
            assert sum(classifications.values()) == count
            report.update(
                classifications=classifications,
                reviewCount=session.scalar(
                    select(func.count())
                    .select_from(PoiQuality)
                    .where(PoiQuality.needs_review.is_(True))
                ),
                incompleteDistricts=session.scalar(
                    select(func.count())
                    .select_from(AnalysisScopeQuality)
                    .where(AnalysisScopeQuality.completeness_warning.is_(True))
                ),
                importedStatistics=session.scalar(
                    select(func.count()).select_from(PublicStatistic)
                ),
                grid=snapshot["metadata"]["grid"],
                geometryRepairCount=len(snapshot["metadata"]["repairs"]),
                assignment={
                    k: v
                    for k, v in snapshot["metadata"]["assignment"].items()
                    if k.endswith("Count")
                },
            )
            assert classifications == snapshot["metadata"]["classificationCounts"]
            indexes = session.execute(text("SHOW INDEX FROM charging_stations")).mappings().all()
            report["stationIndexes"] = [
                {
                    "name": r["Key_name"],
                    "column": r["Column_name"],
                    "unique": not bool(r["Non_unique"]),
                }
                for r in indexes
            ]
            city = snapshot["cities"][0]["code"]
            district = next(r["code"] for r in snapshot["districts"] if r["cityCode"] == city)
            city_boundary = session.get(AnalysisBoundary, city)
            west, south, east, north = shape(city_boundary.geometry).bounds
            bbox = (west, south, (west + east) / 2, (south + north) / 2)
            statement = (
                StationRepository(session)
                .query(real_only=True, exact_adcode=district, bbox=bbox)
                .with_only_columns(ChargingStation.id, maintain_column_froms=True)
                .limit(200)
            )
            sql = str(statement.compile(engine, compile_kwargs={"literal_binds": True}))
            report["countyBboxQueryPlan"] = [
                dict(r) for r in session.execute(text("EXPLAIN " + sql)).mappings()
            ]
        for path in [
            f"/stations?city={city}&page_size=200",
            f"/stations?city={city}&adcode={district}&page_size=200",
            f"/stations?city={city}&bbox=" + ",".join(map(str, bbox)) + "&page_size=200",
            f"/analysis/layers/coverage?city={city}&adcode={district}",
            f"/analysis/layers/grid?city={city}&adcode={district}",
            "/quality/pois?classification=personal",
            "/statistics/public",
        ]:
            data, timing = request_json(path, 5)
            if "/stations" in path:
                assert all(r["cityCode"] == city and not r["simulated"] for r in data["items"])
                assert all("identity_hash" not in r for r in data["items"])
                if "adcode=" in path:
                    assert all(r["adcode"] == district for r in data["items"])
            elif "/analysis/layers" in path:
                assert data["snapshotId"] == snapshot["snapshotId"]
            report["timings"].append(timing)
        report["checks"] = (
            "province/city/county counts, shares, area identities, grid conservation, classification and snapshot consistency verified"
        )
        return report
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit()
    content = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(content + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "report": str(args.output),
                    "snapshotId": report["snapshotId"],
                    "checks": report["checks"],
                },
                ensure_ascii=True,
            )
        )
    else:
        print(content)


if __name__ == "__main__":
    main()
