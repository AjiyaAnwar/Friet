"""
Common API response envelope.

Per Phase 1: "Define base API response contracts for all commercial
endpoints." Every endpoint in this service returns one of these two
shapes - success or paginated - so the frontend (or Team 1 reviewing
our contracts) only has to learn ONE response format, not one per
endpoint.
"""

from typing import Generic, TypeVar, Optional
from pydantic import BaseModel

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str
    field: Optional[str] = None


class APIResponse(BaseModel, Generic[T]):
    success: bool = True
    data: Optional[T] = None
    errors: list[ErrorDetail] = []


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total_count: int
    total_pages: int


class PaginatedResponse(BaseModel, Generic[T]):
    success: bool = True
    data: list[T]
    meta: PaginationMeta
