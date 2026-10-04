from collections.abc import Iterator
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, load_only

from app.models import (
    AnalysisScopeQuality,
    ChargingStation,
    DataSource,
    PoiQuality,
    Region,
    StatisticSnapshot,
)
from app.schemas.data import StationCreate


class RegionRepository:
    def __init__(self, session: Session):
        self.session = session

    def cities(self) -> list[Region]:
        return list(
            self.session.scalars(
                select(Region)
                .where(Region.parent_adcode == "430000", Region.level == "city")
                .order_by(Region.adcode)
            )
        )

    def get(self, adcode: str) -> Region | None:
        return self.session.scalar(select(Region).where(Region.adcode == adcode))

    def by_city_name(self, name: str) -> Region | None:
        return self.session.scalar(
            select(Region).where(
                Region.level == "city", or_(Region.name == name, Region.short_name == name)
            )
        )


class SnapshotRepository:
    def __init__(self, session: Session):
        self.session = session

    def latest_date(self, adcode: str = "430000") -> date | None:
        return self.session.scalar(
            select(func.max(StatisticSnapshot.statistic_date)).where(
                StatisticSnapshot.region_adcode == adcode
            )
        )

    def at_date(self, day: date | None) -> dict[str, StatisticSnapshot]:
        if day is None:
            return {}
        return {
            row.region_adcode: row
            for row in self.session.scalars(
                select(StatisticSnapshot).where(StatisticSnapshot.statistic_date == day)
            )
        }

    def history(self, adcode: str) -> list[StatisticSnapshot]:
        return list(
            self.session.scalars(
                select(StatisticSnapshot)
                .where(StatisticSnapshot.region_adcode == adcode)
                .order_by(StatisticSnapshot.statistic_date)
            )
        )

    def save(self, snapshot: StatisticSnapshot) -> StatisticSnapshot:
        """Analysis jobs can persist a precomputed snapshot; caller owns commit."""
        self.session.add(snapshot)
        self.session.flush()
        return snapshot


class SourceRepository:
    def __init__(self, session: Session):
        self.session = session
        self._by_id = {}
        self._all = None

    def all(self) -> list[DataSource]:
        if self._all is None:
            self._all = list(self.session.scalars(select(DataSource).order_by(DataSource.id)))
            self._by_id.update({row.id: row for row in self._all})
        return self._all

    def get(self, source_id: int) -> DataSource | None:
        if source_id not in self._by_id:
            self._by_id[source_id] = self.session.get(DataSource, source_id)
        return self._by_id[source_id]


class StationRepository:
    def __init__(self, session: Session):
        self.session = session

    def query(
        self,
        *,
        region: Region | None = None,
        keyword: str | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        real_only: bool = False,
        exact_adcode: str | None = None,
        classification: str | None = None,
        review_status: str | None = None,
        needs_review: bool | None = None,
        batch: str | None = None,
    ):
        statement = select(ChargingStation)
        if classification or review_status or batch or needs_review is not None:
            statement = statement.join(PoiQuality, PoiQuality.station_id == ChargingStation.id)
            if classification:
                statement = statement.where(PoiQuality.classification == classification)
            if review_status:
                statement = statement.where(PoiQuality.review_status == review_status)
            if needs_review is not None:
                statement = statement.where(PoiQuality.needs_review == needs_review)
            if batch:
                statement = statement.where(PoiQuality.run_id == batch)
        if real_only:
            statement = statement.join(
                DataSource, DataSource.id == ChargingStation.data_source_id
            ).where(
                DataSource.is_demo.is_(False),
                ChargingStation.source == "amap",
                ChargingStation.adcode.startswith("43"),
            )
        if region:
            prefix = (
                region.adcode[:2]
                if region.level == "province"
                else region.adcode[:4]
                if region.level == "city"
                else region.adcode
            )
            statement = statement.where(ChargingStation.adcode.startswith(prefix, autoescape=True))
        if keyword:
            statement = statement.where(
                or_(
                    ChargingStation.name.contains(keyword, autoescape=True),
                    ChargingStation.address.contains(keyword, autoescape=True),
                    ChargingStation.poi_id.contains(keyword, autoescape=True),
                )
            )
        if exact_adcode:
            statement = statement.where(ChargingStation.adcode == exact_adcode)
        if bbox:
            west, south, east, north = bbox
            statement = statement.where(
                ChargingStation.longitude.between(west, east),
                ChargingStation.latitude.between(south, north),
            )
        return statement

    def page(self, *, page: int, page_size: int, **filters):
        statement = self.query(**filters)
        total = (
            self.session.scalar(
                statement.with_only_columns(func.count(), maintain_column_froms=True).order_by(None)
            )
            or 0
        )
        # Materialize only the filtered page IDs before reading wide text columns.
        # LIMIT in the derived table avoids sorting full station payloads across
        # source/quality joins; both phases retain the same stable ID order.
        page_ids = (
            statement.with_only_columns(ChargingStation.id, maintain_column_froms=True)
            .order_by(ChargingStation.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
            .subquery()
        )
        items = list(
            self.session.scalars(
                select(ChargingStation)
                .join(page_ids, ChargingStation.id == page_ids.c.id)
                .options(
                    load_only(
                        ChargingStation.id,
                        ChargingStation.poi_id,
                        ChargingStation.name,
                        ChargingStation.address,
                        ChargingStation.province,
                        ChargingStation.city,
                        ChargingStation.district,
                        ChargingStation.adcode,
                        ChargingStation.longitude,
                        ChargingStation.latitude,
                        ChargingStation.station_type,
                        ChargingStation.public_charger_count,
                        ChargingStation.source,
                        ChargingStation.collected_at,
                        ChargingStation.data_source_id,
                    )
                )
                .order_by(ChargingStation.id)
            )
        )
        return items, total

    def quality_for(self, rows):
        """One projected query per page; do not attach raw provider JSON to map payloads."""
        if not rows:
            return {}
        values = self.session.execute(
            select(
                PoiQuality.station_id,
                PoiQuality.classification,
                PoiQuality.review_status,
                PoiQuality.confidence,
                PoiQuality.needs_review,
                PoiQuality.run_id,
                PoiQuality.rules_version,
                AnalysisScopeQuality.completeness_warning,
            )
            .join(ChargingStation, ChargingStation.id == PoiQuality.station_id)
            .outerjoin(AnalysisScopeQuality, AnalysisScopeQuality.adcode == ChargingStation.adcode)
            .where(PoiQuality.station_id.in_([row.id for row in rows]))
        )
        return {row.station_id: row._asdict() for row in values}

    def iter_for_region(
        self, region: Region, *, batch_size: int = 500
    ) -> Iterator[ChargingStation]:
        """Batch-access contract for a future collector / spatial-analysis worker."""
        yield from self.session.scalars(
            self.query(region=region)
            .order_by(ChargingStation.id)
            .execution_options(yield_per=batch_size)
        )

    def upsert_by_poi(self, payload: StationCreate) -> ChargingStation:
        """Persist validated collected fields; no POI requests or auto-commit."""
        row = (
            self.session.scalar(
                select(ChargingStation).where(ChargingStation.poi_id == payload.poi_id)
            )
            if payload.poi_id
            else None
        )
        if row is None:
            row = ChargingStation(**payload.model_dump())
            self.session.add(row)
        else:
            for name, value in payload.model_dump().items():
                setattr(row, name, value)
        self.session.flush()
        return row
