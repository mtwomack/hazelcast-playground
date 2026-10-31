"""
Stats service: CPU, memory, disk read/write and network I/O.

- Host stats come from psutil (the machine running this API).
- Container stats come from the Docker Engine API (the Hazelcast container),
  the same numbers `docker stats` shows.

Rates (per second) are measured over a short sample window; totals are
cumulative since the machine / container started.
"""
from __future__ import annotations

import time
from typing import Any

import psutil

MB = 1024 * 1024


class ContainerNotFound(LookupError):
    """No Docker container with that name."""


class DockerUnavailable(RuntimeError):
    """Docker isn't running or can't be reached."""


def _mb(n: float) -> float:
    return round(n / MB, 2)


# --------------------------------------------------------------------------- #
# Host (psutil)
# --------------------------------------------------------------------------- #
def host_stats(interval: float = 1.0) -> dict[str, Any]:
    """Sample the host for `interval` seconds and return CPU, memory, disk and network stats."""
    disk0 = psutil.disk_io_counters()
    net0 = psutil.net_io_counters()
    cpu = psutil.cpu_percent(interval=interval)   # blocks for `interval`, measures over it
    disk1 = psutil.disk_io_counters()
    net1 = psutil.net_io_counters()
    mem = psutil.virtual_memory()

    def rate(a, b, attr):
        return _mb((getattr(b, attr) - getattr(a, attr)) / interval)

    disk = {"available": False}
    if disk0 and disk1:   # None on some systems / containers without block devices
        disk = {
            "available": True,
            "read_mb_per_s": rate(disk0, disk1, "read_bytes"),
            "write_mb_per_s": rate(disk0, disk1, "write_bytes"),
            "read_total_mb": _mb(disk1.read_bytes),
            "write_total_mb": _mb(disk1.write_bytes),
        }

    return {
        "source": "host",
        "sample_seconds": interval,
        "cpu": {"percent": cpu, "cores": psutil.cpu_count(logical=True)},
        "memory": {
            "percent": mem.percent,
            "used_mb": _mb(mem.total - mem.available),
            "total_mb": _mb(mem.total),
        },
        "disk": disk,
        "network": {
            "received_mb_per_s": rate(net0, net1, "bytes_recv"),
            "sent_mb_per_s": rate(net0, net1, "bytes_sent"),
            "received_total_mb": _mb(net1.bytes_recv),
            "sent_total_mb": _mb(net1.bytes_sent),
        },
    }


# --------------------------------------------------------------------------- #
# Docker container (Hazelcast)
# --------------------------------------------------------------------------- #
def _blkio_bytes(raw: dict) -> tuple[int, int]:
    """Total (read, write) bytes from Docker's blkio stats (cgroup v1 or v2 layout)."""
    entries = (raw.get("blkio_stats") or {}).get("io_service_bytes_recursive") or []
    read = sum(e.get("value", 0) for e in entries if str(e.get("op", "")).lower() == "read")
    write = sum(e.get("value", 0) for e in entries if str(e.get("op", "")).lower() == "write")
    return read, write


def _net_bytes(raw: dict) -> tuple[int, int]:
    nets = (raw.get("networks") or {}).values()
    return sum(n.get("rx_bytes", 0) for n in nets), sum(n.get("tx_bytes", 0) for n in nets)


def parse_container_stats(raw: dict, prev: dict | None = None, interval: float | None = None) -> dict[str, Any]:
    """Turn one Docker stats snapshot into CPU / memory / disk / network figures.

    CPU % uses the snapshot's own cpu_stats vs precpu_stats (the same formula as `docker stats`).
    If `prev` and `interval` are given, disk and network rates are computed between the two.
    """
    cpu, pre = raw.get("cpu_stats") or {}, raw.get("precpu_stats") or {}
    cpu_delta = (cpu.get("cpu_usage") or {}).get("total_usage", 0) - (pre.get("cpu_usage") or {}).get("total_usage", 0)
    sys_delta = cpu.get("system_cpu_usage", 0) - pre.get("system_cpu_usage", 0)
    cores = cpu.get("online_cpus") or len((cpu.get("cpu_usage") or {}).get("percpu_usage") or []) or 1
    cpu_pct = round(cpu_delta / sys_delta * cores * 100, 2) if cpu_delta > 0 and sys_delta > 0 else 0.0

    m = raw.get("memory_stats") or {}
    mstats = m.get("stats") or {}
    cache = mstats.get("inactive_file", mstats.get("total_inactive_file", 0))   # v2 / v1; same as docker CLI
    used = max(m.get("usage", 0) - cache, 0)
    limit = m.get("limit", 0)

    read, write = _blkio_bytes(raw)
    rx, tx = _net_bytes(raw)

    out: dict[str, Any] = {
        "cpu": {"percent": cpu_pct, "cores": cores},
        "memory": {
            "percent": round(used / limit * 100, 2) if limit else None,
            "used_mb": _mb(used),
            "limit_mb": _mb(limit),
        },
        "disk": {"read_total_mb": _mb(read), "write_total_mb": _mb(write)},
        "network": {"received_total_mb": _mb(rx), "sent_total_mb": _mb(tx)},
    }
    if prev is not None and interval:
        pread, pwrite = _blkio_bytes(prev)
        prx, ptx = _net_bytes(prev)
        out["disk"].update(read_mb_per_s=_mb(max(read - pread, 0) / interval),
                           write_mb_per_s=_mb(max(write - pwrite, 0) / interval))
        out["network"].update(received_mb_per_s=_mb(max(rx - prx, 0) / interval),
                              sent_mb_per_s=_mb(max(tx - ptx, 0) / interval))
    return out


def container_stats(name: str, interval: float = 1.0, client=None) -> dict[str, Any]:
    """Stats for a running Docker container, sampled over `interval` seconds.

    Raises ContainerNotFound if there's no such container, DockerUnavailable if Docker can't be reached.
    """
    try:
        import docker   # imported lazily so the API still starts without Docker

        client = client or docker.from_env()
        container = client.containers.get(name)
        first = container.stats(stream=False)
        time.sleep(interval)
        second = container.stats(stream=False)
    except Exception as e:  # noqa: BLE001 - docker raises many exception types
        if type(e).__name__ == "NotFound":
            raise ContainerNotFound(f"Docker container '{name}' not found. Check the name with: docker ps") from e
        raise DockerUnavailable(f"Can't read Docker stats ({type(e).__name__}): is Docker Desktop running?") from e
    return {
        "source": "container",
        "container": container.name,
        "status": container.status,
        "sample_seconds": interval,
        **parse_container_stats(second, prev=first, interval=interval),
    }


def all_stats(container: str, interval: float = 1.0) -> dict[str, Any]:
    """Host stats plus container stats; the container part reports its error instead of failing."""
    host = host_stats(interval)
    try:
        hz = container_stats(container, interval)
    except (ContainerNotFound, DockerUnavailable) as e:
        hz = {"available": False, "error": str(e)}
    return {"host": host, "hazelcast_container": hz}
