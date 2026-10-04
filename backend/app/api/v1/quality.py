from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.api.dependencies import SessionDep
from app.models import (
    AnalysisScopeQuality,
    ChargingStation,
    CollectionRun,
    PoiQuality,
    PoiReviewEvent,
)
from app.schemas.common import APIResponse
from app.schemas.filters import PoiClassification, ReviewStatus
from app.utils.bbox import parse_bbox

router = APIRouter(prefix="/api/v1/quality", tags=["数据治理"])


@router.get(
    "/pois",
    response_model=APIResponse[dict],
    summary="查询保守分类与人工复核证据",
    description="默认分页读取复核线索；all_records=true查看全部保留记录。类别、状态、行政区、关键词、批次和bbox取交集。公共候选不代表已确认营业，不自动删除任何原始POI。",
)
def quality_pois(
    session: SessionDep,
    classification: PoiClassification | None = None,
    review_status: ReviewStatus | None = None,
    needs_review: bool | None = True,
    all_records: bool = False,
    adcode: str | None = Query(None, pattern=r"^43\d{4}$"),
    keyword: str | None = Query(None, max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    batch: str | None = Query(None, pattern=r"^[a-f0-9]{32}$", description="治理证据关联批次"),
    bbox: str | None = Query(None, max_length=150, description="GCJ-02 west,south,east,north"),
):
    conditions = [ChargingStation.source == "amap"]
    if classification:
        conditions.append(PoiQuality.classification == classification)
    if review_status:
        conditions.append(PoiQuality.review_status == review_status)
    if batch:
        if session.get(CollectionRun, batch) is None:
            raise HTTPException(404, "未找到该采集批次")
        conditions.append(PoiQuality.run_id == batch)
    bounds = parse_bbox(bbox)
    if bounds:
        west, south, east, north = bounds
        conditions.extend(
            [
                ChargingStation.longitude.between(west, east),
                ChargingStation.latitude.between(south, north),
            ]
        )
    if needs_review is not None and not all_records:
        conditions.append(PoiQuality.needs_review == needs_review)
    if adcode:
        prefix = (
            adcode[:2] if adcode == "430000" else adcode[:4] if adcode.endswith("00") else adcode
        )
        conditions.append(ChargingStation.adcode.startswith(prefix, autoescape=True))
    if keyword:
        conditions.append(ChargingStation.name.contains(keyword, autoescape=True))
    total = session.scalar(
        select(func.count()).select_from(PoiQuality).join(ChargingStation).where(*conditions)
    )
    rows = session.execute(
        select(
            PoiQuality,
            ChargingStation.poi_id,
            ChargingStation.name,
            ChargingStation.adcode,
            AnalysisScopeQuality.completeness_warning,
        )
        .select_from(PoiQuality)
        .join(ChargingStation)
        .outerjoin(AnalysisScopeQuality, ChargingStation.adcode == AnalysisScopeQuality.adcode)
        .where(*conditions)
        .order_by(PoiQuality.station_id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [
        {
            "stationId": q.station_id,
            "poiId": poi_id,
            "name": name,
            "adcode": code,
            "classification": q.classification,
            "confidence": q.confidence,
            "reasons": q.reasons,
            "evidence": q.evidence,
            "reviewStatus": q.review_status,
            "reviewNote": q.review_note,
            "reviewedAt": q.reviewed_at.isoformat() + "Z" if q.reviewed_at else None,
            "needsReview": q.needs_review,
            "completenessWarning": bool(warning),
            "rulesVersion": q.rules_version,
            "runId": q.run_id,
        }
        for q, poi_id, name, code, warning in rows
    ]
    return APIResponse(
        data={
            "items": items,
            "total": total,
            "page": page,
            "pageSize": page_size,
            "notice": "保守分类仅提供复核线索，不证明公共开放或真实营业状态；未删除任何样本。",
        }
    )


@router.get("/pois/{station_id}/reviews", response_model=APIResponse[dict])
def review_events(session: SessionDep, station_id: int):
    if session.get(ChargingStation, station_id) is None:
        raise HTTPException(404, "站点不存在")
    events = session.scalars(
        select(PoiReviewEvent)
        .where(PoiReviewEvent.station_id == station_id)
        .order_by(PoiReviewEvent.id.desc())
        .limit(100)
    )
    return APIResponse(
        data={
            "items": [
                {
                    "id": e.id,
                    "kind": e.kind,
                    "actor": e.actor,
                    "before": e.before,
                    "after": e.after,
                    "evidence": e.evidence,
                    "reason": e.reason,
                    "createdAt": e.created_at.isoformat() + "Z",
                    "eventHash": e.event_hash,
                }
                for e in events
            ],
            "notice": "追加式台账；自动分流不等于人工确认营业或公共开放。",
        }
    )
