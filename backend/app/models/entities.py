from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_unicode_ci",
}


def utc_now() -> datetime:
    """MySQL DATETIME stores UTC without an implicit local-time conversion."""
    return datetime.now(UTC).replace(tzinfo=None)


class DataSource(Base):
    __tablename__ = "data_sources"
    __table_args__ = TABLE_OPTIONS
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    source_type: Mapped[str] = mapped_column(String(40))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    description: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")


class Region(Base):
    __tablename__ = "regions"
    __table_args__ = (
        CheckConstraint("center_lng BETWEEN -180 AND 180", name="center_lng_range"),
        CheckConstraint("center_lat BETWEEN -90 AND 90", name="center_lat_range"),
        CheckConstraint("area_km2 IS NULL OR area_km2 > 0", name="positive_area"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    adcode: Mapped[str] = mapped_column(String(6), unique=True)
    level: Mapped[str] = mapped_column(String(20))
    parent_adcode: Mapped[str | None] = mapped_column(ForeignKey("regions.adcode"), index=True)
    center_lng: Mapped[Decimal] = mapped_column(Numeric(10, 7))
    center_lat: Mapped[Decimal] = mapped_column(Numeric(10, 7))
    short_name: Mapped[str | None] = mapped_column(String(40))
    group_name: Mapped[str | None] = mapped_column(String(40))
    area_km2: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")


class ChargingStation(Base):
    __tablename__ = "charging_stations"
    __table_args__ = (
        CheckConstraint("longitude BETWEEN -180 AND 180", name="longitude_range"),
        CheckConstraint("latitude BETWEEN -90 AND 90", name="latitude_range"),
        CheckConstraint(
            "public_charger_count IS NULL OR public_charger_count >= 0", name="charger_nonnegative"
        ),
        Index("ix_charging_stations_location", "longitude", "latitude"),
        Index(
            "ix_charging_stations_source_adcode_location",
            "source",
            "adcode",
            "longitude",
            "latitude",
        ),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    poi_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    # Conservative secondary identity: normalized name + GCJ-02 coordinates (6 decimals).
    identity_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(String(500))
    province: Mapped[str] = mapped_column(String(100))
    city: Mapped[str] = mapped_column(String(100), index=True)
    district: Mapped[str | None] = mapped_column(String(100))
    adcode: Mapped[str] = mapped_column(String(6), index=True)
    longitude: Mapped[Decimal] = mapped_column(Numeric(10, 7))
    latitude: Mapped[Decimal] = mapped_column(Numeric(10, 7))
    station_type: Mapped[str | None] = mapped_column(String(40))
    source: Mapped[str] = mapped_column(String(200))
    collected_at: Mapped[datetime] = mapped_column(DateTime)
    public_charger_count: Mapped[int | None] = mapped_column(Integer)
    data_source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), index=True)


class CollectionRun(Base):
    __tablename__ = "collection_runs"
    __table_args__ = TABLE_OPTIONS
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(24))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    manifest: Mapped[dict] = mapped_column(JSON)
    last_error: Mapped[str | None] = mapped_column(String(500))


class CollectionPage(Base):
    __tablename__ = "collection_pages"
    __table_args__ = (UniqueConstraint("run_id", "adcode", "page"), TABLE_OPTIONS)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("collection_runs.id"), index=True)
    city_code: Mapped[str] = mapped_column(String(6), index=True)
    adcode: Mapped[str] = mapped_column(String(6))
    page: Mapped[int] = mapped_column(Integer)
    collected_at: Mapped[datetime] = mapped_column(DateTime)
    attempts: Mapped[int] = mapped_column(Integer)
    raw_pois: Mapped[list] = mapped_column(JSON)
    response_hash: Mapped[str] = mapped_column(String(64))
    outcomes: Mapped[list] = mapped_column(JSON)
    terminal: Mapped[bool] = mapped_column(Boolean)
    capped: Mapped[bool] = mapped_column(Boolean)


class StatisticSnapshot(Base):
    __tablename__ = "statistic_snapshots"
    __table_args__ = (
        UniqueConstraint("region_adcode", "statistic_date"),
        CheckConstraint("station_count >= 0", name="station_nonnegative"),
        CheckConstraint(
            "public_charger_count >= 0 AND dc_charger_count >= 0 AND ac_charger_count >= 0",
            name="chargers_nonnegative",
        ),
        CheckConstraint(
            "dc_charger_count + ac_charger_count = public_charger_count", name="charger_split"
        ),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    region_adcode: Mapped[str] = mapped_column(ForeignKey("regions.adcode"), index=True)
    statistic_date: Mapped[date] = mapped_column(Date)
    station_count: Mapped[int] = mapped_column(Integer)
    public_charger_count: Mapped[int] = mapped_column(Integer)
    dc_charger_count: Mapped[int] = mapped_column(Integer)
    ac_charger_count: Mapped[int] = mapped_column(Integer)
    data_source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), index=True)
