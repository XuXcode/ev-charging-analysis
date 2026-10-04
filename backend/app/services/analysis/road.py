"""Bounded real driving queries, frozen evidence and restartable accounting."""

import argparse
import logging
import math
import time
import uuid
from datetime import timedelta

import httpx
from shapely import STRtree, make_valid
from shapely.geometry import Point, box, shape
from sqlalchemy import select, text

from app.core.config import Settings
from app.db.session import create_db_engine, create_session_factory
from app.models import (
    AnalysisBoundary,
    AnalysisScopeQuality,
    ChargingStation,
    PoiQuality,
    RoadAccessibilityRun,
    RoadODCache,
)
from app.models.entities import utc_now
from app.services.analysis.job import digest

ENDPOINT = "https://restapi.amap.com/v3/direction/driving"
VERSION = "road-county-representative-v1"
NOTICE = (
    "区县几何内部代表点到附近3个公共候选POI的驾车估计，非人口覆盖、面积覆盖或等时圈；"
    "候选最短时间不保证全库最近，POI营业和公共开放尚未认证。路网及路况随查询时间变化。"
)


def frozen_digest(value):
    """MySQL JSON may reserialize doubles; pin numeric hash precision explicitly."""

    def normalized(item):
        if isinstance(item, bool) or item is None:
            return item
        if isinstance(item, (int, float)):
            return format(item, ".8f")
        if isinstance(item, list):
            return [normalized(v) for v in item]
        if isinstance(item, dict):
            return {k: normalized(v) for k, v in item.items()}
        return item

    return digest(normalized(value))


def distance_m(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 6371008.8 * 2 * math.asin(min(1, math.sqrt(h)))


def od_request(origin, destination):
    def coordinate(point):
        if len(point) != 2 or not all(math.isfinite(float(v)) for v in point):
            raise ValueError("路线坐标非法")
        if not (-180 <= float(point[0]) <= 180 and -90 <= float(point[1]) <= 90):
            raise ValueError("路线坐标越界")
        return ",".join(f"{float(v):.6f}" for v in point)

    return {
        "origin": coordinate(origin),
        "destination": coordinate(destination),
        "strategy": "0",
        "extensions": "base",
        "output": "JSON",
    }


def parse_route(body):
    if not isinstance(body, dict) or body.get("status") != "1":
        code = str(body.get("infocode", "unknown")) if isinstance(body, dict) else "unknown"
        # Never echo provider messages or request URLs: they can contain credentials.
        return {"status": "provider_error", "code": code if code.isdigit() else "unknown"}
    route = body.get("route")
    if not isinstance(route, dict):
        return {"status": "invalid_response"}
    paths = route.get("paths", [])
    if not isinstance(paths, list) or not paths:
        return {"status": "no_route"}
    try:
        candidates = [(float(p["duration"]), float(p["distance"])) for p in paths]
        if not all(math.isfinite(v) and v >= 0 for pair in candidates for v in pair):
            raise ValueError
        duration, distance = min(candidates)
    except (ValueError, TypeError, KeyError, OverflowError):
        return {"status": "invalid_response"}
    return {"status": "ok", "durationSeconds": duration, "distanceM": distance}


def create_run(session, max_calls=500):
    if not 1 <= max_calls <= 500:
        raise ValueError("本轮调用上限必须介于1和500")
    rows = session.execute(
        select(
            ChargingStation.id,
            ChargingStation.poi_id,
            ChargingStation.longitude,
            ChargingStation.latitude,
            PoiQuality.run_id,
        )
        .join(PoiQuality)
        .where(ChargingStation.source == "amap", PoiQuality.classification == "public_candidate")
        .order_by(ChargingStation.id)
    ).all()
    if not rows:
        raise ValueError("无公共候选真实POI，不创建路线任务")
    stations = [
        {
            "id": r.id,
            "poiId": r.poi_id,
            "position": [float(r.longitude), float(r.latitude)],
            "qualityBatch": r.run_id,
        }
        for r in rows
    ]
    tree = STRtree([Point(s["position"]) for s in stations])
    quality = {
        q.adcode: q.completeness_warning for q in session.scalars(select(AnalysisScopeQuality))
    }
    origins, tasks = [], []
    for boundary in session.scalars(
        select(AnalysisBoundary)
        .where(AnalysisBoundary.level == "district")
        .order_by(AnalysisBoundary.adcode)
    ):
        geometry = make_valid(shape(boundary.geometry))
        point = geometry.representative_point()
        position = [point.x, point.y]
        # Spatial bounding box first; exact spherical radius then nearest three.
        lat_delta = 20000 / 111000
        lon_delta = lat_delta / math.cos(math.radians(point.y))
        indices = tree.query(
            box(point.x - lon_delta, point.y - lat_delta, point.x + lon_delta, point.y + lat_delta)
        )
        candidates = sorted(
            (
                (distance_m(position, stations[int(i)]["position"]), stations[int(i)])
                for i in indices
            ),
            key=lambda pair: (pair[0], pair[1]["id"]),
        )
        candidates = [pair for pair in candidates if pair[0] <= 20000][:3]
        origins.append(
            {
                "adcode": boundary.adcode,
                "cityCode": boundary.city_code,
                "name": boundary.name,
                "position": position,
                "boundaryHash": boundary.content_hash,
                "completenessWarning": quality.get(boundary.adcode, True),
                "candidateCount": len(candidates),
            }
        )
        for straight, station in candidates:
            request = od_request(position, station["position"])
            tasks.append(
                {
                    "adcode": boundary.adcode,
                    "poiId": station["poiId"],
                    "stationId": station["id"],
                    "straightDistanceM": straight,
                    "request": request,
                    "cacheKey": digest(
                        {"endpoint": ENDPOINT, "coordinateSystem": "GCJ-02", **request}
                    ),
                }
            )
    inputs = {"origins": origins, "tasks": tasks, "stations": stations}
    run = RoadAccessibilityRun(
        id=uuid.uuid4().hex,
        status="prepared",
        algorithm_version=VERSION,
        input_hash=frozen_digest(inputs),
        inputs=inputs,
        parameters={
            "maxCalls": max_calls,
            "candidateRadiusM": 20000,
            "candidateCount": 3,
            "originMethod": "geometry_representative_point",
            "coordinateSystem": "GCJ-02",
            "strategy": 0,
            "endpoint": ENDPOINT,
            "cacheTtlDays": 7,
            "minimumIntervalSeconds": 1,
            "maxAttemptsPerOD": 3,
            "thresholdMinutes": [5, 10, 15],
            "notice": NOTICE,
        },
        progress={},
        result={},
        api_calls=0,
        cache_hits=0,
    )
    session.add(run)
    session.commit()
    return run


def aggregate(run):
    regions = []
    for origin in run.inputs["origins"]:
        tasks = [t for t in run.inputs["tasks"] if t["adcode"] == origin["adcode"]]
        observations = [run.progress.get(t["cacheKey"], {}) for t in tasks]
        ok = [(o, t) for o, t in zip(observations, tasks, strict=True) if o.get("status") == "ok"]
        complete = bool(tasks) and all(o.get("status") in {"ok", "no_route"} for o in observations)
        best = min(ok, key=lambda pair: pair[0]["durationSeconds"]) if ok else None
        regions.append(
            {
                **origin,
                "complete": complete,
                "successfulOD": len(ok),
                "durationSeconds": best[0]["durationSeconds"] if best else None,
                "distanceM": best[0]["distanceM"] if best else None,
                "nearestCandidatePoiId": best[1]["poiId"] if best else None,
                "thresholdReached": {
                    str(m): bool(best and best[0]["durationSeconds"] <= m * 60)
                    if complete
                    else None
                    for m in [5, 10, 15]
                },
            }
        )
    resolved = [r for r in regions if r["complete"]]
    measured = [r for r in resolved if r["durationSeconds"] is not None]
    return {
        "regions": regions,
        "originCount": len(regions),
        "resolvedOriginCount": len(resolved),
        "thresholdPercent": {
            str(m): 100 * sum(r["thresholdReached"][str(m)] for r in resolved) / len(resolved)
            if resolved
            else None
            for m in [5, 10, 15]
        },
        "meanNearestDurationSeconds": sum(r["durationSeconds"] for r in measured) / len(measured)
        if measured
        else None,
        "meanNearestDistanceM": sum(r["distanceM"] for r in measured) / len(measured)
        if measured
        else None,
        "meanDenominator": len(measured),
        "ratioDenominator": len(resolved),
        "notice": NOTICE,
        "qualityBatches": sorted({s["qualityBatch"] for s in run.inputs["stations"]}),
    }


def execute(session, run, key, client=None):
    if run.algorithm_version != VERSION or frozen_digest(run.inputs) != run.input_hash:
        raise ValueError("冻结输入或算法版本不一致")
    lock_connection = session.get_bind().engine.connect()
    lock_name = "ev_road_" + digest(str(lock_connection.engine.url.database))[:32]
    if lock_connection.scalar(text("SELECT GET_LOCK(:name, 0)"), {"name": lock_name}) != 1:
        lock_connection.close()
        raise ValueError("已有道路计算任务正在执行")
    owned = client is None
    client = client or httpx.Client(timeout=20, trust_env=False, follow_redirects=False)
    last_call = 0.0
    transport_failures = 0
    try:
        run.status = "running"
        session.commit()
        for task in run.inputs["tasks"]:
            cache_key = task["cacheKey"]
            state = dict(run.progress.get(cache_key, {}))
            if state.get("status") in {"ok", "no_route"}:
                continue
            cached = session.get(RoadODCache, cache_key)
            if cached and cached.fetched_at >= utc_now() - timedelta(
                days=run.parameters["cacheTtlDays"]
            ):
                run.progress = {
                    **run.progress,
                    cache_key: {
                        **cached.response,
                        "attempts": state.get("attempts", 0),
                        "cacheHit": True,
                        "observedAt": cached.fetched_at.isoformat() + "Z",
                    },
                }
                run.cache_hits += 1
                session.commit()
                continue
            while state.get("attempts", 0) < run.parameters["maxAttemptsPerOD"]:
                if run.api_calls >= run.parameters["maxCalls"]:
                    run.status = "quota_stopped"
                    run.result = aggregate(run)
                    run.updated_at = utc_now()
                    session.commit()
                    return
                time.sleep(
                    max(
                        0, run.parameters["minimumIntervalSeconds"] - (time.monotonic() - last_call)
                    )
                )
                # Commit reservation BEFORE network: crash may waste a slot, cannot overspend.
                state = {"status": "reserved", "attempts": state.get("attempts", 0) + 1}
                run.api_calls += 1
                run.progress = {**run.progress, cache_key: state}
                run.updated_at = utc_now()
                session.commit()
                last_call = time.monotonic()
                try:
                    response = client.get(ENDPOINT, params={**task["request"], "key": key})
                    response.raise_for_status()
                    evidence = parse_route(response.json())
                except (httpx.HTTPError, ValueError):
                    evidence = {"status": "transport_error"}
                transport_failures = (
                    transport_failures + 1 if evidence["status"] == "transport_error" else 0
                )
                state = {
                    **state,
                    **evidence,
                    "observedAt": utc_now().isoformat() + "Z",
                    "cacheHit": False,
                }
                run.progress = {**run.progress, cache_key: state}
                if evidence["status"] in {"ok", "no_route"}:
                    if cached:
                        cached.response, cached.fetched_at = evidence, utc_now()
                    else:
                        session.add(
                            RoadODCache(key=cache_key, request=task["request"], response=evidence)
                        )
                session.commit()
                if transport_failures >= 3:
                    run.status = "transport_stopped"
                    run.result = aggregate(run)
                    session.commit()
                    return
                if evidence["status"] in {"ok", "no_route"}:
                    break
                if evidence.get("code") in {
                    "10001",
                    "10003",
                    "10004",
                    "10009",
                    "10010",
                    "10013",
                    "10014",
                    "10016",
                    "10044",
                }:
                    run.status = "provider_stopped"
                    run.result = aggregate(run)
                    session.commit()
                    return
                time.sleep(state["attempts"])
        run.result = aggregate(run)
        run.status = (
            "completed"
            if run.result["resolvedOriginCount"] == run.result["originCount"]
            else "partial"
        )
        run.updated_at = utc_now()
        session.commit()
    finally:
        if owned:
            client.close()
        lock_connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": lock_name})
        lock_connection.close()


def main():
    parser = argparse.ArgumentParser(description="真实道路可达性：代表点、候选筛选和500次硬上限")
    parser.add_argument("--run-id")
    parser.add_argument("--max-calls", type=int, default=500)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    settings = Settings()
    engine = create_db_engine(settings)
    try:
        with create_session_factory(engine)() as session:
            run = (
                session.get(RoadAccessibilityRun, args.run_id)
                if args.run_id
                else create_run(session, args.max_calls)
            )
            if run is None:
                raise ValueError("任务不存在")
            if not args.prepare_only:
                if not settings.amap_webservice_key:
                    raise ValueError("未配置Web Service Key")
                execute(session, run, settings.amap_webservice_key.get_secret_value())
            print(
                {
                    "id": run.id,
                    "status": run.status,
                    "origins": len(run.inputs["origins"]),
                    "plannedOD": len(run.inputs["tasks"]),
                    "apiCalls": run.api_calls,
                    "cacheHits": run.cache_hits,
                }
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
