"""Resource stats endpoints. Each one validates input and calls the stats service."""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.config import HZ_CONTAINER
from app.schemas.stats import AllStats, ContainerStats, HostStats
from app.services import stats_service

router = APIRouter(prefix="/stats", tags=["stats"])

SampleSeconds = Query(1.0, ge=0.1, le=10, description="How long to measure for (rates are per second over this window)")
Container = Query(HZ_CONTAINER, description="Hazelcast Docker container name")


@router.get("", response_model=AllStats, response_model_exclude_none=True,
            summary="CPU, memory, disk and network for this machine and the Hazelcast container")
def stats_all(interval: float = SampleSeconds, container: str = Container):
    return stats_service.all_stats(container, interval)


@router.get("/host", response_model=HostStats, response_model_exclude_none=True,
            summary="CPU, memory, disk and network for this machine")
def stats_host(interval: float = SampleSeconds):
    return stats_service.host_stats(interval)


@router.get("/hazelcast", response_model=ContainerStats, response_model_exclude_none=True,
            summary="CPU, memory, disk and network for the Hazelcast Docker container (like `docker stats`)")
def stats_hazelcast(interval: float = SampleSeconds, container: str = Container):
    return stats_service.container_stats(container, interval)
