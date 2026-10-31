"""
Low-level Hazelcast helpers: connecting, getting maps and converting values.

No FastAPI or HTTP here; used by the services and the scripts.
"""
from __future__ import annotations

import json
from typing import Any

import hazelcast
from hazelcast.core import HazelcastJsonValue

from app.core.config import HZ_CLUSTER_NAME, HZ_MEMBERS

MAP_SERVICE = "hz:impl:mapService"   # Hazelcast's internal service name for maps (a constant, not a setting)


def create_client(members: list[str] | None = None, cluster_name: str | None = None,
                  connect_timeout: float = 15) -> hazelcast.HazelcastClient:
    """Connect to the cluster. Raises if no member is reachable within `connect_timeout` seconds."""
    return hazelcast.HazelcastClient(
        cluster_members=members or HZ_MEMBERS,
        cluster_name=cluster_name or HZ_CLUSTER_NAME,
        cluster_connect_timeout=connect_timeout,
    )


def get_map(hz, name: str):
    """Blocking proxy for a map (calls return values, not futures)."""
    return hz.get_map(name).blocking()


def list_map_names(hz) -> list[str]:
    return sorted(o.name for o in hz.get_distributed_objects() if o.service_name == MAP_SERVICE)


def to_hz(value: Any) -> HazelcastJsonValue:
    """Store any JSON value. Always serialise ourselves: HazelcastJsonValue treats a bare str as raw JSON text."""
    return HazelcastJsonValue(json.dumps(value))


def from_hz(value: Any) -> Any:
    """Read a stored value back as Python data."""
    if isinstance(value, HazelcastJsonValue):
        return value.loads()
    return value   # entries written by other apps in another format
