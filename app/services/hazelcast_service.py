"""
Hazelcast service layer: the logic behind each Hazelcast endpoint.

Each function takes a connected Hazelcast client (`hz`) as its first argument
and returns plain Python data. Nothing here knows about FastAPI or HTTP, so
these functions can be reused from scripts, tests or other apps. Missing
entries raise `EntryNotFound`, which the API turns into a 404.
"""
from __future__ import annotations

import json
from typing import Any

from hazelcast.predicate import equal

from app.clients.hazelcast_client import from_hz, get_map, list_map_names, to_hz
from app.core.config import HZ_CLUSTER_NAME


class EntryNotFound(LookupError):
    """The key doesn't exist in the map."""

    def __init__(self, map_name: str, key: str):
        self.map_name, self.key = map_name, key
        super().__init__(f"Key '{key}' not found in map '{map_name}'")


# --------------------------------------------------------------------------- #
# Cluster
# --------------------------------------------------------------------------- #
def health(hz) -> dict:
    """Connection status and the addresses of the cluster members."""
    members = [str(m.address) for m in hz.cluster_service.get_members()]
    return {
        "connected": hz.lifecycle_service.is_running() and bool(members),
        "cluster_name": HZ_CLUSTER_NAME,
        "members": members,
    }


def list_maps(hz) -> list[str]:
    """Names of all maps in the cluster."""
    return list_map_names(hz)


# --------------------------------------------------------------------------- #
# Maps
# --------------------------------------------------------------------------- #
def list_entries(hz, map_name: str, limit: int = 100) -> dict:
    """Up to `limit` entries from a map, plus the map's total size."""
    m = get_map(hz, map_name)
    entries: dict[str, Any] = {}
    for k, v in m.entry_set():
        entries[k] = from_hz(v)
        if len(entries) >= limit:
            break
    return {"map": map_name, "size": m.size(), "returned": len(entries), "entries": entries}


def map_size(hz, map_name: str) -> dict:
    return {"map": map_name, "size": get_map(hz, map_name).size()}


def map_keys(hz, map_name: str) -> list:
    return sorted(get_map(hz, map_name).key_set(), key=str)


def parse_search_value(value: str) -> Any:
    """Turn query-string text into a JSON value: "42" -> 42, "true" -> True, "Risk" stays "Risk"."""
    try:
        return json.loads(value)
    except ValueError:
        return value


def search(hz, map_name: str, field: str, value: Any) -> dict:
    """Entries whose JSON `field` equals `value`."""
    matches = get_map(hz, map_name).entry_set(equal(field, value))
    return {k: from_hz(v) for k, v in matches}


def put_many(hz, map_name: str, entries: dict[str, Any]) -> dict:
    """Write many entries in one call."""
    get_map(hz, map_name).put_all({k: to_hz(v) for k, v in entries.items()})
    return {"map": map_name, "written": len(entries)}


def clear_map(hz, map_name: str) -> dict:
    """Remove every entry; returns how many there were."""
    m = get_map(hz, map_name)
    removed = m.size()
    m.clear()
    return {"map": map_name, "removed": removed}


# --------------------------------------------------------------------------- #
# Entries
# --------------------------------------------------------------------------- #
def put_entry(hz, map_name: str, key: str, value: Any, ttl: int | None = None) -> dict:
    """Create or replace an entry, optionally expiring after `ttl` seconds."""
    m = get_map(hz, map_name)
    if ttl:
        m.set(key, to_hz(value), ttl=ttl)
    else:
        m.set(key, to_hz(value))
    return {"map": map_name, "key": key, "ttl_seconds": ttl, "value": value}


def get_entry(hz, map_name: str, key: str) -> dict:
    value = get_map(hz, map_name).get(key)
    if value is None:
        raise EntryNotFound(map_name, key)
    return {"map": map_name, "key": key, "value": from_hz(value)}


def delete_entry(hz, map_name: str, key: str) -> dict:
    if get_map(hz, map_name).remove(key) is None:
        raise EntryNotFound(map_name, key)
    return {"map": map_name, "key": key, "deleted": True}
