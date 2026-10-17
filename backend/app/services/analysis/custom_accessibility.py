"""Bounded interactive driving; shared OD cache, separate accounting and no snapshot writes."""

import math
import time
from contextlib import contextmanager
from datetime import timedelta

import httpx
from fastapi import HTTPException
from shapely.geometry import Point, shape
from sqlalchemy import select, text

from app.models import AnalysisBoundary, ChargingStation, PoiQuality, RoadODCache
from app.models.entities import utc_now
from app.services.analysis.job import digest
from app.services.analysis.road import ENDPOINT, distance_m, od_request, parse_route

VERSION = "custom-driving-v1"
TIPS_ENDPOINT = "https://restapi.amap.com/v3/assistant/inputtips"
TTL = timedelta(days=7)
NOTICE = "20km直线范围内筛选最近公共候选POI，再按真实驾车时间排序；不保证全库最快。非人口或面积覆盖率，开放与营业状态待核验。"


@contextmanager
def query_lock(session):
    # Dedicated connection survives ORM commits; also bounds calls across workers.
    with session.get_bind().connect() as connection:
        if connection.scalar(text("SELECT GET_LOCK('custom_accessibility_requests', 0)")) != 1:
            raise HTTPException(409, "已有地点查询正在执行，请稍后重试")
        try:
            yield
        finally:
            connection.execute(text("SELECT RELEASE_LOCK('custom_accessibility_requests')"))


def budget_key(kind):
    return digest(
        {"kind": "custom-query-budget", "service": kind, "dayUTC": utc_now().date().isoformat()}
    )


def usage(session, kind):
    row = session.get(RoadODCache, budget_key(kind))
    return int((row.response if row else {}).get("used", 0))


def policy(session, settings):
    enabled = settings.custom_accessibility_enabled and bool(settings.amap_webservice_key)
    return {
        "enabled": enabled,
        "dailyLimitEnabled": False,
        "drivingCallsToday": usage(session, "driving"),
        "placesCallsToday": usage(session, "places"),
        "providerQuotaKnown": False,
        "version": VERSION,
        "notice": NOTICE,
    }


def provider_get(session, settings, kind, endpoint, params, accounting=None):
    if not settings.custom_accessibility_enabled or not settings.amap_webservice_key:
        raise HTTPException(403, "真实查询尚未启用；请先确认账号配额和服务权限")
    key = budget_key(kind)
    row = session.get(RoadODCache, key)
    state = dict(row.response) if row else {}
    pause = 1.05 - (time.time() - float(state.get("lastAt", 0)))
    if pause > 0:
        time.sleep(pause)
    state.update(used=int(state.get("used", 0)) + 1, lastAt=time.time())
    if row:
        row.response = state
        row.fetched_at = utc_now()
    else:
        session.add(
            RoadODCache(
                key=key,
                request={"kind": kind, "dayUTC": utc_now().date().isoformat()},
                response=state,
                fetched_at=utc_now(),
            )
        )
    session.commit()  # Reserve before networking, including failed attempts. No retries.
    if accounting is not None:
        accounting["apiCalls"] += 1
    try:
        with httpx.Client(timeout=10, trust_env=False, follow_redirects=False) as client:
            response = client.get(
                endpoint, params={**params, "key": settings.amap_webservice_key.get_secret_value()}
            )
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "高德请求失败，本次调用已记录；未自动重试") from None


def route_with_geometry(body):
    result = parse_route(body)
    if result["status"] != "ok":
        return result
    try:
        path = min(
            body["route"]["paths"], key=lambda p: (float(p["duration"]), float(p["distance"]))
        )
        segments = []
        for step in path.get("steps", []):
            points = [
                [float(v) for v in pair.split(",")]
                for pair in step.get("polyline", "").split(";")
                if pair
            ]
            if any(
                len(p) != 2
                or not all(math.isfinite(v) for v in p)
                or not (-180 <= p[0] <= 180 and -90 <= p[1] <= 90)
                for p in points
            ):
                raise ValueError
            if len(points) >= 2:
                segments.append(points)
        if not segments:
            return {"status": "geometry_missing"}
        return {**result, "segments": segments}
    except (ValueError, TypeError, KeyError):
        return {"status": "invalid_response"}


def cache_route(session, origin, station):
    request = od_request(origin, station["position"])
    key = digest({"endpoint": ENDPOINT, "coordinateSystem": "GCJ-02", **request})
    row = session.get(RoadODCache, key)
    response = row.response if row and row.fetched_at >= utc_now() - TTL else {}
    complete = response.get("status") == "ok" and bool(response.get("segments"))
    negative = response.get("status") == "no_route"
    return request, key, row, response if complete or negative else None


def plan(session, query, settings):
    position = [query.origin.longitude, query.origin.latitude]
    boundaries = session.scalars(
        select(AnalysisBoundary).where(AnalysisBoundary.level == "city")
    ).all()
    if not boundaries:
        raise HTTPException(503, "湖南省市州边界尚未入库，无法验证选点范围")
    if not any(shape(boundary.geometry).covers(Point(position)) for boundary in boundaries):
        raise HTTPException(422, "请选择湖南省行政范围内的地点")
    dy = 20000 / 111000
    dx = dy / math.cos(math.radians(position[1]))
    rows = session.execute(
        select(ChargingStation, PoiQuality.run_id)
        .join(PoiQuality)
        .where(
            ChargingStation.source == "amap",
            PoiQuality.classification == "public_candidate",
            ChargingStation.longitude.between(position[0] - dx, position[0] + dx),
            ChargingStation.latitude.between(position[1] - dy, position[1] + dy),
        )
    ).all()
    stations = []
    for station, batch in rows:
        point = [float(station.longitude), float(station.latitude)]
        distance = distance_m(position, point)
        if distance <= 20000:
            stations.append(
                {
                    "id": station.id,
                    "poiId": station.poi_id,
                    "name": station.name,
                    "address": station.address,
                    "position": point,
                    "screeningDistanceM": round(distance),
                    "qualityBatch": batch,
                }
            )
    stations.sort(key=lambda s: (s["screeningDistanceM"], s["id"]))
    stations = stations[: query.candidate_count]
    missing = 0
    for station in stations:
        _, _, _, cached = cache_route(session, position, station)
        station.update(cached=cached is not None, route=cached)
        missing += cached is None
    plan_id = digest(
        {
            "origin": od_request(position, position)["origin"],
            "candidates": [
                {"id": s["id"], "position": s["position"], "batch": s["qualityBatch"]}
                for s in stations
            ],
        }
    )
    return {
        "origin": query.origin.model_dump(),
        "candidates": stations,
        "planId": plan_id,
        "requiredCalls": missing,
        "cacheHits": len(stations) - missing,
        "policy": policy(session, settings),
        "notice": NOTICE,
    }


def execute(session, query, settings):
    with query_lock(session):
        result = plan(session, query, settings)
        if query.max_api_calls and query.plan_id != result["planId"]:
            raise HTTPException(409, "候选数据发生变化，请重新估算后确认")
        if query.max_api_calls and result["requiredCalls"] > query.max_api_calls:
            raise HTTPException(409, "所需调用超过本次授权上限，请重新确认")
        accounting = {"apiCalls": 0}
        stopped = None
        position = [query.origin.longitude, query.origin.latitude]
        for station in result["candidates"]:
            if station["cached"] or not query.max_api_calls or stopped:
                continue
            request, key, row, _ = cache_route(session, position, station)
            try:
                body = provider_get(session, settings, "driving", ENDPOINT, request, accounting)
                response = route_with_geometry(body)
                station["route"] = response
                if response["status"] in {"ok", "no_route"}:
                    if row:
                        row.response = response
                        row.fetched_at = utc_now()
                    else:
                        session.add(
                            RoadODCache(
                                key=key, request=request, response=response, fetched_at=utc_now()
                            )
                        )
                    session.commit()
                elif response["status"] == "provider_error":
                    stopped = "高德服务拒绝请求，已停止后续调用；请检查权限或额度"
            except HTTPException as exc:
                stopped = exc.detail
        result["candidates"].sort(
            key=lambda s: (
                s.get("route", {}).get("durationSeconds", float("inf"))
                if isinstance(s.get("route"), dict) and s["route"].get("status") == "ok"
                else float("inf"),
                s["id"],
            )
        )
        result.update(
            apiCalls=accounting["apiCalls"],
            warning=stopped,
            policy=policy(session, settings),
            queriedAt=utc_now().isoformat() + "Z",
        )
        return result


def places(session, settings, keyword):
    params = {
        "keywords": keyword,
        "city": "430000",
        "citylimit": "true",
        "datatype": "all",
        "output": "JSON",
    }
    key = digest({"endpoint": TIPS_ENDPOINT, **params})
    with query_lock(session):
        row = session.get(RoadODCache, key)
        if row and row.fetched_at >= utc_now() - timedelta(hours=6):
            return {"items": row.response["items"], "cached": True}
        body = provider_get(session, settings, "places", TIPS_ENDPOINT, params)
        if not isinstance(body, dict) or body.get("status") != "1":
            raise HTTPException(502, "高德地点提示不可用，请检查权限或额度")
        items = []
        for tip in body.get("tips", []):
            try:
                point = [float(v) for v in tip["location"].split(",")]
                if len(point) != 2 or not all(math.isfinite(v) for v in point):
                    continue
                items.append(
                    {
                        "name": str(tip["name"])[:120],
                        "address": str(tip.get("district", ""))
                        + (tip.get("address") if isinstance(tip.get("address"), str) else ""),
                        "position": point,
                    }
                )
            except (ValueError, TypeError, KeyError, AttributeError):
                continue
        response = {"items": items[:10]}
        if row:
            row.response, row.fetched_at = response, utc_now()
        else:
            session.add(
                RoadODCache(key=key, request=params, response=response, fetched_at=utc_now())
            )
        session.commit()
        return {**response, "cached": False}
