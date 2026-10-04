"""One bounded, on-demand POI search. No collector, persistence or analysis."""

from datetime import UTC, datetime
from math import isfinite

import httpx
from fastapi import HTTPException

from app.core.config import Settings
from app.models import Region
from app.schemas.data import AMapStationResult, SourceInfo, Station

AMAP_POI_URL = "https://restapi.amap.com/v5/place/text"


def optional_text(poi: dict, field: str) -> str | None:
    value = poi.get(field)
    return value if isinstance(value, str) and value else None


def query_stations(
    settings: Settings, region: Region, page: int, page_size: int
) -> AMapStationResult:
    key = settings.amap_webservice_key
    if not key or not key.get_secret_value().strip():
        raise HTTPException(
            503, "尚未配置高德 Web 服务 Key，请在 backend/.env 设置 AMAP_WEBSERVICE_KEY"
        )
    if page * page_size > 200:
        raise HTTPException(422, "同一组高德搜索参数最多获取200条，请缩小查询范围")
    params = {
        "key": key.get_secret_value(),
        "keywords": "充电站",
        "region": region.adcode,
        "city_limit": "true",
        "page_num": page,
        "page_size": page_size,
    }
    try:
        with httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as client:
            response = client.get(AMAP_POI_URL, params=params)
            response.raise_for_status()
            body = response.json()
    except httpx.TimeoutException:
        raise HTTPException(504, "高德地点查询超时，请稍后重试") from None
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "高德地点查询暂时不可用") from None
    if not isinstance(body, dict) or body.get("status") != "1":
        raise HTTPException(502, "高德未返回成功结果，请检查 Key 类型、服务权限和配额")
    pois = body.get("pois")
    if not isinstance(pois, list):
        raise HTTPException(502, "高德返回的地点数据格式异常")
    now = datetime.now(UTC)
    items = []
    skipped = 0
    for poi in pois[:page_size]:
        try:
            lng, lat = map(float, poi["location"].split(","))
            adcode = str(poi["adcode"])
            if not all(isfinite(v) for v in (lng, lat)) or not (
                -180 <= lng <= 180 and -90 <= lat <= 90
            ):
                raise ValueError
            if len(adcode) != 6 or not adcode.isdigit() or adcode[:4] != region.adcode[:4]:
                raise ValueError
            if not poi.get("id") or not poi.get("name"):
                raise ValueError

            items.append(
                Station(
                    id=str(poi["id"]),
                    poiId=str(poi["id"]),
                    name=str(poi["name"]),
                    address=optional_text(poi, "address"),
                    province=optional_text(poi, "pname") or "湖南省",
                    city=optional_text(poi, "cityname") or region.name,
                    district=optional_text(poi, "adname"),
                    adcode=adcode,
                    cityCode=region.adcode,
                    position=[lng, lat],
                    type=optional_text(poi, "type"),
                    piles=None,
                    source="高德地图地点搜索",
                    collectedAt=now,
                    simulated=False,
                )
            )
        except (KeyError, TypeError, ValueError, AttributeError):
            skipped += 1
    notice = "当前页为高德关键词检索结果，不代表市州充电站总量；搜索最多获取200条。桩数、快慢充比例与历史统计未提供。"
    return AMapStationResult(
        items=items,
        cityCode=region.adcode,
        page=page,
        pageSize=page_size,
        returnedCount=len(items),
        skippedCount=skipped,
        mayHaveMore=len(pois) >= page_size and (page + 1) * page_size <= 200,
        queriedAt=now,
        notice=notice,
        sourceInfo=SourceInfo(
            simulated=False,
            updatedAt=now.isoformat(),
            period="实时地点查询",
            label="高德地图 Web 服务 API",
            note=notice,
        ),
    )
