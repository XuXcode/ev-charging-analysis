"""Source-reported metrics, independent of POI samples and complete legacy snapshots."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.entities import TABLE_OPTIONS, utc_now


class PublicStatistic(Base):
    __tablename__ = "public_statistics"
    __table_args__ = (
        Index("ix_public_statistic_lookup", "region_adcode", "year", "metric"),
        TABLE_OPTIONS,
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    region_adcode: Mapped[str] = mapped_column(String(6))
    year: Mapped[int] = mapped_column(Integer)
    metric: Mapped[str] = mapped_column(String(50))
    value: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    unit: Mapped[str] = mapped_column(String(20))
    source_name: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str] = mapped_column(String(1000))
    source_kind: Mapped[str] = mapped_column(String(20))
    scope_description: Mapped[str] = mapped_column(String(1000))
    file_name: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64))
    row_number: Mapped[int] = mapped_column(Integer)
    record_hash: Mapped[str] = mapped_column(String(64), unique=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
