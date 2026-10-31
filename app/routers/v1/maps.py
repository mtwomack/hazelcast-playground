"""Cluster, map and entry endpoints. Each one validates input and calls the Hazelcast service."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Path, Query

from app.dependencies import get_hz
from app.schemas.maps import (
    ClearResponse,
    DeleteResponse,
    EntriesResponse,
    EntryResponse,
    HealthResponse,
    PutEntryResponse,
    PutManyResponse,
    SizeResponse,
)
from app.services import hazelcast_service as svc

router = APIRouter()

MapName = Path(..., description="Map name, e.g. `bankers`", examples=["bankers"])
Key = Path(..., description="Entry key (always a string)", examples=["ab12345"])


# --------------------------------------------------------------------------- #
# Cluster
# --------------------------------------------------------------------------- #
@router.get("/health", tags=["cluster"], response_model=HealthResponse,
            summary="Is the Hazelcast client connected?")
def health(hz=Depends(get_hz)):
    return svc.health(hz)


@router.get("/maps", tags=["cluster"], response_model=list[str], summary="List the maps in the cluster")
def list_maps(hz=Depends(get_hz)):
    return svc.list_maps(hz)


# --------------------------------------------------------------------------- #
# Maps
# --------------------------------------------------------------------------- #
@router.get("/maps/{map_name}", tags=["maps"], response_model=EntriesResponse, summary="List entries in a map")
def list_entries(map_name: str = MapName,
                 limit: int = Query(100, ge=1, le=10_000, description="Max entries to return"),
                 hz=Depends(get_hz)):
    return svc.list_entries(hz, map_name, limit)


@router.get("/maps/{map_name}/size", tags=["maps"], response_model=SizeResponse,
            summary="Number of entries in a map")
def map_size(map_name: str = MapName, hz=Depends(get_hz)):
    return svc.map_size(hz, map_name)


@router.get("/maps/{map_name}/keys", tags=["maps"], response_model=list[str], summary="List keys in a map")
def map_keys(map_name: str = MapName, hz=Depends(get_hz)):
    return svc.map_keys(hz, map_name)


@router.get("/maps/{map_name}/search", tags=["maps"], response_model=dict[str, Any],
            summary="Find entries where a JSON field equals a value")
def search(map_name: str = MapName,
           field: str = Query(..., description="JSON field name, e.g. `dept`", examples=["dept"]),
           value: str = Query(..., description="Value to match (numbers and true/false are parsed)", examples=["Risk"]),
           hz=Depends(get_hz)):
    return svc.search(hz, map_name, field, svc.parse_search_value(value))


@router.post("/maps/{map_name}/entries", tags=["maps"], response_model=PutManyResponse,
             summary="Put many entries at once")
def put_many(map_name: str = MapName,
             entries: dict[str, Any] = Body(..., examples=[{
                 "ab12345": {"name": "Alice", "dept": "Risk", "gfcids": ["1001", "1002"]},
                 "cd67890": {"name": "Bob", "dept": "Quant", "gfcids": ["2001"]},
             }]),
             hz=Depends(get_hz)):
    return svc.put_many(hz, map_name, entries)


@router.delete("/maps/{map_name}", tags=["maps"], response_model=ClearResponse,
               summary="Remove every entry in a map")
def clear_map(map_name: str = MapName, hz=Depends(get_hz)):
    return svc.clear_map(hz, map_name)


# --------------------------------------------------------------------------- #
# Entries
# --------------------------------------------------------------------------- #
@router.put("/maps/{map_name}/entries/{key}", tags=["entries"], response_model=PutEntryResponse,
            summary="Create or replace an entry")
def put_entry(map_name: str = MapName, key: str = Key,
              value: Any = Body(..., examples=[{"name": "Alice", "dept": "Risk", "gfcids": ["1001", "1002"]}]),
              ttl: int | None = Query(None, ge=1, description="Seconds until the entry expires (optional)"),
              hz=Depends(get_hz)):
    return svc.put_entry(hz, map_name, key, value, ttl)


@router.get("/maps/{map_name}/entries/{key}", tags=["entries"], response_model=EntryResponse,
            summary="Get one entry")
def get_entry(map_name: str = MapName, key: str = Key, hz=Depends(get_hz)):
    return svc.get_entry(hz, map_name, key)


@router.delete("/maps/{map_name}/entries/{key}", tags=["entries"], response_model=DeleteResponse,
               summary="Delete one entry")
def delete_entry(map_name: str = MapName, key: str = Key, hz=Depends(get_hz)):
    return svc.delete_entry(hz, map_name, key)
