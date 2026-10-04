"""Weighted maximum incremental coverage with explicit missing-OD protection."""

import math

VERSION = "incremental-maximum-coverage-v1"


def validate_problem(problem):
    origins, candidates = problem["origins"], problem["candidates"]
    for name, rows in (("origins", origins), ("candidates", candidates)):
        if len({r["id"] for r in rows}) != len(rows):
            raise ValueError(f"{name} ID重复")
    if (
        not origins
        or any(
            r.get("weight") is None or not math.isfinite(r["weight"]) or r["weight"] < 0
            for r in origins
        )
        or sum(r["weight"] for r in origins) <= 0
    ):
        raise ValueError("缺少有效真实需求权重，不生成优化结果")
    if (
        not isinstance(problem["n"], int)
        or isinstance(problem["n"], bool)
        or not 0 <= problem["n"] <= len(candidates)
    ):
        raise ValueError("新增N必须在0和可用候选数之间")
    if (
        problem["threshold"] <= 0
        or not math.isfinite(problem["threshold"])
        or problem["metric"] not in {"durationSeconds", "distanceM", "straightDistanceM"}
    ):
        raise ValueError("服务阈值或单位不合法")
    ids = {r["id"] for r in origins}
    if set(problem["baselineCovered"]) - ids:
        raise ValueError("现状覆盖包含未知需求点")
    coverage = {}
    edges = {(r["originId"], r["destinationId"]): r for r in problem["edges"]}
    if len(edges) != len(problem["edges"]):
        raise ValueError("OD边重复")
    for candidate in candidates:
        hit = set()
        for origin in origins:
            edge = edges.get((origin["id"], candidate["id"]))
            if edge is None or edge.get("status") not in {"ok", "no_route", "spatially_excluded"}:
                raise ValueError("候选OD未完整：未知不能作为未覆盖")
            if edge["status"] == "ok":
                value = edge.get(problem["metric"])
                if value is None or not math.isfinite(value) or value < 0:
                    raise ValueError("OD服务指标缺失或非法")
                if value <= problem["threshold"]:
                    hit.add(origin["id"])
            elif edge["status"] == "spatially_excluded" and problem["metric"] == "durationSeconds":
                raise ValueError("空间排除不能证明道路时间不可达")
        coverage[candidate["id"]] = hit
    return coverage


def summarize(problem, selected, coverage, solver):
    weights = {r["id"]: r["weight"] for r in problem["origins"]}
    before = set(problem["baselineCovered"])
    after = before | set().union(*(coverage[c] for c in selected))
    total = math.fsum(weights.values())
    before_weight, after_weight = (
        sum(weights[k] for k in sorted(before)),
        sum(weights[k] for k in sorted(after)),
    )
    return {
        "algorithmVersion": VERSION,
        "solver": solver,
        "selectedIds": selected,
        "before": {
            "coveredWeight": before_weight,
            "coveragePercent": 100 * before_weight / total,
            "uncoveredWeight": total - before_weight,
        },
        "after": {
            "coveredWeight": after_weight,
            "coveragePercent": 100 * after_weight / total,
            "uncoveredWeight": total - after_weight,
        },
        "coverageGain": after_weight - before_weight,
        "newlyCoveredIds": sorted(after - before),
        "uncoveredIds": sorted(set(weights) - after),
        "notice": "覆盖比例按输入需求权重汇总；不代表人口或面积，除非来源明确提供该口径。最大覆盖不以最短平均时间为优化目标。",
    }


def greedy(problem):
    coverage = validate_problem(problem)
    weights = {r["id"]: r["weight"] for r in problem["origins"]}
    covered, selected = set(problem["baselineCovered"]), []
    for _ in range(problem["n"]):
        remaining = sorted(set(coverage) - set(selected))
        winner = min(
            remaining, key=lambda c: (-sum(weights[k] for k in sorted(coverage[c] - covered)), c)
        )
        if sum(weights[k] for k in sorted(coverage[winner] - covered)) <= 0:
            break
        selected.append(winner)
        covered |= coverage[winner]
    return summarize(
        problem,
        selected,
        coverage,
        {"name": "greedy", "status": "heuristic", "optimal": False, "budget": problem["n"]},
    )


def mclp(problem, *, time_limit=30):
    import numpy as np
    import scipy
    from scipy.optimize import Bounds, LinearConstraint, milp
    from scipy.sparse import lil_matrix

    coverage = validate_problem(problem)
    candidates = sorted(coverage)
    origins = sorted(
        r["id"] for r in problem["origins"] if r["id"] not in problem["baselineCovered"]
    )
    weights = {r["id"]: r["weight"] for r in problem["origins"]}
    if not candidates or not origins or problem["n"] == 0:
        return summarize(
            problem,
            [],
            coverage,
            {
                "name": "mclp",
                "status": "optimal",
                "optimal": True,
                "gap": 0,
                "scipyVersion": scipy.__version__,
            },
        )
    p, d = len(candidates), len(origins)
    matrix = lil_matrix((d + 1, p + d))
    matrix[0, :p] = 1
    for i, origin in enumerate(origins):
        matrix[i + 1, p + i] = 1
        for j, candidate in enumerate(candidates):
            if origin in coverage[candidate]:
                matrix[i + 1, j] = -1
    result = milp(
        c=np.array([0.0] * p + [-weights[o] for o in origins]),
        integrality=np.ones(p + d),
        bounds=Bounds(0, 1),
        constraints=LinearConstraint(matrix.tocsc(), -np.inf, np.array([problem["n"]] + [0] * d)),
        options={"time_limit": time_limit, "mip_rel_gap": 0},
    )
    if result.x is None:
        raise ValueError("MCLP未获得可行解，不能展示推荐方案")
    selected = [c for j, c in enumerate(candidates) if result.x[j] > 0.5]
    # Remove zero-gain selections without altering the maximum-coverage objective.
    for c in list(reversed(selected)):
        without = set(problem["baselineCovered"]) | set().union(
            *(coverage[k] for k in selected if k != c)
        )
        with_c = set(problem["baselineCovered"]) | set().union(*(coverage[k] for k in selected))
        if sum(weights[k] for k in sorted(without)) == sum(weights[k] for k in sorted(with_c)):
            selected.remove(c)
    return summarize(
        problem,
        selected,
        coverage,
        {
            "name": "mclp",
            "status": "optimal" if result.status == 0 else "feasible_limit",
            "optimal": result.status == 0,
            "gap": float(result.mip_gap),
            "timeLimitSeconds": time_limit,
            "scipyVersion": scipy.__version__,
        },
    )
