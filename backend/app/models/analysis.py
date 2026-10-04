"""Additive governance and reproducible analysis records; raw stations stay intact."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.entities import TABLE_OPTIONS, utc_now


class PoiQuality(Base):
    __tablename__ = "poi_quality"
    __table_args__ = (
        Index("ix_poi_quality_filter", "classification", "review_status", "needs_review"),
        TABLE_OPTIONS,
    )
    station_id: Mapped[int] = mapped_column(ForeignKey("charging_stations.id"), primary_key=True)
    classification: Mapped[str] = mapped_column(String(30))
    confidence: Mapped[str] = mapped_column(String(20))
    reasons: Mapped[list] = mapped_column(JSON)
    evidence: Mapped[dict] = mapped_column(JSON)
    needs_review: Mapped[bool] = mapped_column(Boolean)
    review_status: Mapped[str] = mapped_column(String(20), default="unreviewed")
    review_note: Mapped[str | None] = mapped_column(String(1000))
    rules_version: Mapped[str] = mapped_column(String(40))
    run_id: Mapped[str] = mapped_column(ForeignKey("collection_runs.id"), index=True)
    classified_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)


class AnalysisSnapshot(Base):
    __tablename__ = "analysis_snapshots"
    __table_args__ = (Index("ix_analysis_snapshot_latest", "status", "computed_at"), TABLE_OPTIONS)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(20))
    algorithm_version: Mapped[str] = mapped_column(String(40))
    run_id: Mapped[str] = mapped_column(ForeignKey("collection_runs.id"), index=True)
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    boundary_hash: Mapped[str] = mapped_column(String(64))
    parameters: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class AnalysisBoundary(Base):
    __tablename__ = "analysis_boundaries"
    __table_args__ = TABLE_OPTIONS
    adcode: Mapped[str] = mapped_column(String(6), primary_key=True)
    city_code: Mapped[str] = mapped_column(String(6), index=True)
    name: Mapped[str] = mapped_column(String(100))
    level: Mapped[str] = mapped_column(String(20))
    geometry: Mapped[dict] = mapped_column(JSON)
    source_url: Mapped[str] = mapped_column(String(1000))
    coordinate_system: Mapped[str] = mapped_column(String(20))
    content_hash: Mapped[str] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class AnalysisScopeQuality(Base):
    __tablename__ = "analysis_scope_quality"
    __table_args__ = TABLE_OPTIONS
    adcode: Mapped[str] = mapped_column(String(6), primary_key=True)
    city_code: Mapped[str] = mapped_column(String(6), index=True)
    name: Mapped[str] = mapped_column(String(100))
    completeness_warning: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str | None] = mapped_column(String(500))
    run_id: Mapped[str] = mapped_column(ForeignKey("collection_runs.id"), index=True)
