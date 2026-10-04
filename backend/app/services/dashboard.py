from app.core.indicators import GROUP_DEFINITIONS, INDICATORS, RESERVED_CHARTS
from app.services.data import DataService


def dashboard_payload(service: DataService) -> dict:
    """Compatibility adapter for the current Vue dashboard. DB-derived values only."""
    overview = service.overview()
    cities = service.cities()
    city_trends = {
        city.code: [point.model_dump(mode="json") for point in service.trends(city.code)]
        for city in cities
    }
    region_names = list(dict.fromkeys(city.region for city in cities if city.region))
    group_rows = {
        "region": [
            {
                "key": name,
                "label": name,
                "cityCodes": [city.code for city in cities if city.region == name],
            }
            for name in region_names
        ],
        "scale": [
            {
                "key": "high",
                "label": "1,000座及以上",
                "cityCodes": [
                    city.code
                    for city in cities
                    if city.stations is not None and city.stations >= 1000
                ],
            },
            {
                "key": "middle",
                "label": "500–999座",
                "cityCodes": [
                    city.code
                    for city in cities
                    if city.stations is not None and 500 <= city.stations < 1000
                ],
            },
            {
                "key": "low",
                "label": "不足500座",
                "cityCodes": [
                    city.code
                    for city in cities
                    if city.stations is not None and city.stations < 500
                ],
            },
        ],
    }
    unknown_codes = [city.code for city in cities if city.stations is None]
    if unknown_codes:
        group_rows["scale"] = [group for group in group_rows["scale"] if group["cityCodes"]]
        group_rows["scale"].append(
            {"key": "pending", "label": "统计待接入", "cityCodes": unknown_codes}
        )
    for groups in group_rows.values():
        for group in groups:
            members = [city for city in cities if city.code in group["cityCodes"]]
            group.update(
                stations=sum(city.stations for city in members)
                if members and all(city.stations is not None for city in members)
                else None,
                piles=sum(city.piles for city in members)
                if members and all(city.piles is not None for city in members)
                else None,
            )
            points = {}
            for code in group["cityCodes"]:
                for point in city_trends[code]:
                    key = point["statisticDate"]
                    merged = points.setdefault(
                        key, {"period": point["period"], "stations": 0, "piles": 0}
                    )
                    merged["stations"] += point["stations"]
                    merged["piles"] += point["piles"]
            group["trend"] = [points[key] for key in sorted(points)]
    marker_rows, marker_total = service.stations.page(page=1, page_size=200, real_only=True)
    return {
        "cities": [city.model_dump(mode="json") for city in cities],
        "stations": [service.station_view(row).model_dump(mode="json") for row in marker_rows],
        "metrics": [metric.model_dump(mode="json") for metric in overview.metrics],
        "trend": [point.model_dump(mode="json") for point in service.trends("430000")]
        if service.regions.get("430000")
        else [],
        "sourceInfo": overview.sourceInfo.model_dump(mode="json"),
        "regions": [
            {"name": group["label"], "stations": group["stations"]}
            for group in group_rows["region"]
        ],
        "cityTrends": city_trends,
        "analysisGroups": group_rows,
        "indicatorDefinitions": INDICATORS,
        "groupDefinitions": GROUP_DEFINITIONS,
        "reservedCharts": RESERVED_CHARTS,
        "stationPage": {"limit": 200, "total": marker_total, "truncated": marker_total > 200},
    }
