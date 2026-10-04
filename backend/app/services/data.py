from datetime import UTC, date

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ChargingStation, Region
from app.repositories.data import (
    RegionRepository,
    SnapshotRepository,
    SourceRepository,
    StationRepository,
)
from app.schemas.data import City, Metric, Overview, Source, SourceInfo, Station, TrendPoint
from app.utils.dates import growth_rate, period_label, quarter_label


class DataService:
    """Read persisted data; never synthesizes snapshots or analysis results."""

    def __init__(self, session: Session):
        self.regions = RegionRepository(session)
        self.snapshots = SnapshotRepository(session)
        self.sources = SourceRepository(session)
        self.stations = StationRepository(session)
        self.station_quality = {}

    def require_region(self, adcode: str) -> Region:
        region = self.regions.get(adcode)
        if region is None:
            raise HTTPException(404, "未找到该行政区")
        return region

    def source_info(self, day: date | None = None) -> SourceInfo:
        sources = self.sources.all()
        simulated = any(source.is_demo for source in sources)
        updated = max((source.updated_at for source in sources), default=None)
        statistic_day = day if day is not None else self.snapshots.latest_date()
        return SourceInfo(
            simulated=simulated,
            updatedAt=updated.date().isoformat() if updated and statistic_day else None,
            period=period_label(statistic_day),
            label=(" / ".join(source.name for source in sources) or "尚未接入数据")
            if statistic_day
            else "统计数据未接入",
            note="联调测试数据：数量、面积、趋势与站点位置均为模拟值，不作为正式分析数据。"
            if simulated
            else "尚未接入完整统计。高德已入库POI单独展示，不作为省、市州设施总量。"
            if statistic_day is None
            else "指标来自数据库统计快照；快照总量与分页站点清单分开展示。",
        )

    def station_source_info(self, *, real_only=True) -> SourceInfo:
        statement = self.stations.query(real_only=real_only).subquery()
        updated = self.stations.session.scalar(select(func.max(statement.c.collected_at)))
        return SourceInfo(
            simulated=False if real_only else self.source_info().simulated,
            updatedAt=updated.isoformat() + "Z" if updated else None,
            period="已入库POI清单",
            label="高德地图 Web Service API" if updated else "尚无已采集站点",
            note="坐标GCJ-02；数量为去重入库POI数，不代表完整设施总量。桩数与历史统计暂无数据。",
        )

    def city(self, region: Region, snapshots: dict, day: date | None) -> City:
        snapshot = snapshots.get(region.adcode)
        count = snapshot.station_count if snapshot else None
        piles = snapshot.public_charger_count if snapshot else None
        histories = self.snapshots.history(region.adcode)
        previous_year = next(
            (
                row
                for row in histories
                if day
                and row.statistic_date.year == day.year - 1
                and row.statistic_date.month == day.month
                and row.statistic_date.day == day.day
            ),
            None,
        )
        source = self.sources.get(snapshot.data_source_id) if snapshot else None
        return City(
            id=region.id,
            code=region.adcode,
            adcode=region.adcode,
            name=region.name,
            shortName=region.short_name or region.name,
            level=region.level,
            parentAdcode=region.parent_adcode,
            center=[float(region.center_lng), float(region.center_lat)],
            areaKm2=float(region.area_km2) if region.area_km2 else None,
            region=region.group_name,
            stations=count,
            piles=piles,
            fastRate=round(snapshot.dc_charger_count / piles * 100, 1)
            if snapshot and piles
            else None,
            growth=growth_rate(count, previous_year.station_count if previous_year else None),
            density=round(count / float(region.area_km2) * 100, 2)
            if snapshot and region.area_km2
            else None,
            statisticDate=snapshot.statistic_date if snapshot else None,
            simulated=region.is_demo or bool(source and source.is_demo),
        )

    def cities(self) -> list[City]:
        day = self.snapshots.latest_date()
        rows = self.snapshots.at_date(day)
        return [self.city(region, rows, day) for region in self.regions.cities()]

    def region_detail(self, adcode: str) -> City:
        region = self.require_region(adcode)
        day = self.snapshots.latest_date(adcode)
        return self.city(region, self.snapshots.at_date(day), day)

    def trends(self, adcode: str) -> list[TrendPoint]:
        self.require_region(adcode)
        return [
            TrendPoint(
                period=quarter_label(row.statistic_date),
                statisticDate=row.statistic_date,
                stations=row.station_count,
                piles=row.public_charger_count,
            )
            for row in self.snapshots.history(adcode)
        ]

    def overview(self) -> Overview:
        histories = self.snapshots.history("430000")
        latest = histories[-1] if histories else None
        day = latest.statistic_date if latest else None
        metrics = []
        for key, attribute, label, unit in [
            ("stations", "station_count", "充电站总量", "座"),
            ("piles", "public_charger_count", "公共充电桩", "个"),
        ]:
            current = getattr(latest, attribute) if latest else None
            previous_year = next(
                (
                    row
                    for row in histories
                    if day
                    and (row.statistic_date.year, row.statistic_date.month, row.statistic_date.day)
                    == (day.year - 1, day.month, day.day)
                ),
                None,
            )
            previous_quarter = next(
                (
                    row
                    for row in reversed(histories[:-1])
                    if day
                    and (row.statistic_date.year * 4 + (row.statistic_date.month - 1) // 3)
                    == day.year * 4 + (day.month - 1) // 3 - 1
                ),
                None,
            )
            metrics.append(
                Metric(
                    key=key,
                    label=label,
                    value=current,
                    unit=unit,
                    change="期末快照存量" if latest else "暂无数据 · 统计快照未接入",
                    yoy=growth_rate(
                        current, getattr(previous_year, attribute) if previous_year else None
                    ),
                    qoq=growth_rate(
                        current, getattr(previous_quarter, attribute) if previous_quarter else None
                    ),
                    sparkline=[getattr(row, attribute) for row in histories[-8:]],
                )
            )
        metrics.append(
            Metric(
                key="cities",
                label="统计市州",
                value=len(self.regions.cities()),
                unit="个",
                change="湖南省直属市州",
            )
        )
        metrics.append(
            Metric(
                key="fast",
                label="直流快充占比",
                value=round(latest.dc_charger_count / latest.public_charger_count * 100, 1)
                if latest and latest.public_charger_count
                else None,
                unit="%",
                change="直流桩数量 / 公共充电桩总量"
                if latest
                else "暂无数据 · 高德地点搜索未提供该指标",
            )
        )
        return Overview(metrics=metrics, sourceInfo=self.source_info(day), statisticDate=day)

    def station_view(self, row: ChargingStation) -> Station:
        source = self.sources.get(row.data_source_id)
        quality = self.station_quality.get(row.id, {})
        return Station(
            id=str(row.id),
            poiId=row.poi_id,
            name=row.name,
            address=row.address,
            province=row.province,
            city=row.city,
            district=row.district,
            adcode=row.adcode,
            cityCode=row.adcode[:4] + "00",
            position=[float(row.longitude), float(row.latitude)],
            type=row.station_type,
            piles=row.public_charger_count,
            source=row.source,
            collectedAt=row.collected_at.replace(tzinfo=UTC),
            simulated=bool(source and source.is_demo),
            classification=quality.get("classification"),
            reviewStatus=quality.get("review_status"),
            confidence=quality.get("confidence"),
            needsReview=quality.get("needs_review"),
            batch=quality.get("run_id"),
            rulesVersion=quality.get("rules_version"),
            completenessWarning=bool(quality.get("completeness_warning")),
        )

    def data_sources(self) -> list[Source]:
        return [
            Source(
                id=s.id,
                name=s.name,
                sourceType=s.source_type,
                sourceUrl=s.source_url,
                description=s.description,
                updatedAt=s.updated_at,
                simulated=s.is_demo,
            )
            for s in self.sources.all()
        ]
