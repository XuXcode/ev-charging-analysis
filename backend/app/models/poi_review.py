"""Append-only review evidence keeps originals and correction decisions recoverable."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.entities import TABLE_OPTIONS, utc_now


class PoiReviewEvent(Base):
    __tablename__ = "poi_review_events"
    __table_args__ = TABLE_OPTIONS
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("charging_stations.id"), index=True)
    event_hash: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(100))
    before: Mapped[dict] = mapped_column(JSON)
    after: Mapped[dict] = mapped_column(JSON)
    evidence: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class BoundaryRevision(Base):
    __tablename__ = "boundary_revisions"
    __table_args__ = TABLE_OPTIONS
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    adcode: Mapped[str] = mapped_column(String(6), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    geometry: Mapped[dict] = mapped_column(JSON)
    source_url: Mapped[str] = mapped_column(String(1000))
    coordinate_system: Mapped[str] = mapped_column(String(20))
    fetched_at: Mapped[datetime] = mapped_column(DateTime)
    reason: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
