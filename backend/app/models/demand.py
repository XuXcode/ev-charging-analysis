from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
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


class DemandPoi(Base):
    """A demand-side POI (shopping mall / hospital / office / parking / residential)
    collected as evidence for planning-reference scoring. Not a construction decision."""

    __tablename__ = "demand_pois"
    __table_args__ = (
        UniqueConstraint("poi_id", "demand_type", name="uq_demand_pois_poi_type"),
        Index("ix_demand_pois_type_adcode", "demand_type", "adcode"),
        Index("ix_demand_pois_location", "longitude", "latitude"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    poi_id: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    demand_type: Mapped[str] = mapped_column(String(30), index=True)
    city: Mapped[str] = mapped_column(String(100))
    adcode: Mapped[str] = mapped_column(String(6), index=True)
    longitude: Mapped[Decimal] = mapped_column(Numeric(10, 7))
    latitude: Mapped[Decimal] = mapped_column(Numeric(10, 7))
    collected_at: Mapped[datetime] = mapped_column(DateTime)
    data_source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), index=True)


class DemandRun(Base):
    """Bookkeeping of a demand-POI collection run (resumable)."""

    __tablename__ = "demand_runs"
    __table_args__ = TABLE_OPTIONS
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(24))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    manifest: Mapped[dict] = mapped_column(JSON)
    last_error: Mapped[str | None] = mapped_column(String(500))


class DemandScoreRun(Base):
    """A planning-reference scoring run over demand POIs + grid cells."""

    __tablename__ = "demand_score_runs"
    __table_args__ = TABLE_OPTIONS
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(20))
    algorithm_version: Mapped[str] = mapped_column(String(60))
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    parameters: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)