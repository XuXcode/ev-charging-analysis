"""Read imported evidence without synthesizing complete statistics or derived trends."""

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.dependencies import SessionDep
from app.models import OfficialStatistic, PublicStatistic
from app.schemas.common import APIResponse
from app.services.statistics_import import METRICS

router = APIRouter(prefix="/api/v1/statistics", tags=["公开统计来源"])


@router.get("/public", response_model=APIResponse[dict])
def public_statistics(
    session: SessionDep,
    adcode: str | None = Query(None, pattern=r"^43\d{4}$"),
    year: int | None = Query(None, ge=1900, le=9999),
    metric: str | None = Query(None, max_length=50),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
):
    return read_statistics(session, PublicStatistic, adcode, year, metric, page, page_size)


@router.get("/official", response_model=APIResponse[dict])
def official_statistics(
    session: SessionDep,
    adcode: str | None = Query(None, pattern=r"^43\d{4}$"),
    year: int | None = Query(None, ge=1900, le=9999),
    metric: str | None = Query(None, max_length=50),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
):
    return read_statistics(session, OfficialStatistic, adcode, year, metric, page, page_size)


def read_statistics(session, model, adcode, year, metric, page, page_size):
    conditions = []
    if adcode:
        conditions.append(model.region_adcode == adcode)
    if year:
        conditions.append(model.year == year)
    if metric:
        conditions.append(model.metric == metric)
    total = session.scalar(select(func.count()).select_from(model).where(*conditions))
    rows = session.scalars(
        select(model)
        .where(*conditions)
        .order_by(model.year.desc(), model.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return APIResponse(
        data={
            "items": [
                {
                    "id": row.id,
                    "adcode": row.region_adcode,
                    "year": row.year,
                    "metric": row.metric,
                    "label": METRICS[row.metric][0],
                    "value": int(row.value),
                    "unit": row.unit,
                    "sourceName": row.source_name,
                    "sourceUrl": row.source_url,
                    "sourceKind": row.source_kind,
                    "scopeDescription": row.scope_description,
                    "fileName": row.file_name,
                    "fileSha256": row.file_sha256,
                    "recordHash": row.record_hash,
                    "rowNumber": row.row_number,
                    "importedAt": row.imported_at.isoformat() + "Z",
                    "updatedAt": getattr(row, "updated_at", row.imported_at).isoformat() + "Z",
                }
                for row in rows
            ],
            "total": total,
            "page": page,
            "pageSize": page_size,
            "notice": "来源类别由导入者按原文件标注，需核对原文及统计口径；不同口径不自动合并，不补齐缺失指标。",
        }
    )
