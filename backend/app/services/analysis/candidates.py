"""Filter evidence-backed facilities, retaining exclusion decisions."""

from shapely import STRtree
from shapely.geometry import Point, shape

from app.services.analysis.od_matrix import nearby_indices
from app.services.analysis.road import distance_m

VERSION = "candidate-facility-filter-v1"
CATEGORIES = {"parking", "commercial", "office", "transport", "residential"}


def filter_candidates(
    records, boundary, existing, *, min_existing_distance_m=100, dedup_distance_m=20
):
    if min_existing_distance_m < 0 or dedup_distance_m < 0:
        raise ValueError("空间约束距离不可为负")
    polygon = shape(boundary)
    if polygon.is_empty or not polygon.is_valid:
        raise ValueError("候选筛选边界无效")
    kept, excluded, seen = [], [], set()
    existing_tree = STRtree([Point(r["position"]) for r in existing])
    # Stable identity ordering makes duplicate decisions reproducible.
    for row in sorted(records, key=lambda r: r["id"]):
        identity = (row["source"], row["poiId"])
        reason = None
        if row.get("category") not in CATEGORIES:
            reason = "unsupported_facility_category"
        elif not polygon.covers(Point(row["position"])):
            reason = "outside_boundary"
        elif identity in seen or any(
            distance_m(row["position"], r["position"]) <= dedup_distance_m for r in kept
        ):
            reason = "duplicate_facility"
        elif any(
            distance_m(row["position"], existing[int(i)]["position"]) < min_existing_distance_m
            for i in nearby_indices(existing_tree, row["position"], min_existing_distance_m)
        ):
            reason = "too_close_to_existing"
        if reason:
            excluded.append({"id": row["id"], "reason": reason})
        else:
            seen.add(identity)
            kept.append(
                {
                    **row,
                    "score": None,
                    "scoreNotice": "需求与建设条件尚未评分；真实设施位置不等于可建设用地。",
                }
            )
    return {
        "version": VERSION,
        "candidates": kept,
        "excluded": excluded,
        "constraints": {
            "minExistingDistanceM": min_existing_distance_m,
            "dedupDistanceM": dedup_distance_m,
        },
    }


def score_candidates(candidates, evidence, weights):
    """An optional score consumes normalized, sourced measurements only."""
    import math

    if (
        not weights
        or any(not math.isfinite(v) or v < 0 for v in weights.values())
        or sum(weights.values()) <= 0
    ):
        raise ValueError("候选评分权重无效")
    result = []
    for candidate in candidates:
        observations = evidence.get(candidate["id"], {})
        active = [key for key, weight in weights.items() if weight > 0]
        missing = [key for key in active if key not in observations]
        for item in observations.values():
            if (
                not item.get("source")
                or not item.get("sourceUrl")
                or not math.isfinite(item["value"])
                or not 0 <= item["value"] <= 1
            ):
                raise ValueError("评分证据需来源和0至1的标准化实测值")
        result.append(
            {
                **candidate,
                "score": None
                if missing
                else sum(observations[k]["value"] * weights[k] for k in active)
                / sum(weights.values()),
                "scoreEvidence": observations,
                "missingScoreVariables": missing,
            }
        )
    return result
