"""Persisted actual OD observations; reading never requests provider routes."""

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import load_only

from app.api.dependencies import SessionDep
from app.models import RoadAccessibilityRun
from app.schemas.common import APIResponse
from app.services.analysis.road import VERSION

router = APIRouter(prefix="/api/v1/analysis/accessibility", tags=["真实道路可达性"])


@router.get("/latest", response_model=APIResponse[dict])
def latest(
    session: SessionDep,
    city_code: str | None = Query(None, pattern=r"^43\d{2}00$"),
    adcode: str | None = Query(None, pattern=r"^43\d{4}$"),
    classification: str = "public_candidate",
    review_status: str | None = None,
    needs_review: bool | None = None,
    batch: str | None = None,
):
    if classification != "public_candidate" or review_status or needs_review or batch:
        raise HTTPException(404, "该治理口径没有真实道路快照，不回退公共候选结果")
    run_id = session.scalar(
        select(RoadAccessibilityRun.id)
        .where(
            RoadAccessibilityRun.algorithm_version == VERSION,
            RoadAccessibilityRun.status.in_(
                ["completed", "partial", "quota_stopped", "provider_stopped"]
            ),
        )
        .order_by(RoadAccessibilityRun.updated_at.desc())
        .limit(1)
    )
    run = (
        session.scalar(
            select(RoadAccessibilityRun)
            .where(RoadAccessibilityRun.id == run_id)
            .options(
                load_only(
                    RoadAccessibilityRun.id,
                    RoadAccessibilityRun.status,
                    RoadAccessibilityRun.algorithm_version,
                    RoadAccessibilityRun.input_hash,
                    RoadAccessibilityRun.parameters,
                    RoadAccessibilityRun.result,
                    RoadAccessibilityRun.api_calls,
                    RoadAccessibilityRun.cache_hits,
                    RoadAccessibilityRun.updated_at,
                )
            )
        )
        if run_id
        else None
    )
    if run is None or not run.result:
        raise HTTPException(404, "尚无真实道路计算结果，不使用直线缓冲代替")
    regions = [
        r
        for r in run.result["regions"]
        if (not city_code or r["cityCode"] == city_code) and (not adcode or r["adcode"] == adcode)
    ]
    if (adcode or city_code) and not regions:
        raise HTTPException(422, "行政范围与道路计算区县目录不匹配")
    resolved = [r for r in regions if r["complete"]]
    measured = [r for r in resolved if r["durationSeconds"] is not None]
    return APIResponse(
        data={
            "id": run.id,
            "status": run.status,
            "algorithmVersion": run.algorithm_version,
            "inputHash": run.input_hash,
            "parameters": run.parameters,
            "updatedAt": run.updated_at.isoformat() + "Z",
            "source": "高德路径规划API",
            "apiCalls": run.api_calls,
            "cacheHits": run.cache_hits,
            "qualityBatches": run.result["qualityBatches"],
            "regions": regions,
            "originCount": len(regions),
            "resolvedOriginCount": len(resolved),
            "thresholdPercent": {
                str(m): 100 * sum(r["thresholdReached"][str(m)] for r in resolved) / len(resolved)
                if resolved
                else None
                for m in [5, 10, 15]
            },
            "meanNearestDurationSeconds": sum(r["durationSeconds"] for r in measured)
            / len(measured)
            if measured
            else None,
            "meanNearestDistanceM": sum(r["distanceM"] for r in measured) / len(measured)
            if measured
            else None,
            "meanDenominator": len(measured),
            "ratioDenominator": len(resolved),
            "notice": run.result["notice"],
        }
    )
