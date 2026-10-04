"""Persist reusable, versioned sample analysis; never mutate source stations."""

import hashlib
import json
import math
import time
import uuid
from collections import Counter, namedtuple
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import get_args

import pyproj
import shapely
from shapely import union_all
from shapely.geometry import Point
from sqlalchemy import select

from app.core.config import Settings
from app.db.session import create_db_engine, create_session_factory
from app.models import (
    AnalysisBoundary,
    AnalysisScopeQuality,
    AnalysisSnapshot,
    ChargingStation,
    CollectionRun,
    PoiQuality,
)
from app.models.entities import utc_now
from app.schemas.filters import PoiClassification, ReviewStatus
from app.services.analysis.geometry import (
    COORDINATE_NOTICE,
    METRIC_PIPELINE,
    assignment_check,
    display_feature,
    grid_analysis,
    prepare_boundary,
    region_metrics,
    sample_coverage_union,
    to_metric,
)
from app.services.governance import latest_province_run

ALGORITHM_VERSION = "sample-spatial-v1.2"
PARAMETERS = {
    "radiusM": 1000,
    "gridStepM": 5000,
    "bufferSegments": 256,
    "bufferModel": "ellipsoid-scale-ring-on-GCJ-chart",
    "bufferEllipsoid": "WGS84-scale-only-no-datum-conversion",
    "bufferMaximumChordSagittaM": 1000 * (1 - math.cos(math.pi / 256)),
    "displayToleranceM": 25,
    "sampleScope": "all_retained_pois",
    "countAssignment": "source_adcode",
    "coordinateModel": "GCJ02-chart-LAEA-approximate",
    "metricPipeline": METRIC_PIPELINE,
}


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def station_rows(session):
    """Shared input fingerprint: detect coordinate, attribution and governance changes."""
    return session.execute(
        select(
            ChargingStation.id,
            ChargingStation.poi_id,
            ChargingStation.adcode,
            ChargingStation.longitude,
            ChargingStation.latitude,
            ChargingStation.collected_at,
            PoiQuality.classification,
            PoiQuality.needs_review,
            PoiQuality.review_status,
            PoiQuality.rules_version,
            PoiQuality.run_id.label("quality_run_id"),
        )
        .outerjoin(PoiQuality)
        .where(ChargingStation.source == "amap", ChargingStation.adcode.startswith("43"))
        .order_by(ChargingStation.id)
    ).all()


def station_fingerprint(rows):
    return digest([list(map(str, row)) for row in rows])


def freeze_inputs(run, boundaries, scopes, rows, parameters):
    return {
        "schemaVersion": 1,
        "runId": run.id,
        "parameters": parameters,
        "rowFields": list(rows[0]._fields),
        "rows": [
            [
                str(value)
                if isinstance(value, Decimal)
                else value.isoformat()
                if isinstance(value, datetime)
                else value
                for value in row
            ]
            for row in rows
        ],
        "boundaries": [
            {
                key: getattr(boundary, key).isoformat()
                if key == "fetched_at"
                else getattr(boundary, key)
                for key in (
                    "adcode",
                    "city_code",
                    "name",
                    "level",
                    "geometry",
                    "content_hash",
                    "source_url",
                    "coordinate_system",
                    "fetched_at",
                )
            }
            for boundary in boundaries
        ],
        "scopes": [
            {
                key: getattr(scope, key)
                for key in ("adcode", "city_code", "name", "run_id", "completeness_warning")
            }
            for scope in scopes
        ],
    }


def thaw_inputs(frozen):
    if frozen.get("schemaVersion") != 1:
        raise ValueError("不支持该冻结输入格式")
    record = namedtuple("FrozenStation", frozen["rowFields"])
    rows = []
    for values in frozen["rows"]:
        data = dict(zip(frozen["rowFields"], values, strict=True))
        data["longitude"] = Decimal(data["longitude"])
        data["latitude"] = Decimal(data["latitude"])
        data["collected_at"] = datetime.fromisoformat(data["collected_at"])
        rows.append(record(**data))
    boundaries = [
        SimpleNamespace(**{**item, "fetched_at": datetime.fromisoformat(item["fetched_at"])})
        for item in frozen["boundaries"]
    ]
    return (
        SimpleNamespace(id=frozen["runId"]),
        boundaries,
        [SimpleNamespace(**item) for item in frozen["scopes"]],
        rows,
    )


def run_analysis(
    session,
    *,
    force=False,
    classification=None,
    review_status=None,
    batch=None,
    needs_review=None,
    frozen_input=None,
):
    started = time.perf_counter()
    if frozen_input is not None:
        run, boundaries, scopes, all_rows = thaw_inputs(frozen_input)
    else:
        run = latest_province_run(session)
        boundaries = list(
            session.scalars(select(AnalysisBoundary).order_by(AnalysisBoundary.adcode))
        )
        scopes = list(
            session.scalars(select(AnalysisScopeQuality).order_by(AnalysisScopeQuality.adcode))
        )
        all_rows = station_rows(session)
    if (
        len(boundaries) != 136
        or len(scopes) != 122
        or not all_rows
        or any(row.classification is None for row in all_rows)
    ):
        raise ValueError("需完成真实站点治理与14市州/122区县边界准备")
    if classification and classification not in get_args(PoiClassification):
        raise ValueError("无效POI分类")
    if review_status and review_status not in get_args(ReviewStatus):
        raise ValueError("无效复核状态")
    if batch and session.get(CollectionRun, batch) is None:
        raise ValueError("没有该采集批次")
    filters = {
        key: value
        for key, value in {
            "classification": classification,
            "reviewStatus": review_status,
            "batch": batch,
            "needsReview": needs_review,
        }.items()
        if value is not None and value != ""
    }
    rows = [
        row
        for row in all_rows
        if (not classification or row.classification == classification)
        and (not review_status or row.review_status == review_status)
        and (not batch or row.quality_run_id == batch)
        and (needs_review is None or bool(row.needs_review) == needs_review)
    ]
    if any(scope.run_id != run.id for scope in scopes):
        raise ValueError("区县完整性记录与当前批次不一致，请先执行治理任务")
    if len([b for b in boundaries if b.level == "city"]) != 14 or {
        b.adcode for b in boundaries if b.level == "district"
    } != {s.adcode for s in scopes}:
        raise ValueError("边界层级或区县编码与真实采集范围不一致")
    boundary_hash = digest(
        [(b.adcode, b.content_hash, b.source_url, b.coordinate_system) for b in boundaries]
    )
    parameters = {
        **PARAMETERS,
        "filters": filters,
        "shapelyVersion": shapely.__version__,
        "pyprojVersion": pyproj.__version__,
        "geosVersion": shapely.geos_version_string,
        "sourceHash": digest(
            [
                (path.name, path.read_text(encoding="utf-8"))
                for path in (Path(__file__), Path(__file__).with_name("geometry.py"))
            ]
        ),
    }
    if frozen_input is not None and frozen_input["parameters"] != parameters:
        raise ValueError("算法代码、参数或依赖版本已变化，不能宣称同版本复现；请使用原版本运行")
    frozen = frozen_input or freeze_inputs(run, boundaries, scopes, all_rows, parameters)
    input_hash = digest(
        {
            "runId": run.id,
            "boundaries": boundary_hash,
            "scopes": [(s.adcode, s.completeness_warning) for s in scopes],
            "stations": [list(map(str, row)) for row in rows],
            "datasetStations": station_fingerprint(all_rows),
            "parameters": parameters,
        }
    )
    existing = session.scalar(
        select(AnalysisSnapshot.id)
        .where(AnalysisSnapshot.input_hash == input_hash, AnalysisSnapshot.status == "completed")
        .order_by(AnalysisSnapshot.computed_at.desc())
        .limit(1)
    )
    if existing and not force:
        return {"snapshotId": existing, "reused": True, "seconds": time.perf_counter() - started}
    points = [to_metric(Point(float(row.longitude), float(row.latitude))) for row in rows]
    counts = Counter(row.adcode for row in rows)
    review_counts = Counter(row.adcode for row in rows if row.needs_review)
    scope_map = {scope.adcode: scope for scope in scopes}
    prepared = {}
    repairs = []
    for boundary in boundaries:
        geometry, audit = prepare_boundary(boundary.geometry)
        prepared[boundary.adcode] = geometry
        if audit["repaired"]:
            repairs.append({"adcode": boundary.adcode, **audit})
    province = union_all([prepared[b.adcode] for b in boundaries if b.level == "city"])
    coverage = sample_coverage_union(
        [Point(float(row.longitude), float(row.latitude)) for row in rows],
        PARAMETERS["radiusM"],
        PARAMETERS["bufferSegments"],
    )
    features = {"coverage": [], "uncovered": []}
    regions = []
    for boundary in boundaries:
        districts = (
            [scope for scope in scopes if scope.city_code == boundary.adcode]
            if boundary.level == "city"
            else [scope_map[boundary.adcode]]
        )
        codes = {scope.adcode for scope in districts}
        count = sum(counts[code] for code in codes)
        metrics, covered, uncovered = region_metrics(
            prepared[boundary.adcode], coverage, count, len(rows)
        )
        warning_codes = [scope.adcode for scope in districts if scope.completeness_warning]
        properties = {
            "code": boundary.adcode,
            "cityCode": boundary.city_code,
            "name": boundary.name,
            "level": boundary.level,
            **metrics,
            "reviewCount": sum(review_counts[code] for code in codes),
            "completenessWarning": bool(warning_codes),
            "incompleteDistricts": warning_codes,
            "geometryRepaired": any(r["adcode"] == boundary.adcode for r in repairs),
            "qualityStatus": "名称与类别尚未人工全面核验",
        }
        if not rows:
            properties["sharePercent"] = None
        regions.append(properties)
        if boundary.level == "district":
            for name, geometry in (("coverage", covered), ("uncovered", uncovered)):
                features[name].append(
                    display_feature(
                        geometry,
                        {
                            "code": boundary.adcode,
                            "cityCode": boundary.city_code,
                            "name": boundary.name,
                            "completenessWarning": bool(warning_codes),
                        },
                        PARAMETERS["displayToleranceM"],
                    )
                )
    cells, grid_metadata = grid_analysis(province, points, PARAMETERS["gridStepM"])
    grid_features = [display_feature(cell, properties, 0) for cell, properties in cells]
    province_metrics, _, _ = region_metrics(province, coverage, len(rows), len(rows))
    if not rows:
        province_metrics["sharePercent"] = None
    metadata = {
        "algorithmVersion": ALGORITHM_VERSION,
        "runId": run.id,
        "stationCount": len(rows),
        "datasetStationCount": len(all_rows),
        "filters": filters,
        "datasetStationHash": station_fingerprint(all_rows),
        "sourceUpdatedAt": max(row.collected_at for row in all_rows).isoformat() + "Z",
        "parameters": parameters,
        "boundaryHash": boundary_hash,
        "inputHash": input_hash,
        "frozenInputHash": digest(frozen),
        "reproduction": "快照内冻结完整站点输入、行政边界与完整性状态；不读取当前站点进行历史重放",
        "coordinateNotice": COORDINATE_NOTICE,
        "repairs": repairs,
        "boundarySources": [
            {
                "adcode": b.adcode,
                "source": b.source_url,
                "hash": b.content_hash,
                "fetchedAt": b.fetched_at.isoformat() + "Z",
            }
            for b in boundaries
        ],
        "classificationCounts": dict(Counter(row.classification for row in rows)),
        "classificationRulesVersions": sorted({row.rules_version for row in rows}),
        "qualityRunIds": sorted({row.quality_run_id for row in rows}),
        "datasetQualityRunIds": sorted({row.quality_run_id for row in all_rows}),
        "stationHash": station_fingerprint(rows),
        "scopeHash": digest([(s.adcode, s.completeness_warning, s.run_id) for s in scopes]),
        "reviewCount": sum(bool(row.needs_review) for row in rows),
        "completenessWarning": any(s.completeness_warning for s in scopes),
        "incompleteDistricts": [s.adcode for s in scopes if s.completeness_warning],
        "assignment": assignment_check(
            {b.adcode: prepared[b.adcode] for b in boundaries if b.level == "district"},
            points,
            [row.adcode for row in rows],
        ),
        "grid": grid_metadata,
        "seconds": time.perf_counter() - started,
        "notice": (
            "按明确分类/复核/批次条件选择保留POI，不删除原始记录；"
            if filters
            else "所有保留POI均参与计算，包括疑似停业、个人、专用及未知；"
        )
        + "样本覆盖不代表公共营业设施覆盖。检索上限与几何版本影响结论。",
    }
    result = {
        "frozenInputs": frozen,
        "metadata": metadata,
        "province": province_metrics,
        "regions": regions,
        "layers": {
            **{
                name: {"type": "FeatureCollection", "features": layer}
                for name, layer in features.items()
            },
            "grid": {"type": "FeatureCollection", "features": grid_features},
        },
    }
    for evidence in metadata["assignment"]["evidence"]:
        row = rows[evidence.pop("sampleIndex")]
        evidence.update({"stationId": row.id, "poiId": row.poi_id})
    snapshot = AnalysisSnapshot(
        id=uuid.uuid4().hex,
        status="completed",
        algorithm_version=ALGORITHM_VERSION,
        run_id=run.id,
        input_hash=input_hash,
        boundary_hash=boundary_hash,
        parameters=parameters,
        result=result,
        computed_at=utc_now(),
    )
    session.add(snapshot)
    session.flush()
    return {
        "snapshotId": snapshot.id,
        "reused": False,
        "province": province_metrics,
        "districts": 122,
        "grid": grid_metadata,
        "repairs": len(repairs),
        "assignment": metadata["assignment"],
        "seconds": metadata["seconds"],
        "jsonBytes": len(json.dumps(result).encode()),
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="相同输入也生成独立快照")
    parser.add_argument("--classification", choices=get_args(PoiClassification))
    parser.add_argument("--review-status", choices=get_args(ReviewStatus))
    parser.add_argument("--batch", help="当前治理证据关联批次；不是历史POI还原")
    parser.add_argument(
        "--needs-review",
        action="store_true",
        default=None,
        help="仅规则识别的待复核样本，独立于人工状态",
    )
    parser.add_argument("--replay", help="从快照冻结输入重算并核对结果；不使用当前站点或边界")
    args = parser.parse_args()
    engine = create_db_engine(Settings())
    try:
        with create_session_factory(engine)() as session, session.begin():
            if args.replay:
                source = session.get(AnalysisSnapshot, args.replay)
                if source is None or "frozenInputs" not in source.result:
                    raise ValueError("该快照缺少冻结输入，不能宣称历史复现")
                frozen = source.result["frozenInputs"]
                if digest(frozen) != source.result["metadata"].get("frozenInputHash"):
                    raise ValueError("冻结输入哈希不一致，停止重放")
                filters = source.parameters.get("filters", {})
                result = run_analysis(
                    session,
                    force=True,
                    classification=filters.get("classification"),
                    review_status=filters.get("reviewStatus"),
                    batch=filters.get("batch"),
                    needs_review=filters.get("needsReview"),
                    frozen_input=frozen,
                )
                recreated = session.get(AnalysisSnapshot, result["snapshotId"])
                keys = ("province", "regions", "layers")
                matches = digest({key: source.result[key] for key in keys}) == digest(
                    {key: recreated.result[key] for key in keys}
                )
                if not matches:
                    raise ValueError("重放结果与原快照不一致，事务回滚")
                result = {
                    "originalSnapshotId": source.id,
                    "snapshotId": recreated.id,
                    "reproduced": matches,
                    "stationCount": recreated.result["metadata"]["stationCount"],
                    "seconds": result["seconds"],
                }
            else:
                result = run_analysis(
                    session,
                    force=args.force,
                    classification=args.classification,
                    review_status=args.review_status,
                    batch=args.batch,
                    needs_review=args.needs_review,
                )
        print(json.dumps(result, ensure_ascii=True, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
