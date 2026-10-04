"""Versioned demand preparation. Unknown evidence never becomes zero demand."""

import math

VERSION = "demand-normalization-v1"
VARIABLES = {"residential", "parking", "commercial", "office", "transport", "population"}


def prepare(records, weights, method="minmax"):
    if method != "minmax" or not weights or set(weights) - VARIABLES:
        raise ValueError("需指定受支持的需求变量权重和minmax标准化")
    if (
        any(not math.isfinite(v) or v < 0 for v in weights.values())
        or math.fsum(weights.values()) <= 0
    ):
        raise ValueError("权重须为有限非负数且合计大于0")
    total_weight = math.fsum(weights.values())
    active = {k: weights[k] / total_weight for k in sorted(weights) if weights[k] > 0}
    limits = {}
    for key in active:
        values = [
            r["variables"][key] for r in records if r.get("variables", {}).get(key) is not None
        ]
        if any(
            not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v < 0
            for v in values
        ):
            raise ValueError("需求观测须为有限非负数")
        limits[key] = [min(values), max(values)] if values else None
    nodes = []
    for row in records:
        missing = [key for key in active if row.get("variables", {}).get(key) is None]
        constant = [key for key, bounds in limits.items() if bounds and bounds[0] == bounds[1]]
        complete = not missing and not constant
        normalized = (
            {
                key: (row["variables"][key] - limits[key][0]) / (limits[key][1] - limits[key][0])
                for key in active
            }
            if complete
            else None
        )
        nodes.append(
            {
                **row,
                "weight": sum(normalized[k] * active[k] for k in active) if complete else None,
                "normalized": normalized,
                "missingVariables": missing,
                "constantVariables": constant,
                "complete": complete,
            }
        )
    return {
        "version": VERSION,
        "method": method,
        "weights": active,
        "limits": limits,
        "nodes": nodes,
        "unit": "weighted_demand_index",
        "notice": "标准化需求指数不是人口数、充电次数或需求预测；缺失或无区分度变量不补值。",
    }
