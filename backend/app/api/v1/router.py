from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Query

from app.api.dependencies import DataServiceDep, SessionDep
from app.models import CollectionRun
from app.schemas.common import APIResponse, ErrorResponse
from app.schemas.data import (
    City,
    Overview,
    RankingResult,
    RegionsResult,
    SourcesResult,
    StationPage,
    TrendResult,
)
from app.schemas.filters import PoiClassification, ReviewStatus
from app.services.collector.runner import collection_summary, report_run
from app.services.dashboard import dashboard_payload
from app.utils.bbox import parse_bbox

Adcode = Annotated[str, Path(pattern=r"^\d{6}$")]
router = APIRouter(
    prefix="/api/v1",
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@router.get(
    "/overview",
    response_model=APIResponse[Overview],
    tags=["统计快照"],
)
def overview(service: DataServiceDep):
    return APIResponse(data=service.overview())


@router.get("/regions", response_model=APIResponse[RegionsResult], tags=["行政区"])
def regions(service: DataServiceDep):
    return APIResponse(data=RegionsResult(items=service.cities(), sourceInfo=service.source_info()))


@router.get("/regions/{adcode}", response_model=APIResponse[City], tags=["行政区"])
def region(adcode: Adcode, service: DataServiceDep):
    return APIResponse(data=service.region_detail(adcode))


@router.get("/rankings", response_model=APIResponse[RankingResult], tags=["统计快照"])
def rankings(
    service: DataServiceDep,
    metric: Literal["station_count", "public_charger_count", "density"] = "station_count",
):
    attribute, unit = {
        "station_count": ("stations", "座"),
        "public_charger_count": ("piles", "个"),
        "density": ("density", "座 / 百平方公里"),
    }[metric]
    items = sorted(
        service.cities(),
        key=lambda city: (
            getattr(city, attribute) is None,
            -(getattr(city, attribute) or 0),
            city.code,
        ),
    )
    return APIResponse(
        data=RankingResult(metric=metric, unit=unit, items=items, sourceInfo=service.source_info())
    )


@router.get("/trends", response_model=APIResponse[TrendResult], tags=["统计快照"])
def trends(service: DataServiceDep, adcode: str = Query("430000", pattern=r"^\d{6}$")):
    return APIResponse(
        data=TrendResult(
            adcode=adcode,
            items=service.trends(adcode),
            sourceInfo=service.source_info(service.snapshots.latest_date(adcode)),
        )
    )


@router.get(
    "/stations",
    response_model=APIResponse[StationPage],
    tags=["站点清单"],
    summary="按行政区、视野与治理条件读取真实POI样本",
    description="分类只表示证据线索；返回范围内分页站点与治理来源，不推算官方设施总量。",
)
def stations(
    service: DataServiceDep,
    city: str | None = Query(
        None, min_length=1, max_length=100, description="市州名称、简称或六位行政编码"
    ),
    adcode: str | None = Query(None, pattern=r"^\d{6}$"),
    bbox: str | None = Query(
        None, max_length=150, description="west,south,east,north，站点原始经纬度坐标"
    ),
    keyword: str | None = Query(
        None,
        min_length=1,
        max_length=100,
        description="名称、地址或POI ID字面量包含匹配；与行政区、分类、复核及批次取交集，%/_不作为通配符",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    real_only: bool = Query(True, description="默认仅湖南真实高德站点；false用于旧演示数据联调"),
    classification: PoiClassification | None = Query(
        None, description="治理分类，公共候选不证明营业或公共开放"
    ),
    review_status: ReviewStatus | None = Query(None, description="人工复核状态"),
    needs_review: bool | None = Query(
        None, description="规则识别的待复核线索；独立于人工复核状态，可与类别取交集，不代表已判无效"
    ),
    batch: str | None = Query(
        None,
        pattern=r"^[a-f0-9]{32}$",
        description="站点当前治理证据关联采集批次；不是历史站点还原",
    ),
):
    selected = service.regions.get(adcode) if adcode else None
    if batch and service.stations.session.get(CollectionRun, batch) is None:
        raise HTTPException(404, "未找到该采集批次")
    exact_adcode = None
    if adcode and selected is None:
        # Collector district scopes live in its manifest; counties need no fabricated Region.
        parent = service.regions.get(adcode[:4] + "00")
        if adcode.endswith("00") or parent is None or parent.level != "city":
            raise HTTPException(404, "未找到该行政区")
        selected, exact_adcode = parent, adcode
    if city:
        city_region = (
            service.regions.get(city) if city.isdigit() else service.regions.by_city_name(city)
        )
        if city_region is None or city_region.level != "city":
            raise HTTPException(404, "未找到该市州")
        if selected and selected.adcode[:4] != city_region.adcode[:4]:
            raise HTTPException(422, "city 与 adcode 不属于同一市州")
        selected = selected or city_region
    rows, total = service.stations.page(
        region=selected,
        keyword=keyword,
        bbox=parse_bbox(bbox),
        page=page,
        page_size=page_size,
        real_only=real_only,
        exact_adcode=exact_adcode,
        classification=classification,
        review_status=review_status,
        needs_review=needs_review,
        batch=batch,
    )
    service.station_quality = service.stations.quality_for(rows)
    return APIResponse(
        data=StationPage(
            items=[service.station_view(row) for row in rows],
            total=total,
            page=page,
            pageSize=page_size,
            sourceInfo=service.station_source_info(real_only=real_only),
        )
    )


@router.get("/collection/summary", response_model=APIResponse[dict], tags=["采集记录"])
def collected_summary(session: SessionDep):
    return APIResponse(data=collection_summary(session))


@router.get("/collection/runs/{run_id}", response_model=APIResponse[dict], tags=["采集记录"])
def collection_run(session: SessionDep, run_id: str = Path(pattern=r"^[a-f0-9]{32}$")):
    run = session.get(CollectionRun, run_id)
    if run is None:
        raise HTTPException(404, "未找到采集批次")
    return APIResponse(data=report_run(session, run))


@router.get("/data-sources", response_model=APIResponse[SourcesResult], tags=["数据来源"])
def data_sources(service: DataServiceDep):
    return APIResponse(
        data=SourcesResult(items=service.data_sources(), sourceInfo=service.source_info())
    )


@router.get("/dashboard", response_model=APIResponse[dict], tags=["前端兼容"])
def dashboard(service: DataServiceDep):
    """现有 Vue 总览的聚合读取适配；不执行空间分析。"""
    return APIResponse(data=dashboard_payload(service))


@router.get("/cities/{adcode}/districts", response_model=APIResponse[dict], tags=["前端兼容"])
def districts(adcode: Adcode, service: DataServiceDep):
    service.require_region(adcode)
    return APIResponse(data={"status": "pending", "features": [], "message": "区县边界尚未接入"})
