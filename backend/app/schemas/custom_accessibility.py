"""Interactive queries never become county representative statistics."""

from typing import Literal

from pydantic import BaseModel, Field


class CustomOrigin(BaseModel):
    longitude: float = Field(ge=108, le=115, allow_inf_nan=False)
    latitude: float = Field(ge=24, le=31, allow_inf_nan=False)
    name: str = Field(default="地图选点", max_length=120)


class CustomQuery(BaseModel):
    origin: CustomOrigin
    candidate_count: Literal[3, 5] = 3
    max_api_calls: int = Field(default=0, ge=0, le=5)
    plan_id: str | None = Field(default=None, max_length=64)
