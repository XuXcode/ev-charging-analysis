"""Planning-reference scoring over demand POIs and existing stations.

Descriptive, versioned, reproducible. For each 5km grid cell over the province
we count demand POIs (five weighted types) and nearby supply stations. The
final "planning reference score" is high where demand evidence is strong and
nearby supply is thin. It is a screening hint, not a construction decision,
and the API response must keep saying so.

The result is persisted into demand_score_runs with an input hash so identical
inputs reuse the same snapshot, mirroring the analysis snapshot pattern.
"""

import hashlib
import json
import math
import time
import uuid
from collections import Counter

from shapely import STRtree, union_all
from shapely.geometry import Point, box, shape
from sqlalchemy import select

from app.core.config import Settings
from app.db.session import create_db_engine, create_session_factory
from app.models import (
    AnalysisBoundary,
    ChargingStation,
    DemandPoi,
    DemandScoreRun,
    PoiQuality,
)
from app.models.demand import utc_now
from app.services.analysis.geometry import (
    COORDINATE_NOTICE,
    display_feature,
    to_metric,
)

ALGORITHM_VERSION = "planning-reference-v2"
GRID_STEP_M = 5000
DEMAND_WEIGHTS = {
    "shopping": 1.0,
    "hospital": 1.2,
    "office": 1.0,
    "parking": 0.8,
    "residential": 1.1,
}

PARAMETERS = {
    "algorithm": ALGORITHM_VERSION,
    "gridStepM": GRID_STEP_M,
    "demandWeights": DEMAND_WEIGHTS,
    "supplyRadiusM": GRID_STEP_M,  # one grid step = neighborhood supply window
    "supplyCap": 20,  # ~20 nearby stations saturate the supply adequacy term
    "supplyOffset": 0.75,  # supply adequacy offsets at most 75% of the demand score
    "scoreScale": "0-100 descriptive, not a probability",
    "supplyBasis": "public_candidate stations within the same and 8 adjacent cells",
    "notice": "需求代理评分，非建设决策依据；POI样本不代表官方总量。",
}


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def demand_input_rows(session):
    """Fingerprint of demand POIs and supply stations used by the score."""
    demand = session.execute(
        select(
            DemandPoi.poi_id,
            DemandPoi.demand_type,
            DemandPoi.adcode,
            DemandPoi.longitude,
            DemandPoi.latitude,
        ).order_by(DemandPoi.id)
    ).all()
    supply = session.execute(
        select(
            ChargingStation.id,
            ChargingStation.longitude,
            ChargingStation.latitude,
            ChargingStation.adcode,
        )
        .join(PoiQuality, PoiQuality.station_id == ChargingStation.id)
        .where(
            ChargingStation.source == "amap",
            ChargingStation.adcode.startswith("43"),
            PoiQuality.classification == "public_candidate",
        )
        .order_by(ChargingStation.id)
    ).all()
    boundaries = session.execute(
        select(AnalysisBoundary.adcode, AnalysisBoundary.content_hash, AnalysisBoundary.geometry)
        .order_by(AnalysisBoundary.adcode)
    ).all()
    return demand, supply, boundaries


def input_fingerprint(demand, supply, boundaries):
    return digest(
        {
            "demand": [tuple(map(str, row)) for row in demand],
            "supply": [tuple(map(str, row)) for row in supply],
            "boundaries": [
                (row.adcode, row.content_hash, row.geometry) for row in boundaries
            ],
        }
    )


def run_scoring(session, *, force=False):
    started = time.perf_counter()
    demand, supply, boundaries = demand_input_rows(session)
    if not demand or not supply or not boundaries:
        raise ValueError("需要需求POI、公共候选站点和行政边界才能评分")
    if len(boundaries) != 136:
        raise ValueError("需要136条真实边界记录")
    city_geoms = {
        row.adcode: to_metric(shape(row.geometry))
        for row in boundaries
        if row.adcode.endswith("00")
    }
    if len(city_geoms) != 14:
        raise ValueError("需要14条市州边界")
    district_geoms = {
        row.adcode: to_metric(shape(row.geometry))
        for row in boundaries
        if not row.adcode.endswith("00")
    }
    province = union_all(list(city_geoms.values()))

    fp = input_fingerprint(demand, supply, boundaries)
    existing = session.scalar(
        select(DemandScoreRun.id)
        .where(DemandScoreRun.input_hash == fp, DemandScoreRun.status == "completed")
        .order_by(DemandScoreRun.created_at.desc())
        .limit(1)
    )
    if existing and not force:
        return {"snapshotId": existing, "reused": True, "seconds": time.perf_counter() - started}

    step = GRID_STEP_M
    west, south, east, north = province.bounds
    x0, y0 = math.floor(west / step), math.floor(south / step)
    x1, y1 = math.floor(east / step), math.floor(north / step)

    # Weighted demand per cell.
    demand_cells = Counter()
    demand_type_counts = Counter()
    outside = 0
    for row in demand:
        point = to_metric(Point(float(row.longitude), float(row.latitude)))
        if not province.covers(point):
            outside += 1
            continue
        x, y = math.floor(point.x / step), math.floor(point.y / step)
        demand_cells[(x, y)] += DEMAND_WEIGHTS.get(row.demand_type, 0.0)
        demand_type_counts[row.demand_type] += 1

    # Supply per cell.
    supply_cells = Counter()
    for row in supply:
        point = to_metric(Point(float(row.longitude), float(row.latitude)))
        if not province.covers(point):
            continue
        x, y = math.floor(point.x / step), math.floor(point.y / step)
        supply_cells[(x, y)] += 1

    cells = []
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            cell_key = (x, y)
            cell = box(x * step, y * step, (x + 1) * step, (y + 1) * step).intersection(province)
            if cell.is_empty or cell.area < 1:
                continue
            area_km2 = cell.area / 1e6
            demand_value = demand_cells.get(cell_key, 0.0)
            supply_around = sum(
                supply_cells.get((x + dx, y + dy), 0)
                for dx in (-1, 0, 1)
                for dy in (-1, 0, 1)
            )
            cells.append(
                {
                    "key": f"{x}:{y}",
                    "cell": cell,
                    "demandWeighted": demand_value,
                    "demandDensity": demand_value / area_km2 if area_km2 else 0.0,
                    "supplyCount": supply_around,
                    "areaKm2": area_km2,
                }
            )
    # Demand density descriptive threshold (95th percentile across positive cells).
    positive = sorted(c["demandDensity"] for c in cells if c["demandWeighted"] > 0)
    threshold = positive[math.ceil(len(positive) * 0.95) - 1] if positive else None
    max_density = max((c["demandDensity"] for c in cells), default=0) or 1e-9
    for c in cells:
        c["demandScore"] = min(100.0, c["demandDensity"] / max_density * 100)
        c["supplyScore"] = min(100.0, c["supplyCount"] * 5.0)
        c["planningScore"] = max(
            0.0, c["demandScore"] * (1 - min(0.75, c["supplyScore"] / 100))
        )

    # District aggregate by cell representative point.
    district_metrics = {}
    tree = STRtree(list(district_geoms.values()))
    keys = list(district_geoms)
    for c in cells:
        if c["planningScore"] <= 0:
            continue
        centroid = c["cell"].representative_point()
        hits = [keys[int(i)] for i in tree.query(centroid, predicate="intersects")]
        if len(hits) != 1:
            continue
        adcode = hits[0]
        agg = district_metrics.setdefault(
            adcode, {"adcode": adcode, "sumPlanning": 0.0, "cells": 0, "maxPlanning": 0.0}
        )
        agg["sumPlanning"] += c["planningScore"]
        agg["cells"] += 1
        agg["maxPlanning"] = max(agg["maxPlanning"], c["planningScore"])
    for agg in district_metrics.values():
        agg["meanPlanning"] = agg["sumPlanning"] / agg["cells"]
        agg.pop("sumPlanning", None)

    features = []
    for c in cells:
        properties = {
            "id": c["key"],
            "demandWeighted": round(c["demandWeighted"], 2),
            "demandDensity": round(c["demandDensity"], 4),
            "supplyCount": c["supplyCount"],
            "planningScore": round(c["planningScore"], 2),
            "areaKm2": round(c["areaKm2"], 2),
        }
        features.append(display_feature(c["cell"], properties, 0))
    metadata = {
        "algorithmVersion": ALGORITHM_VERSION,
        "parameters": PARAMETERS,
        "inputHash": fp,
        "demandCount": len(demand),
        "supplyCount": len(supply),
        "gridCellCount": len(cells),
        "demandOutsideBoundaryCount": outside,
        "demandDensityThreshold": threshold,
        "demandTypeCounts": dict(demand_type_counts),
        "districtAggregates": district_metrics,
        "notice": PARAMETERS["notice"],
        "coordinateNotice": COORDINATE_NOTICE,
        "seconds": time.perf_counter() - started,
    }
    result = {
        "metadata": metadata,
        "layers": {
            "planning": {"type": "FeatureCollection", "features": features},
        },
        "summary": {
            "totalDemandWeighted": round(sum(c["demandWeighted"] for c in cells), 2),
            "avgPlanningScore": round(
                sum(c["planningScore"] for c in cells) / len(cells) if cells else 0, 2
            ),
            "topDistricts": sorted(
                district_metrics.values(), key=lambda d: -d["meanPlanning"]
            )[:10],
        },
    }
    snapshot = DemandScoreRun(
        id=uuid.uuid4().hex,
        status="completed",
        algorithm_version=ALGORITHM_VERSION,
        input_hash=fp,
        parameters=PARAMETERS,
        result=result,
        created_at=utc_now(),
    )
    session.add(snapshot)
    session.flush()
    return {
        "snapshotId": snapshot.id,
        "reused": False,
        "gridCellCount": len(cells),
        "seconds": result["metadata"]["seconds"],
    }


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser(description="需求代理评分；非建设决策依据")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    engine = create_db_engine(settings)
    try:
        with create_session_factory(engine)() as session, session.begin():
            result = run_scoring(session, force=args.force)
        print(json.dumps(result, ensure_ascii=True, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()