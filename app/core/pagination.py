"""Cursor-based pagination helpers."""

import base64
import json
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageMeta(BaseModel):
    next_cursor: str | None = None
    has_more: bool = False
    limit: int = 50


class PaginatedResponse(BaseModel, Generic[T]):
    data: list[T]
    meta: PageMeta
    errors: list[Any] = Field(default_factory=list)


def encode_cursor(value: UUID | str) -> str:
    payload = {"c": str(value)}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def decode_cursor(cursor: str) -> str:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        return payload["c"]
    except (KeyError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("Invalid cursor") from exc
