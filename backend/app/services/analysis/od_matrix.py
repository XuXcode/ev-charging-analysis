"""Sparse directional OD matrix using existing route evidence; no network I/O."""

import math
from datetime import timedelta

from shapely import STRtree
from shapely.geometry import Point, box
from sqlalchemy import func, select

from app.models import RoadODCache
from app.models.entities import utc_now
from app.services.analysis.job import digest
from app.services.analysis.road import ENDPOINT, distance_m, od_request

VERSION = "sparse-od-matrix-v1.1"


def nearby_indices(tree, position, radius_m):
    angular = math.degrees(radius_m / 6371008.8)
    lon, lat = position
    longitude_delta = angular / max(1e-6, math.cos(math.radians(min(89.99, abs(lat) + angular))))
    return tree.query(
        box(lon - longitude_delta, lat - angular, lon + longitude_delta, lat + angular)
    )


def read_observations(session, keys, ttl_days):
    observations = {}
    keys = sorted(set(keys))
    cutoff = utc_now() - timedelta(days=ttl_days)
    for offset in range(0, len(keys), 1000):
        for row in session.scalars(
            select(RoadODCache).where(RoadODCache.key.in_(keys[offset : offset + 1000]))
        ):
            if row.fetched_at >= cutoff and row.response.get("status") in {"ok", "no_route"}:
                observations[row.key] = {
                    **row.response,
                    "observedAt": row.fetched_at.isoformat() + "Z",
                }
    return observations


def cached_matrix(session, origins, destinations, ttl_days=7):
    """Read a frozen pair set in batches; missing edges remain unknown."""
    pairs = [
        (o["id"], d["id"], cache_key(o["position"], d["position"]))
        for o in origins
        for d in destinations
    ]
    observations = read_observations(session, (p[2] for p in pairs), ttl_days)
    return [
        {
            "originId": o,
            "destinationId": d,
            "cacheKey": key,
            **observations.get(
                key, {"status": "missing", "durationSeconds": None, "distanceM": None}
            ),
        }
        for o, d, key in pairs
    ]


def cache_key(origin, destination):
    request = od_request(origin, destination)
    return digest({"endpoint": ENDPOINT, "coordinateSystem": "GCJ-02", **request})


def plan(session, origins, destinations, *, nearest=5, radius_m=20000, ttl_days=7):
    if not 1 <= nearest <= 20 or radius_m <= 0 or not 0 <= ttl_days <= 30:
        raise ValueError("OD候选数、半径或缓存有效期无效")
    edges, unique = [], {}
    tree = STRtree([Point(d["position"]) for d in destinations])
    for origin in sorted(origins, key=lambda r: r["id"]):
        ordered = sorted(
            [
                (
                    distance_m(origin["position"], destinations[int(i)]["position"]),
                    destinations[int(i)],
                )
                for i in nearby_indices(tree, origin["position"], radius_m)
            ],
            key=lambda item: (item[0], item[1]["id"]),
        )
        for straight, destination in [item for item in ordered if item[0] <= radius_m][:nearest]:
            key = cache_key(origin["position"], destination["position"])
            unique.setdefault(
                key, {"status": "missing", "durationSeconds": None, "distanceM": None}
            )
            edges.append(
                {
                    "originId": origin["id"],
                    "destinationId": destination["id"],
                    "straightDistanceM": straight,
                    "cacheKey": key,
                    **unique[key],
                }
            )
    unique.update(read_observations(session, unique, ttl_days))
    edges = [{**edge, **unique[edge["cacheKey"]]} for edge in edges]
    misses = sum(e["status"] == "missing" for e in unique.values())
    return {
        "version": VERSION,
        "edges": edges,
        "uniqueOD": len(unique),
        "validCacheHits": len(unique) - misses,
        "estimatedCalls": misses,
        "maximumAttempts": misses * 3,
        "originsWithoutCandidates": sorted(
            {o["id"] for o in origins} - {e["originId"] for e in edges}
        ),
        "apiCalls": 0,
        "parameters": {"nearest": nearest, "radiusM": radius_m, "ttlDays": ttl_days},
        "notice": "仅规划并读取缓存，不调用高德；空间候选筛选可能遗漏道路更近站点。缓存缺失不等于不可达。",
    }


def count_valid_observations(session, ttl_days=7):
    """Count the cache without loading route JSON; a bound, not scoped cache matches."""
    if not isinstance(ttl_days, int) or isinstance(ttl_days, bool) or not 0 <= ttl_days <= 30:
        raise ValueError("缓存有效期需为0至30天整数")
    return int(
        session.scalar(
            select(func.count())
            .select_from(RoadODCache)
            .where(
                RoadODCache.fetched_at >= utc_now() - timedelta(days=ttl_days),
                RoadODCache.response["status"].as_string().in_(["ok", "no_route"]),
            )
        )
        or 0
    )
