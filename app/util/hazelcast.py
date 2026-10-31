"""
Hazelcast helpers and settings shared by the API and the scripts.

Settings come from environment variables, loaded from the `.env` file in the
project root if one exists (see `.env.example`). Real environment variables
take priority over `.env`. Set ENV_FILE to load a different file.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import hazelcast
from dotenv import load_dotenv
from fastapi import Request
from hazelcast.core import HazelcastJsonValue

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(os.getenv("ENV_FILE") or PROJECT_ROOT / ".env")

# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
HZ_MEMBERS = [m.strip() for m in os.getenv("HZ_MEMBERS", "127.0.0.1:5701").split(",") if m.strip()]
HZ_CLUSTER_NAME = os.getenv("HZ_CLUSTER_NAME", "dev")
HZ_CONTAINER = os.getenv("HZ_CONTAINER", "hazelcast")   # Docker container name for /stats

MAP_SERVICE = "hz:impl:mapService"   # Hazelcast's internal service name for maps (a constant, not a setting)


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #
def create_client(members: list[str] | None = None, cluster_name: str | None = None,
                  connect_timeout: float = 15) -> hazelcast.HazelcastClient:
    """Connect to the cluster. Raises if no member is reachable within `connect_timeout` seconds."""
    return hazelcast.HazelcastClient(
        cluster_members=members or HZ_MEMBERS,
        cluster_name=cluster_name or HZ_CLUSTER_NAME,
        cluster_connect_timeout=connect_timeout,
    )


def get_hz(request: Request):
    """FastAPI dependency: the client created at startup."""
    return request.app.state.hz


# --------------------------------------------------------------------------- #
# Maps and values
# --------------------------------------------------------------------------- #
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
