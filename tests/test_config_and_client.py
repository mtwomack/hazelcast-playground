"""Tests for app/core/config.py (settings) and app/clients/hazelcast_client.py (helpers)."""
import importlib

from hazelcast.core import HazelcastJsonValue

from app.clients import hazelcast_client as client_mod
from app.core import config

HZ_VARS = ("HZ_MEMBERS", "HZ_CLUSTER_NAME", "HZ_CONTAINER")


# ---- client helpers ----
def test_json_round_trip():
    for value in ["hello", 42, True, None, [1, 2], {"name": "Alice", "gfcids": ["1001"]}]:
        stored = client_mod.to_hz(value)
        assert isinstance(stored, HazelcastJsonValue)
        assert client_mod.from_hz(stored) == value


def test_from_hz_passes_through_other_values():
    assert client_mod.from_hz("raw") == "raw"


def test_list_map_names_filters_to_maps():
    class Obj:
        def __init__(self, name, service): self.name, self.service_name = name, service

    class Client:
        def get_distributed_objects(self):
            return [Obj("bankers", client_mod.MAP_SERVICE), Obj("jobs", "hz:impl:queueService"),
                    Obj("accounts", client_mod.MAP_SERVICE)]

    assert client_mod.list_map_names(Client()) == ["accounts", "bankers"]


# ---- settings ----
def test_settings_from_env_file(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("HZ_MEMBERS=10.0.0.1:5701, 10.0.0.2:5701\nHZ_CLUSTER_NAME=qa\nHZ_CONTAINER=hz1\n")
    for var in HZ_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ENV_FILE", str(tmp_path / ".env"))
    try:
        mod = importlib.reload(config)
        assert mod.HZ_MEMBERS == ["10.0.0.1:5701", "10.0.0.2:5701"]
        assert mod.HZ_CLUSTER_NAME == "qa" and mod.HZ_CONTAINER == "hz1"
    finally:
        for var in HZ_VARS:
            monkeypatch.delenv(var, raising=False)   # load_dotenv wrote them into os.environ
        monkeypatch.delenv("ENV_FILE")
        importlib.reload(config)


def test_real_env_var_wins_over_env_file(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("HZ_CLUSTER_NAME=from-file\n")
    monkeypatch.setenv("HZ_CLUSTER_NAME", "from-env")
    monkeypatch.setenv("ENV_FILE", str(tmp_path / ".env"))
    try:
        assert importlib.reload(config).HZ_CLUSTER_NAME == "from-env"
    finally:
        monkeypatch.delenv("HZ_CLUSTER_NAME")
        monkeypatch.delenv("ENV_FILE")
        importlib.reload(config)


def test_defaults_without_env_file(tmp_path, monkeypatch):
    for var in HZ_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ENV_FILE", str(tmp_path / "missing.env"))
    try:
        mod = importlib.reload(config)
        assert mod.HZ_MEMBERS == ["127.0.0.1:5701"] and mod.HZ_CLUSTER_NAME == "dev" and mod.HZ_CONTAINER == "hazelcast"
    finally:
        monkeypatch.delenv("ENV_FILE")
        importlib.reload(config)
