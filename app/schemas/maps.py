"""Response models for the cluster, map and entry endpoints (shown in Swagger)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class HealthResponse(BaseModel):
    connected: bool
    cluster_name: str
    members: list[str]


class EntriesResponse(BaseModel):
    map: str
    size: int
    returned: int
    entries: dict[str, Any]


class SizeResponse(BaseModel):
    map: str
    size: int


class PutManyResponse(BaseModel):
    map: str
    written: int


class ClearResponse(BaseModel):
    map: str
    removed: int


class PutEntryResponse(BaseModel):
    map: str
    key: str
    ttl_seconds: int | None
    value: Any


class EntryResponse(BaseModel):
    map: str
    key: str
    value: Any


class DeleteResponse(BaseModel):
    map: str
    key: str
    deleted: bool
