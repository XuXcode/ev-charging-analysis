"""Read-only same-input comparison of v1.1 and v1.2 coverage models."""

import json
import time
from pathlib import Path

from shapely import union_all
from shapely.geometry import Point
from sqlalchemy import select

from app.core.config import Settings
from app.db.session import create_db_engine, create_session_factory
from app.models import AnalysisBoundary
from app.services.analysis.geometry import (
    SCALE_GEOD,
    coverage_union,
    prepare_boundary,
    region_metrics,
    sample_buffer,
    sample_coverage_union,
    to_display,
    to_metric,
)
from app.services.analysis.job import station_fingerprint, station_rows


def main():
    engine = create_db_engine(Settings())
    try:
        with create_session_factory(engine)() as session:
            rows = [
                row for row in station_rows(session) if row.classification == "public_candidate"
            ]
            boundaries = list(
                session.scalars(select(AnalysisBoundary).where(AnalysisBoundary.level == "city"))
            )
            province = union_all(
                [prepare_boundary(boundary.geometry)[0] for boundary in boundaries]
            )
        display_points = [Point(float(row.longitude), float(row.latitude)) for row in rows]
        metric_points = [to_metric(point) for point in display_points]
        started = time.perf_counter()
        old = coverage_union(metric_points, 1000, 24)
        old_seconds = time.perf_counter() - started
        started = time.perf_counter()
        new = sample_coverage_union(display_points, 1000, 256)
        new_seconds = time.perf_counter() - started
        old_metrics, _, _ = region_metrics(province, old, len(rows), len(rows))
        new_metrics, covered, uncovered = region_metrics(province, new, len(rows), len(rows))
        errors = {"v1.1": [], "v1.2": []}
        # Uniform coordinate-domain probes, including the province's geographic extremes.
        # These are mathematical audit probes, not invented business samples.
        for longitude in (108.5, 110, 111.5, 113, 114):
            for latitude in (25, 26.5, 28, 29.5, 30):
                point = Point(longitude, latitude)
                for version, ring in (
                    ("v1.1", to_metric(point).buffer(1000, quad_segs=24)),
                    ("v1.2", sample_buffer(point)),
                ):
                    for x, y in to_display(ring).exterior.coords:
                        errors[version].append(
                            abs(SCALE_GEOD.inv(longitude, latitude, x, y)[2] - 1000)
                        )
        report = {
            "scope": "public_candidate",
            "stationCount": len(rows),
            "stationInputHash": station_fingerprint(rows),
            "comparisonBasis": "同一补采后样本和同一行政边界，比较距离模型及96/256边离散化的综合变化",
            "v1.1": {
                **old_metrics,
                "unionSeconds": old_seconds,
                "maximumProbeRadialErrorM": max(errors["v1.1"]),
            },
            "v1.2": {
                **new_metrics,
                "unionSeconds": new_seconds,
                "maximumProbeRadialErrorM": max(errors["v1.2"]),
            },
            "coverageChangeKm2": new_metrics["coveredAreaKm2"] - old_metrics["coveredAreaKm2"],
            "coverageChangePercentagePoints": new_metrics["coveragePercent"]
            - old_metrics["coveragePercent"],
            "areaConservationErrorKm2": abs(covered.area + uncovered.area - province.area) / 1e6,
            "notice": "探针只检验椭球尺度模型的径向误差，不测量GCJ-02基准误差、真实设施完整性或道路覆盖。耗时为本机单次测量。",
            "references": [
                "https://pyproj4.github.io/pyproj/stable/api/geod.html",
                "https://shapely.readthedocs.io/en/stable/manual.html",
            ],
        }
        path = Path(__file__).resolve().parents[4] / "docs/reports/GEOMETRY_V12_AUDIT.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=True, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
