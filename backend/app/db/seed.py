"""Explicit test-data import. Nothing is seeded at application startup."""

import argparse
import calendar
import json
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import create_db_engine, create_session_factory
from app.models import DataSource, Region, StatisticSnapshot
from app.repositories.data import StationRepository
from app.schemas.data import StationCreate

FIXTURE = Path(__file__).parent / "fixtures/dashboard.json"
SOURCE_NAME = "前端联调测试数据（模拟）"


def quarter_end(period: str) -> date:
    year, quarter = period.split(" Q")
    month = int(quarter) * 3
    return date(int(year), month, calendar.monthrange(int(year), month)[1])


def seed_demo(session: Session) -> dict[str, int]:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    updated_at = datetime.fromisoformat(data["sourceInfo"]["updatedAt"])
    source = session.scalar(select(DataSource).where(DataSource.name == SOURCE_NAME))
    if source and not source.is_demo:
        raise ValueError("拒绝覆盖非演示数据来源")
    if not source:
        source = DataSource(
            name=SOURCE_NAME,
            source_type="demo",
            source_url=None,
            description=data["description"],
            updated_at=updated_at,
            is_demo=True,
        )
        session.add(source)
        session.flush()
    source.updated_at = updated_at
    province = {
        "code": "430000",
        "name": "湖南省",
        "shortName": "湖南",
        "center": [112.2, 27.8],
        "areaKm2": sum(city["areaKm2"] for city in data["cities"]),
        "region": None,
    }
    for city in [province, *data["cities"]]:
        row = session.scalar(select(Region).where(Region.adcode == city["code"]))
        if row and not row.is_demo:
            raise ValueError("拒绝覆盖非演示行政区")
        if not row:
            row = Region(adcode=city["code"])
            session.add(row)
        row.name = city["name"]
        row.short_name = city["shortName"]
        row.level = "province" if city["code"] == "430000" else "city"
        row.parent_adcode = None if row.level == "province" else "430000"
        row.center_lng, row.center_lat = city["center"]
        row.area_km2 = city["areaKm2"]
        row.group_name = city["region"]
        row.is_demo = True
        session.flush()  # parent is inserted before children
    cities = {city["code"]: city for city in data["cities"]}
    for marker in data["stations"]:
        city = cities[marker["cityCode"]]
        poi_id = "demo-" + marker["id"]
        repo = StationRepository(session)
        # Do not overwrite imported production records, even if a demo POI id collided.
        from app.models import ChargingStation

        existing = session.scalar(select(ChargingStation).where(ChargingStation.poi_id == poi_id))
        if existing and existing.data_source_id != source.id:
            raise ValueError("拒绝覆盖非演示站点")
        repo.upsert_by_poi(
            StationCreate(
                poi_id=poi_id,
                name=marker["name"],
                address="演示位置，仅供接口联调",
                province="湖南省",
                city=city["name"],
                district=None,
                adcode=city["code"],
                longitude=marker["position"][0],
                latitude=marker["position"][1],
                station_type=marker["type"],
                source=SOURCE_NAME,
                collected_at=updated_at,
                public_charger_count=marker["piles"],
                data_source_id=source.id,
            )
        )
    count = 0
    for i, point in enumerate(data["trend"]):
        day = quarter_end(point["period"])
        dc_total = sum(
            round(data["cityTrends"][code][i]["piles"] * city["fastRate"] / 100)
            for code, city in cities.items()
        )
        snapshots = [
            (
                code,
                data["cityTrends"][code][i],
                round(data["cityTrends"][code][i]["piles"] * city["fastRate"] / 100),
            )
            for code, city in cities.items()
        ]
        snapshots.append(("430000", point, dc_total))
        for code, values, dc in snapshots:
            row = session.scalar(
                select(StatisticSnapshot).where(
                    StatisticSnapshot.region_adcode == code, StatisticSnapshot.statistic_date == day
                )
            )
            if row and row.data_source_id != source.id:
                raise ValueError("拒绝覆盖非演示统计快照")
            if not row:
                row = StatisticSnapshot(region_adcode=code, statistic_date=day)
                session.add(row)
            row.station_count = values["stations"]
            row.public_charger_count = values["piles"]
            row.dc_charger_count = dc
            row.ac_charger_count = values["piles"] - dc
            row.data_source_id = source.id
            session.flush()
            count += 1
    return {"regions": len(cities) + 1, "stations": len(data["stations"]), "snapshots": count}


def main():
    parser = argparse.ArgumentParser(description="导入明确标记的测试数据；不应用于生产数据库")
    parser.add_argument("--demo", action="store_true", required=True)
    parser.parse_args()
    settings = get_settings()
    if settings.environment.lower() == "production":
        raise SystemExit("生产环境禁止导入演示数据")
    engine = create_db_engine(settings)
    try:
        with create_session_factory(engine).begin() as session:
            counts = seed_demo(session)
        print(f"模拟数据导入成功：{counts}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
