"""
Hazelcast Playground: a small FastAPI app for trying out a Hazelcast cluster
with curl or the Swagger UI (http://localhost:8000/docs).

Values are stored as JSON (HazelcastJsonValue), so you can put any JSON:
objects, lists, strings, numbers. Keys are strings.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Body, Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse

from app import stats as resource_stats
from app.services import hazelcast as hz_service
from app.services.hazelcast import EntryNotFound
from app.util.hazelcast import (
    HZ_CLUSTER_NAME,
    HZ_CONTAINER,
    HZ_MEMBERS,
    MAP_SERVICE,  # noqa: F401  (re-exported for tests)
    create_client,
    get_hz,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("hazelcast_playground")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Connecting to Hazelcast cluster '%s' at %s", HZ_CLUSTER_NAME, HZ_MEMBERS)
    client = create_client()   # fails after 15s if Hazelcast isn't running
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


@app.exception_handler(EntryNotFound)
def entry_not_found(_request: Request, exc: EntryNotFound):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


MapName = Path(..., description="Map name, e.g. `bankers`", examples=["bankers"])
Key = Path(..., description="Entry key (always a string)", examples=["ab12345"])


# --------------------------------------------------------------------------- #
# Cluster
# --------------------------------------------------------------------------- #
@app.get("/health", tags=["cluster"], summary="Is the Hazelcast client connected?")
def health(hz=Depends(get_hz)):
    return hz_service.health(hz)


@app.get("/maps", tags=["cluster"], summary="List the maps in the cluster")
def list_maps(hz=Depends(get_hz)):
    return hz_service.list_maps(hz)


# --------------------------------------------------------------------------- #
# Maps
# --------------------------------------------------------------------------- #
@app.get("/maps/{map_name}", tags=["maps"], summary="List entries in a map")
def list_entries(map_name: str = MapName,
                 limit: int = Query(100, ge=1, le=10_000, description="Max entries to return"),
                 hz=Depends(get_hz)):
    return hz_service.list_entries(hz, map_name, limit)


@app.get("/maps/{map_name}/size", tags=["maps"], summary="Number of entries in a map")
def map_size(map_name: str = MapName, hz=Depends(get_hz)):
    return hz_service.map_size(hz, map_name)


@app.get("/maps/{map_name}/keys", tags=["maps"], summary="List keys in a map")
def map_keys(map_name: str = MapName, hz=Depends(get_hz)):
    return hz_service.map_keys(hz, map_name)


@app.get("/maps/{map_name}/search", tags=["maps"],
         summary="Find entries where a JSON field equals a value")
def search(map_name: str = MapName,
           field: str = Query(..., description="JSON field name, e.g. `dept`", examples=["dept"]),
           value: str = Query(..., description="Value to match (numbers and true/false are parsed)", examples=["Risk"]),
           hz=Depends(get_hz)):
    return hz_service.search(hz, map_name, field, hz_service.parse_search_value(value))


@app.post("/maps/{map_name}/entries", tags=["maps"], summary="Put many entries at once")
def put_many(map_name: str = MapName,
             entries: dict[str, Any] = Body(..., examples=[{
                 "ab12345": {"name": "Alice", "dept": "Risk", "gfcids": ["1001", "1002"]},
                 "cd67890": {"name": "Bob", "dept": "Quant", "gfcids": ["2001"]},
             }]),
             hz=Depends(get_hz)):
    return hz_service.put_many(hz, map_name, entries)


@app.delete("/maps/{map_name}", tags=["maps"], summary="Remove every entry in a map")
def clear_map(map_name: str = MapName, hz=Depends(get_hz)):
    return hz_service.clear_map(hz, map_name)


# --------------------------------------------------------------------------- #
# Entries
# --------------------------------------------------------------------------- #
@app.put("/maps/{map_name}/entries/{key}", tags=["entries"], summary="Create or replace an entry")
def put_entry(map_name: str = MapName, key: str = Key,
              value: Any = Body(..., examples=[{"name": "Alice", "dept": "Risk", "gfcids": ["1001", "1002"]}]),
              ttl: int | None = Query(None, ge=1, description="Seconds until the entry expires (optional)"),
              hz=Depends(get_hz)):
    return hz_service.put_entry(hz, map_name, key, value, ttl)


@app.get("/maps/{map_name}/entries/{key}", tags=["entries"], summary="Get one entry")
def get_entry(map_name: str = MapName, key: str = Key, hz=Depends(get_hz)):
    return hz_service.get_entry(hz, map_name, key)


@app.delete("/maps/{map_name}/entries/{key}", tags=["entries"], summary="Delete one entry")
def delete_entry(map_name: str = MapName, key: str = Key, hz=Depends(get_hz)):
    return hz_service.delete_entry(hz, map_name, key)


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
