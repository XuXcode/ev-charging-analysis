"""Immutable imported evidence and reproducible planning results."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.entities import TABLE_OPTIONS, utc_now


class PlanningDataset(Base):
    __tablename__ = "planning_datasets"
    __table_args__ = TABLE_OPTIONS
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(120))
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    metadata_json: Mapped[dict] = mapped_column(JSON)
    records: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class PlanningRun(Base):
    __tablename__ = "planning_runs"
    __table_args__ = TABLE_OPTIONS
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    algorithm_version: Mapped[str] = mapped_column(String(60))
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    parameters: Mapped[dict] = mapped_column(JSON)
    inputs: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
