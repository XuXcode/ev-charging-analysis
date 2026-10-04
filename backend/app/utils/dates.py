from datetime import date


def quarter_label(day: date) -> str:
    return f"{day.year} Q{(day.month - 1) // 3 + 1}"


def period_label(day: date | None) -> str:
    return f"{day.year}年第{(day.month - 1) // 3 + 1}季度" if day else "暂无统计快照"


def growth_rate(current: int, previous: int | None) -> float | None:
    return round((current / previous - 1) * 100, 1) if previous else None
