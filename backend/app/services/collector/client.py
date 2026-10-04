"""Bounded AMap transport. Never log URLs, credentials or upstream error text."""

import logging
import re
import time
from dataclasses import dataclass
from math import isfinite

import httpx

from app.core.config import Settings

POI_URL = "https://restapi.amap.com/v5/place/text"
DISTRICT_URL = "https://restapi.amap.com/v3/config/district"
POLYGON_URL = "https://restapi.amap.com/v5/place/polygon"
logger = logging.getLogger("collector")


class CollectionError(Exception):
    """Only safe, locally defined messages may enter logs/checkpoints."""


@dataclass(frozen=True)
class Response:
    body: dict
    attempts: int


class AMapClient:
    def __init__(
        self,
        settings: Settings,
        *,
        interval=1.0,
        retries=3,
        transport=None,
        sleep=time.sleep,
        clock=time.monotonic,
    ):
        key = settings.amap_webservice_key
        if not key or not key.get_secret_value().strip():
            raise CollectionError("尚未配置 AMAP_WEBSERVICE_KEY；未发起采集请求")
        if not isfinite(interval) or interval < 0.2 or not 0 <= retries <= 5:
            raise CollectionError("请求间隔至少0.2秒；重试次数必须为0–5")
        self._key = key.get_secret_value().strip()
        self.interval, self.retries = interval, retries
        self.sleep, self.clock = sleep, clock
        self.last_request = None
        self.http = httpx.Client(
            timeout=20, follow_redirects=False, trust_env=False, transport=transport
        )

    def close(self):
        self.http.close()

    def request(self, url, params):
        for attempt in range(self.retries + 1):
            if self.last_request is not None:
                self.sleep(max(0, self.interval - (self.clock() - self.last_request)))
            self.last_request = self.clock()
            retry = False
            message = "高德请求失败"
            try:
                response = self.http.get(url, params={**params, "key": self._key})
                if response.status_code == 429 or response.status_code >= 500:
                    retry, message = True, "高德限流或服务暂时不可用"
                elif response.is_error:
                    raise CollectionError("高德 HTTP 请求被拒绝")
                else:
                    body = response.json()
                    if not isinstance(body, dict):
                        raise ValueError
                    if str(body.get("status")) == "1":
                        return Response(body, attempt + 1)
                    code = str(body.get("infocode", ""))
                    code = code if re.fullmatch(r"\d{5}", code) else "unknown"
                    retry = code in {"10004", "10016", "10019", "10020", "10021"}
                    message = f"高德拒绝请求（infocode={code}）；请检查权限、配额及Key类型"
            except (httpx.HTTPError, ValueError):
                retry, message = True, "高德网络超时或响应格式异常"
            if not retry or attempt == self.retries:
                raise CollectionError(message) from None
            logger.warning("request retry=%d reason=%s", attempt + 1, message)
            self.sleep(min(30, 2**attempt))
        raise CollectionError("重试次数耗尽")

    def districts(self, city_code):
        response = self.request(
            DISTRICT_URL,
            {
                "keywords": city_code,
                "subdistrict": 1,
                "extensions": "base",
            },
        )
        roots = response.body.get("districts")
        if not isinstance(roots, list):
            raise CollectionError("行政区响应缺少 districts")
        root = next(
            (r for r in roots if isinstance(r, dict) and r.get("adcode") == city_code), None
        )
        if root is None:
            raise CollectionError("行政区响应与请求市州不一致")
        children = root.get("districts")
        if not isinstance(children, list) or not children:
            raise CollectionError("未返回区县清单，停止该市州以避免错误地宣称完整采集")
        scopes = []
        for child in children:
            if not isinstance(child, dict):
                raise CollectionError("区县元数据格式异常")
            code = str(child.get("adcode", ""))
            if (
                not re.fullmatch(r"\d{6}", code)
                or code[:4] != city_code[:4]
                or child.get("level") != "district"
                or not child.get("name")
            ):
                raise CollectionError("区县编码或级别与市州不一致")
            scopes.append({"adcode": code, "name": child["name"], "cityCode": city_code})
        return sorted({s["adcode"]: s for s in scopes}.values(), key=lambda s: s["adcode"])

    def pois(self, adcode, page):
        if not 1 <= page <= 8:
            raise CollectionError("同一行政区搜索最多8页，每页25条")
        response = self.request(
            POI_URL,
            {
                "keywords": "充电站",
                "region": adcode,
                "city_limit": "true",
                "page_num": page,
                "page_size": 25,
            },
        )
        pois = response.body.get("pois")
        if not isinstance(pois, list) or len(pois) > 25:
            raise CollectionError("POI 响应列表格式或页大小异常")
        return pois, response.attempts

    def polygon_pois(self, bounds, page):
        """One bounded rectangular shard; caller validates source district and checkpoints."""
        west, south, east, north = bounds
        if (
            not all(isfinite(value) for value in bounds)
            or not (108 < west < east < 115 and 24 < south < north < 31)
            or not 1 <= page <= 8
        ):
            raise CollectionError("湖南网格范围或分页参数无效")
        response = self.request(
            POLYGON_URL,
            {
                "polygon": f"{west:.6f},{north:.6f}|{east:.6f},{south:.6f}",
                "keywords": "充电站",
                "types": "011100",
                "page_size": 25,
                "page_num": page,
            },
        )
        pois = response.body.get("pois")
        if not isinstance(pois, list) or len(pois) > 25:
            raise CollectionError("网格POI响应列表格式或页大小异常")
        return pois, response.attempts
