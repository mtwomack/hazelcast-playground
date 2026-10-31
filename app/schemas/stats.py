"""Response models for the stats endpoints (shown in Swagger).

Fields that only apply to the host or only to a container are optional.
"""
from __future__ import annotations

from pydantic import BaseModel


class CpuStats(BaseModel):
    percent: float
    cores: int


class MemoryStats(BaseModel):
    percent: float | None
    used_mb: float
    total_mb: float | None = None   # host
    limit_mb: float | None = None   # container


class DiskStats(BaseModel):
    available: bool | None = None   # host: False when the OS reports no disk counters
    read_mb_per_s: float | None = None
    write_mb_per_s: float | None = None
    read_total_mb: float | None = None
    write_total_mb: float | None = None


class NetworkStats(BaseModel):
    received_mb_per_s: float | None = None
    sent_mb_per_s: float | None = None
    received_total_mb: float | None = None
    sent_total_mb: float | None = None


class HostStats(BaseModel):
    source: str
    sample_seconds: float
    cpu: CpuStats
    memory: MemoryStats
    disk: DiskStats
    network: NetworkStats


class ContainerStats(HostStats):
    container: str
    status: str


class ContainerUnavailable(BaseModel):
    available: bool = False
    error: str


class AllStats(BaseModel):
    host: HostStats
    hazelcast_container: ContainerStats | ContainerUnavailable
