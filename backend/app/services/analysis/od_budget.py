"""Conservative route-call bounds without materializing an OD matrix or making requests."""

from app.services.analysis.road import od_request

VERSION = "od-call-bounds-v1"


def coordinate_count(records):
    # Count the exact six-decimal coordinate strings used by the provider/cache.
    return len({od_request(r["position"], r["position"])["origin"] for r in records})


def estimate_bounds(origins, candidates, existing, *, valid_cache_count=0, attempts=3):
    if (
        isinstance(valid_cache_count, bool)
        or not isinstance(valid_cache_count, int)
        or valid_cache_count < 0
        or isinstance(attempts, bool)
        or not isinstance(attempts, int)
        or not 1 <= attempts <= 3
    ):
        raise ValueError("缓存数需非负整数，最多尝试次数需为1至3的整数")
    origin_count = coordinate_count(origins)
    existing_count = coordinate_count(existing)
    baseline_upper = origin_count * min(3, existing_count)
    candidate_count = None if candidates is None else coordinate_count(candidates)
    candidate_pairs = None if candidate_count is None else origin_count * candidate_count
    lower = None if candidate_pairs is None else max(0, candidate_pairs - valid_cache_count)
    upper = None if candidate_pairs is None else candidate_pairs + baseline_upper
    return {
        "version": VERSION,
        "uniqueOriginCoordinates": origin_count,
        "uniqueCandidateCoordinates": candidate_count,
        "uniqueExistingCoordinates": existing_count,
        "candidateUniqueOD": candidate_pairs,
        "baselineUniqueODUpperBound": baseline_upper,
        "additionalCallsLowerBound": lower,
        "additionalCallsUpperBound": upper,
        "maximumAttemptsUpperBound": None if upper is None else upper * attempts,
        "globalValidCacheCount": valid_cache_count,
        "apiCalls": 0,
        "status": "missing_candidates" if candidates is None else "bounds_only",
        "notice": (
            "候选OD按请求坐标去重后计算完整组合；现状基线仅20km内最近3站，上界不代表实际存在的边。"
            "未逐边匹配缓存，下界保守扣除全库有效缓存，上界未扣缓存或候选/原有站重叠。"
            "这不是实际调用清单、可达性结果或全部站点最短路径。"
        ),
    }
