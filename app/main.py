"""
Hazelcast Playground: a small FastAPI app for trying out a Hazelcast cluster
with curl or the Swagger UI (http://localhost:8000/docs).

This file only wires the app together: the Hazelcast connection, error
handling and routers. Endpoints live in app/routers, logic in app/services.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.clients.hazelcast_client import create_client
from app.core.config import API_V1_PREFIX, HZ_CLUSTER_NAME, HZ_MEMBERS
from app.routers import v1
from app.services.hazelcast_service import EntryNotFound
from app.services.stats_service import ContainerNotFound, DockerUnavailable

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
    description="Put, get, list and delete entries in Hazelcast maps, and watch resource usage.",
    version="1.0.0",
    lifespan=lifespan,
)


# Service errors -> HTTP status codes
def _error(status: int):
    def handler(_request: Request, exc: Exception):
        return JSONResponse(status_code=status, content={"detail": str(exc)})
    return handler


app.add_exception_handler(EntryNotFound, _error(404))
app.add_exception_handler(ContainerNotFound, _error(404))
app.add_exception_handler(DockerUnavailable, _error(503))

# API versions. Every v1 endpoint lives under /api/v1.
# For a breaking change, add app/routers/v2 and include it under /api/v2 alongside v1.
app.include_router(v1.router, prefix=API_V1_PREFIX)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")
