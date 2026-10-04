from math import isfinite

from fastapi import HTTPException


def parse_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    try:
        parts = tuple(float(part.strip()) for part in value.split(","))
        if len(parts) != 4 or not all(isfinite(part) for part in parts):
            raise ValueError
        west, south, east, north = parts
        if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
            raise ValueError
        return west, south, east, north
    except ValueError:
        raise HTTPException(
            422, "bbox 格式为 west,south,east,north，使用合法经纬度且最小值不大于最大值"
        ) from None
