from fastapi import APIRouter, HTTPException, Query, Request

from app.api.dependencies import DataServiceDep
from app.schemas.common import APIResponse, ErrorResponse
from app.schemas.data import AMapStationResult
from app.services.amap import query_stations

router = APIRouter(
    prefix="/api/v1/amap",
    tags=["高德地点查询"],
    responses={
        422: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        504: {"model": ErrorResponse},
    },
)


@router.get("/status", response_model=APIResponse[dict])
def status(request: Request):
    key = request.app.state.settings.amap_webservice_key
    return APIResponse(data={"configured": bool(key and key.get_secret_value().strip())})


@router.get("/stations", response_model=APIResponse[AMapStationResult])
def stations(
    request: Request,
    service: DataServiceDep,
    city: str = Query(..., pattern=r"^\d{6}$"),
    page: int = Query(1, ge=1, le=200),
    page_size: int = Query(25, ge=1, le=25),
):
    region = service.require_region(city)
    if region.level != "city" or region.parent_adcode != "430000":
        raise HTTPException(422, "请选择湖南省市州行政编码")
    return APIResponse(data=query_stations(request.app.state.settings, region, page, page_size))
