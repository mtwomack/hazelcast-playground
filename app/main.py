"""
Hazelcast Playground: a small FastAPI app for trying out a Hazelcast cluster
with curl or the Swagger UI (http://localhost:8000/docs).

Values are stored as JSON (HazelcastJsonValue), so you can put any JSON:
objects, lists, strings, numbers. Keys are strings.
"""
from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import hazelcast
from fastapi import Body, Depends, FastAPI, HTTPException, Path, Query, Request
from hazelcast.core import HazelcastJsonValue
from hazelcast.predicate import equal

from app import stats as resource_stats

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("hazelcast_playground")

HZ_MEMBERS = [m.strip() for m in os.getenv("HZ_MEMBERS", "127.0.0.1:5701").split(",") if m.strip()]
HZ_CLUSTER_NAME = os.getenv("HZ_CLUSTER_NAME", "dev")
MAP_SERVICE = "hz:impl:mapService"
HZ_CONTAINER = os.getenv("HZ_CONTAINER", "hazelcast")   # Docker container name for /stats


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Connecting to Hazelcast cluster '%s' at %s", HZ_CLUSTER_NAME, HZ_MEMBERS)
    client = hazelcast.HazelcastClient(
        cluster_members=HZ_MEMBERS,
        cluster_name=HZ_CLUSTER_NAME,
        cluster_connect_timeout=15,   # seconds; fail fast if Hazelcast isn't running
    )
    app.state.hz = client
    try:
        yield
    finally:
        client.shutdown()


app = FastAPI(
    title="Hazelcast Playground",
    description="Put, get, list and delete entries in Hazelcast maps.",
    version="1.0.0",
    lifespan=lifespan,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def get_hz(request: Request):
    return request.app.state.hz


def _map(hz, name: str):
    return hz.get_map(name).blocking()


def _to_hz(value: Any) -> HazelcastJsonValue:
    # Always serialise ourselves: HazelcastJsonValue treats a bare str as raw JSON text.
    return HazelcastJsonValue(json.dumps(value))


def _from_hz(value: Any) -> Any:
    if isinstance(value, HazelcastJsonValue):
        return value.loads()
    return value   # entries written by other apps in another format


MapName = Path(..., description="Map name, e.g. `bankers`", examples=["bankers"])
Key = Path(..., description="Entry key (always a string)", examples=["ab12345"])


# --------------------------------------------------------------------------- #
# Cluster
# --------------------------------------------------------------------------- #
@app.get("/health", tags=["cluster"], summary="Is the Hazelcast client connected?")
def health(hz=Depends(get_hz)):
    members = [str(m.address) for m in hz.cluster_service.get_members()]
    return {
        "connected": hz.lifecycle_service.is_running() and bool(members),
        "cluster_name": HZ_CLUSTER_NAME,
        "members": members,
    }


@app.get("/maps", tags=["cluster"], summary="List the maps in the cluster")
def list_maps(hz=Depends(get_hz)):
    return sorted(o.name for o in hz.get_distributed_objects() if o.service_name == MAP_SERVICE)


# --------------------------------------------------------------------------- #
# Maps
# --------------------------------------------------------------------------- #
@app.get("/maps/{map_name}", tags=["maps"], summary="List entries in a map")
def list_entries(map_name: str = MapName,
                 limit: int = Query(100, ge=1, le=10_000, description="Max entries to return"),
                 hz=Depends(get_hz)):
    m = _map(hz, map_name)
    entries = {}
    for k, v in m.entry_set():
        entries[k] = _from_hz(v)
        if len(entries) >= limit:
            break
    return {"map": map_name, "size": m.size(), "returned": len(entries), "entries": entries}


@app.get("/maps/{map_name}/size", tags=["maps"], summary="Number of entries in a map")
def map_size(map_name: str = MapName, hz=Depends(get_hz)):
    return {"map": map_name, "size": _map(hz, map_name).size()}


@app.get("/maps/{map_name}/keys", tags=["maps"], summary="List keys in a map")
def map_keys(map_name: str = MapName, hz=Depends(get_hz)):
    return sorted(_map(hz, map_name).key_set(), key=str)


@app.get("/maps/{map_name}/search", tags=["maps"],
         summary="Find entries where a JSON field equals a value")
def search(map_name: str = MapName,
           field: str = Query(..., description="JSON field name, e.g. `dept`", examples=["dept"]),
           value: str = Query(..., description="Value to match (numbers and true/false are parsed)", examples=["Risk"]),
           hz=Depends(get_hz)):
    try:
        parsed: Any = json.loads(value)   # "42" -> 42, "true" -> True
    except ValueError:
        parsed = value                    # plain text stays a string
    matches = _map(hz, map_name).entry_set(equal(field, parsed))
    return {k: _from_hz(v) for k, v in matches}


@app.post("/maps/{map_name}/entries", tags=["maps"], summary="Put many entries at once")
def put_many(map_name: str = MapName,
             entries: dict[str, Any] = Body(..., examples=[{
                 "ab12345": {"name": "Alice", "dept": "Risk", "gfcids": ["1001", "1002"]},
                 "cd67890": {"name": "Bob", "dept": "Quant", "gfcids": ["2001"]},
             }]),
             hz=Depends(get_hz)):
    _map(hz, map_name).put_all({k: _to_hz(v) for k, v in entries.items()})
    return {"map": map_name, "written": len(entries)}


@app.delete("/maps/{map_name}", tags=["maps"], summary="Remove every entry in a map")
def clear_map(map_name: str = MapName, hz=Depends(get_hz)):
    m = _map(hz, map_name)
    removed = m.size()
    m.clear()
    return {"map": map_name, "removed": removed}


# --------------------------------------------------------------------------- #
# Entries
# --------------------------------------------------------------------------- #
@app.put("/maps/{map_name}/entries/{key}", tags=["entries"], summary="Create or replace an entry")
def put_entry(map_name: str = MapName, key: str = Key,
              value: Any = Body(..., examples=[{"name": "Alice", "dept": "Risk", "gfcids": ["1001", "1002"]}]),
              ttl: int | None = Query(None, ge=1, description="Seconds until the entry expires (optional)"),
              hz=Depends(get_hz)):
    m = _map(hz, map_name)
    if ttl:
        m.set(key, _to_hz(value), ttl=ttl)
    else:
        m.set(key, _to_hz(value))
    return {"map": map_name, "key": key, "ttl_seconds": ttl, "value": value}


@app.get("/maps/{map_name}/entries/{key}", tags=["entries"], summary="Get one entry")
def get_entry(map_name: str = MapName, key: str = Key, hz=Depends(get_hz)):
    value = _map(hz, map_name).get(key)
    if value is None:
        raise HTTPException(404, f"Key '{key}' not found in map '{map_name}'")
    return {"map": map_name, "key": key, "value": _from_hz(value)}


@app.delete("/maps/{map_name}/entries/{key}", tags=["entries"], summary="Delete one entry")
def delete_entry(map_name: str = MapName, key: str = Key, hz=Depends(get_hz)):
    old = _map(hz, map_name).remove(key)
    if old is None:
        raise HTTPException(404, f"Key '{key}' not found in map '{map_name}'")
    return {"map": map_name, "key": key, "deleted": True}


# --------------------------------------------------------------------------- #
# Resource stats
# --------------------------------------------------------------------------- #
SampleSeconds = Query(1.0, ge=0.1, le=10, description="How long to measure for (rates are per second over this window)")


def _hazelcast_container_stats(container: str, interval: float) -> dict:
    try:
        return resource_stats.container_stats(container, interval)
    except Exception as e:  # noqa: BLE001
        name = type(e).__name__
        if name == "NotFound":
            raise HTTPException(404, f"Docker container '{container}' not found. Check the name with: docker ps")
        raise HTTPException(503, f"Can't read Docker stats ({name}): is Docker Desktop running?")


@app.get("/stats", tags=["stats"],
         summary="CPU, memory, disk and network for this machine and the Hazelcast container")
def stats_all(interval: float = SampleSeconds,
              container: str = Query(HZ_CONTAINER, description="Hazelcast Docker container name")):
    host = resource_stats.host_stats(interval)
    try:
        hz = _hazelcast_container_stats(container, interval)
    except HTTPException as e:
        hz = {"available": False, "error": e.detail}
    return {"host": host, "hazelcast_container": hz}


@app.get("/stats/host", tags=["stats"], summary="CPU, memory, disk and network for this machine")
def stats_host(interval: float = SampleSeconds):
    return resource_stats.host_stats(interval)


@app.get("/stats/hazelcast", tags=["stats"],
         summary="CPU, memory, disk and network for the Hazelcast Docker container (like `docker stats`)")
def stats_hazelcast(interval: float = SampleSeconds,
                    container: str = Query(HZ_CONTAINER, description="Hazelcast Docker container name")):
    return _hazelcast_container_stats(container, interval)
