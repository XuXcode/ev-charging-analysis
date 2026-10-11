"""Planning-reference endpoints. Read-only: no computation, no construction advice."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from shapely import make_valid
from shapely.geometry import box, shape
from sqlalchemy import func, select

from app.api.dependencies import SessionDep
from app.models import AnalysisBoundary, DemandPoi, DemandScoreRun
from app.schemas.common import APIResponse
from app.services.demand.scoring import ALGORITHM_VERSION
from app.utils.bbox import parse_bbox

router = APIRouter(prefix="/api/v1/planning", tags=["规划参考（需求代理评分）"])


def latest_score_id(session):
    snapshot_id = session.scalar(
        select(DemandScoreRun.id)
        .where(
            DemandScoreRun.status == "completed",
            DemandScoreRun.algorithm_version == ALGORITHM_VERSION,
        )
        .order_by(DemandScoreRun.created_at.desc())
        .limit(1)
    )
    if snapshot_id is None:
        raise HTTPException(
            404, "尚无需求代理评分快照；请先采集需求POI并运行评分任务"
        )
    return snapshot_id


@router.get(
    "/latest",
    response_model=APIResponse[dict],
    summary="读取需求代理评分快照",
    description="返回需求POI样本量、5km网格评分元数据与区县聚合。需求代理评分仅供规划参考，不构成建设决策依据；POI样本不代表官方总量。",
)
def latest(session: SessionDep, snapshot_id: str | None = Query(None, pattern=r"^[a-f0-9]{32}$")):
    snapshot_id = snapshot_id or latest_score_id(session)
    snapshot = session.get(DemandScoreRun, snapshot_id)
    if snapshot is None or snapshot.status != "completed":
        raise HTTPException(404, "未找到需求评分快照")
    metadata = snapshot.result["metadata"]
    summary = snapshot.result.get("summary", {})
    return APIResponse(
        data={
            "snapshotId": snapshot.id,
            "computedAt": snapshot.created_at.isoformat() + "Z",
            "algorithmVersion": snapshot.algorithm_version,
            "metadata": metadata,
            "summary": summary,
            "indicatorDefinitions": [
                {
                    "key": "demandWeighted",
                    "label": "加权需求POI数",
                    "unit": "条",
                    "formula": "5类需求POI按权重求和",
                },
                {
                    "key": "demandDensity",
                    "label": "需求POI密度",
                    "unit": "条/km²",
                    "formula": "加权需求POI数 / 网格面积",
                },
                {
                    "key": "supplyCount",
                    "label": "周边站点数",
                    "unit": "座",
                    "formula": "本网格及相邻8网格内公共候选站点数",
                },
                {
                    "key": "planningScore",
                    "label": "需求代理评分",
                    "unit": "0-100",
                    "formula": "需求分 × (1 - 供给充足度)；仅供规划参考",
                },
            ],
        }
    )


@router.get(
    "/layers/{layer}",
    response_model=APIResponse[dict],
    summary="读取需求评分网格图层",
    description="只读取已评分快照中的5km需求代理网格。city/adcode/bbox为范围筛选。需求代理评分非建设决策依据。",
)
def layer_geometry(
    session: SessionDep,
    layer: Literal["planning"],
    snapshot_id: str | None = Query(None, pattern=r"^[a-f0-9]{32}$"),
    city: str | None = Query(None, pattern=r"^43\d{4}$"),
    adcode: str | None = Query(None, pattern=r"^43\d{4}$"),
    bbox: str | None = Query(None, max_length=150),
):
    snapshot_id = snapshot_id or latest_score_id(session)
    data = session.scalar(
        select(DemandScoreRun.result["layers"][layer]).where(
            DemandScoreRun.id == snapshot_id, DemandScoreRun.status == "completed"
        )
    )
    if data is None:
        raise HTTPException(404, "未找到需求评分快照或图层")
    features = data["features"]
    if city and not city.endswith("00"):
        raise HTTPException(422, "city须为市州行政编码")
    if city and adcode and adcode[:4] != city[:4]:
        raise HTTPException(422, "city与adcode不属于同一市州")
    for scope_code in (city, adcode):
        if scope_code and session.get(AnalysisBoundary, scope_code) is None:
            raise HTTPException(404, "没有该行政区边界")
    if city or adcode:
        region = session.get(AnalysisBoundary, adcode or city)
        if region is None:
            raise HTTPException(404, "没有该行政区边界")
        selection = make_valid(shape(region.geometry))
        features = [
            feature
            for feature in features
            if shape(feature["geometry"]).intersects(selection)
        ]
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
            "notice": "需求代理评分，非建设决策依据；POI样本不代表官方总量。",
        }
    )


@router.get(
    "/pois",
    response_model=APIResponse[dict],
    summary="读取需求POI样本",
    description="分页读取已采集需求POI（按类型/区县筛选）。仅展示样本，不代表官方总量。",
)
def demand_pois(
    session: SessionDep,
    demand_type: str | None = Query(
        None, pattern=r"^(shopping|hospital|office|parking|residential)$"
    ),
    adcode: str | None = Query(None, pattern=r"^43\d{4}$"),
    city: str | None = Query(None, pattern=r"^43\d{2}00$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    statement = select(DemandPoi)
    if demand_type:
        statement = statement.where(DemandPoi.demand_type == demand_type)
    if adcode:
        statement = statement.where(DemandPoi.adcode == adcode)
    elif city:
        statement = statement.where(DemandPoi.adcode.startswith(city[:4]))
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    rows = list(
        session.scalars(
            statement.order_by(DemandPoi.id).offset((page - 1) * page_size).limit(page_size)
        )
    )
    return APIResponse(
        data={
            "items": [
                {
                    "poiId": row.poi_id,
                    "name": row.name,
                    "demandType": row.demand_type,
                    "city": row.city,
                    "adcode": row.adcode,
                    "longitude": float(row.longitude),
                    "latitude": float(row.latitude),
                }
                for row in rows
            ],
            "total": total,
            "page": page,
            "pageSize": page_size,
            "notice": "需求POI样本，不代表官方总量。",
        }
    )