"""Explicit real-input contracts; missing service capacity stays nullable."""

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class EvidencePoint(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    position: tuple[float, float]
    adcode: str = Field(pattern=r"^43\d{4}$")
    source: str = Field(min_length=1, max_length=200)
    sourceUrl: HttpUrl
    year: int = Field(ge=2000, le=2100)
    unit: str = Field(min_length=1, max_length=100)
    poiId: str | None = Field(None, max_length=100)
    category: Literal["parking", "commercial", "office", "transport", "residential"] | None = None
    variables: dict[str, float | None] = Field(default_factory=dict)
    station_capacity: float | None = Field(None, ge=0)
    charger_count: int | None = Field(None, ge=0)
    power: float | None = Field(None, ge=0)
    waiting_time: float | None = Field(None, ge=0)

    @model_validator(mode="after")
    def check_coordinate(self):
        lon, lat = self.position
        if (
            not math.isfinite(lon)
            or not math.isfinite(lat)
            or not (108 <= lon <= 115 and 24 <= lat <= 31)
        ):
            raise ValueError("仅接受湖南范围内声明为GCJ-02的真实观测坐标")
        if any(v is not None and v < 0 for v in self.variables.values()):
            raise ValueError("需求变量不得为负")
        return self


class DatasetImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["demand", "candidates", "capacity"]
    name: str = Field(min_length=1, max_length=120)
    batch: str = Field(min_length=1, max_length=100)
    coordinateSystem: Literal["GCJ-02"]
    records: list[EvidencePoint] = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def check_records(self):
        if len({r.id for r in self.records}) != len(self.records):
            raise ValueError("同一数据集记录ID不可重复")
        if self.kind == "candidates" and any(not r.poiId or not r.category for r in self.records):
            raise ValueError("候选设施需真实POI ID和设施类别")
        return self


class OptimizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    demandDatasetId: str = Field(pattern=r"^[a-f0-9]{32}$")
    candidateDatasetId: str = Field(pattern=r"^[a-f0-9]{32}$")
    scopeCode: str = Field(pattern=r"^43\d{4}$")
    weights: dict[str, float]
    n: int = Field(ge=0, le=100, strict=True)
    algorithm: Literal["greedy", "mclp"] = "greedy"
    metric: Literal["straightDistanceM", "durationSeconds"] = "straightDistanceM"
    threshold: float = Field(gt=0, le=50000)
    minExistingDistanceM: float = Field(100, ge=0, le=5000)
    dedupDistanceM: float = Field(20, ge=0, le=500)
    timeLimitSeconds: int = Field(30, ge=1, le=120)


class DemandPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    datasetId: str = Field(pattern=r"^[a-f0-9]{32}$")
    weights: dict[str, float]
