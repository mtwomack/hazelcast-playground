"""Tests for app/util/hazelcast.py."""
import importlib

from hazelcast.core import HazelcastJsonValue

from app.util import hazelcast as hz_util


def test_json_round_trip():
    for value in ["hello", 42, True, None, [1, 2], {"name": "Alice", "gfcids": ["1001"]}]:
        stored = hz_util.to_hz(value)
        assert isinstance(stored, HazelcastJsonValue)
        assert hz_util.from_hz(stored) == value


def test_from_hz_passes_through_other_values():
    assert hz_util.from_hz("raw") == "raw"


def test_list_map_names_filters_to_maps():
    class Obj:
        def __init__(self, name, service): self.name, self.service_name = name, service

    class Client:
        def get_distributed_objects(self):
            return [Obj("bankers", hz_util.MAP_SERVICE), Obj("jobs", "hz:impl:queueService"),
                    Obj("accounts", hz_util.MAP_SERVICE)]

    assert hz_util.list_map_names(Client()) == ["accounts", "bankers"]


def test_settings_from_env_file(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("HZ_MEMBERS=10.0.0.1:5701, 10.0.0.2:5701\nHZ_CLUSTER_NAME=qa\nHZ_CONTAINER=hz1\n")
    for var in ("HZ_MEMBERS", "HZ_CLUSTER_NAME", "HZ_CONTAINER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ENV_FILE", str(tmp_path / ".env"))
    try:
        mod = importlib.reload(hz_util)
        assert mod.HZ_MEMBERS == ["10.0.0.1:5701", "10.0.0.2:5701"]
        assert mod.HZ_CLUSTER_NAME == "qa" and mod.HZ_CONTAINER == "hz1"
    finally:
        for var in ("HZ_MEMBERS", "HZ_CLUSTER_NAME", "HZ_CONTAINER"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.delenv("ENV_FILE")
        importlib.reload(hz_util)


def test_real_env_var_wins_over_env_file(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("HZ_CLUSTER_NAME=from-file\n")
    monkeypatch.setenv("HZ_CLUSTER_NAME", "from-env")
    monkeypatch.setenv("ENV_FILE", str(tmp_path / ".env"))
    try:
        assert importlib.reload(hz_util).HZ_CLUSTER_NAME == "from-env"
    finally:
        monkeypatch.delenv("HZ_CLUSTER_NAME")
        monkeypatch.delenv("ENV_FILE")
        importlib.reload(hz_util)
