from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    code: int = 200
    message: str = "success"
    data: T


class ErrorResponse(BaseModel):
    code: int
    message: str
    data: dict | list | None = None


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    pageSize: int
