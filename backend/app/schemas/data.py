from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Page


class SourceInfo(BaseModel):
    simulated: bool
    updatedAt: str | None
    period: str
    label: str
    boundary: str = "阿里云 DataV.GeoAtlas（前端展示边界）"
    note: str


class Metric(BaseModel):
    key: str
    label: str
    value: float | None
    unit: str
    change: str
    yoy: float | None = None
    qoq: float | None = None
    sparkline: list[int] | None = None


class City(BaseModel):
    id: int
    code: str
    adcode: str
    name: str
    shortName: str
    level: str
    parentAdcode: str | None
    center: list[float]
    areaKm2: float | None
    region: str | None
    stations: int | None
    piles: int | None
    fastRate: float | None
    growth: float | None
    density: float | None
    statisticDate: date | None
    simulated: bool


class Overview(BaseModel):
    metrics: list[Metric]
    sourceInfo: SourceInfo
    statisticDate: date | None


class TrendPoint(BaseModel):
    period: str
    statisticDate: date
    stations: int
    piles: int


class TrendResult(BaseModel):
    adcode: str
    items: list[TrendPoint]
    sourceInfo: SourceInfo


class RankingResult(BaseModel):
    metric: str
    unit: str
    items: list[City]
    sourceInfo: SourceInfo


class StationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    poi_id: str | None = Field(default=None, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    province: str = Field(min_length=1, max_length=100)
    city: str = Field(min_length=1, max_length=100)
    district: str | None = Field(default=None, max_length=100)
    adcode: str = Field(pattern=r"^\d{6}$")
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    station_type: str | None = Field(default=None, max_length=40)
    source: str = Field(min_length=1, max_length=200)
    collected_at: datetime
    public_charger_count: int | None = Field(default=None, ge=0)
    data_source_id: int = Field(gt=0)


class Station(BaseModel):
    id: str
    poiId: str | None
    name: str
    address: str | None
    province: str
    city: str
    district: str | None
    adcode: str
    cityCode: str
    position: list[float]
    type: str | None
    piles: int | None
    source: str
    collectedAt: datetime
    simulated: bool
    classification: str | None = None
    reviewStatus: str | None = None
    confidence: str | None = None
    needsReview: bool | None = None
    batch: str | None = None
    rulesVersion: str | None = None
    completenessWarning: bool = False


class Source(BaseModel):
    id: int
    name: str
    sourceType: str
    sourceUrl: str | None
    description: str | None
    updatedAt: datetime
    simulated: bool


class SourcesResult(BaseModel):
    items: list[Source]
    sourceInfo: SourceInfo


class RegionsResult(BaseModel):
    items: list[City]
    sourceInfo: SourceInfo


class StationPage(Page[Station]):
    sourceInfo: SourceInfo


class AMapStationResult(BaseModel):
    items: list[Station]
    cityCode: str
    page: int
    pageSize: int
    returnedCount: int
    skippedCount: int
    mayHaveMore: bool
    queriedAt: datetime
    notice: str
    sourceInfo: SourceInfo
