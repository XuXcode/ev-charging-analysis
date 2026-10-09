"""Same-year source differences are review clues, never inferred time-series growth."""

import math


def source_differences(records, scope_code):
    grouped = {}
    for row in records:
        value = row.get("value")
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            or value < 0
        ):
            continue
        key = (row["year"], row["metric"], row["unit"])
        grouped.setdefault(key, []).append(row)
    result = []
    for (year, metric, unit), rows in sorted(grouped.items()):
        if len({row["value"] for row in rows}) <= 1:
            continue
        result.append(
            {
                "scopeCode": scope_code,
                "year": year,
                "metric": metric,
                "unit": unit,
                "records": sorted(
                    rows, key=lambda row: (row["value"], row["sourceUrl"], row["hash"])
                ),
                "notice": "同年同指标的来源数值不同，统计时点和范围尚未确认可比；保留独立记录，不合并或计算增长率。",
            }
        )
    return result
