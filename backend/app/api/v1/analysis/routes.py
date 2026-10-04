from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from shapely import make_valid
from shapely.geometry import box, shape
from sqlalchemy import and_, func, or_, select

from app.api.dependencies import SessionDep
from app.models import AnalysisBoundary, AnalysisScopeQuality, AnalysisSnapshot, ChargingStation
from app.schemas.common import APIResponse
from app.schemas.filters import PoiClassification, ReviewStatus
from app.services.analysis.job import ALGORITHM_VERSION, digest, station_fingerprint, station_rows
from app.utils.bbox import parse_bbox

router = APIRouter(prefix="/api/v1/analysis", tags=["POI样本空间分析"])


def latest_id(session, classification=None, review_status=None, batch=None, needs_review=None):
    snapshot_id = session.scalar(
        select(AnalysisSnapshot.id)
        .where(AnalysisSnapshot.status == "completed")
        .where(
            func.coalesce(AnalysisSnapshot.parameters["filters"]["needsReview"].as_string(), "")
            == ("" if needs_review is None else str(needs_review).lower())
        )
        .where(
            func.coalesce(AnalysisSnapshot.parameters["filters"]["classification"].as_string(), "")
            == (classification or "")
        )
        .where(
            func.coalesce(AnalysisSnapshot.parameters["filters"]["reviewStatus"].as_string(), "")
            == (review_status or "")
        )
        .where(
            or_(
                func.coalesce(AnalysisSnapshot.parameters["filters"]["batch"].as_string(), "")
                == (batch or ""),
                and_(
                    batch is not None,
                    func.coalesce(AnalysisSnapshot.parameters["filters"]["batch"].as_string(), "")
                    == "",
                    func.json_length(AnalysisSnapshot.result["metadata"]["datasetQualityRunIds"])
                    == 1,
                    AnalysisSnapshot.result["metadata"]["datasetQualityRunIds"][0].as_string()
                    == batch,
                ),
            )
        )
        .order_by(AnalysisSnapshot.computed_at.desc())
        .limit(1)
    )
    if snapshot_id is None:
        raise HTTPException(
            404, "该筛选口径尚未生成真实空间分析快照，请运行对应分析任务；不会回退全样本结果"
        )
    return snapshot_id


@router.get(
    "/latest",
    response_model=APIResponse[dict],
    summary="读取当前筛选的持久化分析快照",
    description="按POI类别、复核状态和质量批次匹配已完成快照。缺失口径返回404，不回退全样本，不启动几何计算。指标为POI样本数量、模型密度和1km直线覆盖，非官方设施统计。",
)
def latest(
    session: SessionDep,
    classification: PoiClassification | None = None,
    review_status: ReviewStatus | None = None,
    needs_review: bool | None = Query(
        None, description="规则识别的待复核线索，与POI类别/人工状态取交集；缺失快照不回退"
    ),
    batch: str | None = Query(None, pattern=r"^[a-f0-9]{32}$"),
):
    snapshot_id = latest_id(session, classification, review_status, batch, needs_review)
    metadata, province, regions, computed = session.execute(
        select(
            AnalysisSnapshot.result["metadata"],
            AnalysisSnapshot.result["province"],
            AnalysisSnapshot.result["regions"],
            AnalysisSnapshot.computed_at,
        ).where(AnalysisSnapshot.id == snapshot_id)
    ).one()
    count, updated = session.execute(
        select(func.count(), func.max(ChargingStation.collected_at)).where(
            ChargingStation.source == "amap", ChargingStation.adcode.startswith("43")
        )
    ).one()
    boundaries = session.execute(
        select(
            AnalysisBoundary.adcode,
            AnalysisBoundary.content_hash,
            AnalysisBoundary.source_url,
            AnalysisBoundary.coordinate_system,
        ).order_by(AnalysisBoundary.adcode)
    ).all()
    boundary_hash = digest([tuple(row) for row in boundaries])
    scope_hash = digest(
        [
            tuple(row)
            for row in session.execute(
                select(
                    AnalysisScopeQuality.adcode,
                    AnalysisScopeQuality.completeness_warning,
                    AnalysisScopeQuality.run_id,
                ).order_by(AnalysisScopeQuality.adcode)
            )
        ]
    )
    stale = (
        count != metadata.get("datasetStationCount", metadata["stationCount"])
        or (updated.isoformat() + "Z" if updated else None) != metadata["sourceUpdatedAt"]
        or boundary_hash != metadata["boundaryHash"]
        or (
            "stationHash" in metadata
            and station_fingerprint(station_rows(session))
            != metadata.get("datasetStationHash", metadata["stationHash"])
        )
        or ("scopeHash" in metadata and scope_hash != metadata["scopeHash"])
        or metadata.get("algorithmVersion", ALGORITHM_VERSION) != ALGORITHM_VERSION
    )
    return APIResponse(
        data={
            "snapshotId": snapshot_id,
            "computedAt": computed.isoformat() + "Z",
            "stale": stale,
            "metadata": metadata,
            "province": province,
            "cities": [row for row in regions if row["level"] == "city"],
            "districts": [row for row in regions if row["level"] == "district"],
            "indicatorDefinitions": [
                {
                    "key": "count",
                    "label": "POI样本数量",
                    "unit": "条",
                    "formula": "按供应方行政编码计数",
                },
                {
                    "key": "density",
                    "label": "POI样本密度",
                    "unit": "条/km²",
                    "formula": "样本数量 / 边界模型面积",
                },
                {
                    "key": "coveragePercent",
                    "label": "1km样本覆盖率",
                    "unit": "%",
                    "formula": "边界与所有1km样本缓冲区并集交集面积 / 边界面积 × 100",
                },
            ],
        }
    )


@router.get(
    "/boundaries",
    response_model=APIResponse[dict],
    summary="读取真实行政区GeoJSON边界",
    description="parent=430000返回14市州；市州编码返回所属区县。坐标为GCJ-02，内容哈希可追溯。不存在的范围返回404。",
)
def boundaries(session: SessionDep, parent: str = Query("430000", pattern=r"^43\d{4}$")):
    statement = select(AnalysisBoundary)
    if parent == "430000":
        statement = statement.where(AnalysisBoundary.level == "city")
    else:
        statement = statement.where(
            AnalysisBoundary.city_code == parent, AnalysisBoundary.level == "district"
        )
    rows = list(session.scalars(statement.order_by(AnalysisBoundary.adcode)))
    if not rows:
        raise HTTPException(404, "没有该范围的真实行政边界")
    return APIResponse(
        data={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "adcode": row.adcode,
                        "name": row.name,
                        "cityCode": row.city_code,
                        "source": row.source_url,
                        "hash": row.content_hash,
                    },
                    "geometry": row.geometry,
                }
                for row in rows
            ],
            "coordinateSystem": "GCJ-02",
            "notice": "原始展示边界；分析快照显式记录计算几何修复。",
        }
    )


@router.get(
    "/layers/{layer}",
    response_model=APIResponse[dict],
    summary="读取固定版本的样本分析图层",
    description="只读取快照中既有网格、描述性聚集、1km覆盖或未覆盖几何。snapshot_id固定分析版本；city、adcode及GCJ-02 bbox筛选范围。热点为描述性阈值，未覆盖不代表实际服务风险。",
)
def layer_geometry(
    session: SessionDep,
    layer: Literal["grid", "hotspots", "coverage", "uncovered"],
    snapshot_id: str | None = Query(None, pattern=r"^[a-f0-9]{32}$"),
    city: str | None = Query(None, pattern=r"^43\d{4}$"),
    adcode: str | None = Query(None, pattern=r"^43\d{4}$"),
    bbox: str | None = Query(None, max_length=150),
):
    snapshot_id = snapshot_id or latest_id(session)
    key = "grid" if layer == "hotspots" else layer
    data = session.scalar(
        select(AnalysisSnapshot.result["layers"][key]).where(
            AnalysisSnapshot.id == snapshot_id, AnalysisSnapshot.status == "completed"
        )
    )
    if data is None:
        raise HTTPException(404, "未找到分析快照或图层")
    features = data["features"]
    if city and not city.endswith("00"):
        raise HTTPException(422, "city须为市州行政编码")
    if city and adcode and adcode[:4] != city[:4]:
        raise HTTPException(422, "city与adcode不属于同一市州")
    for scope_code in (city, adcode):
        if scope_code and session.get(AnalysisBoundary, scope_code) is None:
            raise HTTPException(404, "没有该行政区边界")
    if key != "grid":
        if city:
            features = [
                feature for feature in features if feature["properties"]["cityCode"] == city
            ]
        if adcode:
            features = [feature for feature in features if feature["properties"]["code"] == adcode]
    else:
        if city or adcode:
            region = session.get(AnalysisBoundary, adcode or city)
            if region is None:
                raise HTTPException(404, "没有该行政区边界")
            selection = make_valid(shape(region.geometry))
            features = [
                feature for feature in features if shape(feature["geometry"]).intersects(selection)
            ]
        if layer == "hotspots":
            features = [feature for feature in features if feature["properties"]["hotspot"]]
    if bbox:
        selection = box(*parse_bbox(bbox))
        features = [
            feature
            for feature in features
            if not shape(feature["geometry"]).is_empty
            and shape(feature["geometry"]).intersects(selection)
        ]
    return APIResponse(
        data={
            "type": "FeatureCollection",
            "features": features,
            "snapshotId": snapshot_id,
            "layer": layer,
            "coordinateSystem": "GCJ-02",
            "notice": "仅展示几何采用25m拓扑保留简化；面积指标使用未简化计算几何。网格边界未简化。范围筛选保留相交的全省固定网格，不重新计算局部网格密度。",
        }
    )
