"""Tests for the stats service and /stats endpoints (host via psutil, container via a fake Docker client)."""
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

from app.services import stats_service as stats
from app.main import app

MB = 1024 * 1024


def snapshot(total_cpu, system_cpu, pre_total, pre_system, read, write, rx, tx):
    return {
        "cpu_stats": {"cpu_usage": {"total_usage": total_cpu}, "system_cpu_usage": system_cpu, "online_cpus": 4},
        "precpu_stats": {"cpu_usage": {"total_usage": pre_total}, "system_cpu_usage": pre_system},
        "memory_stats": {"usage": 600 * MB, "limit": 2000 * MB, "stats": {"inactive_file": 100 * MB}},
        "blkio_stats": {"io_service_bytes_recursive": [
            {"major": 8, "minor": 0, "op": "read", "value": read},
            {"major": 8, "minor": 0, "op": "write", "value": write},
        ]},
        "networks": {"eth0": {"rx_bytes": rx, "tx_bytes": tx}},
    }


def test_parse_container_stats():
    prev = snapshot(0, 0, 0, 0, read=10 * MB, write=20 * MB, rx=1 * MB, tx=2 * MB)
    cur = snapshot(total_cpu=200, system_cpu=1000, pre_total=100, pre_system=500,
                   read=12 * MB, write=26 * MB, rx=3 * MB, tx=6 * MB)
    out = stats.parse_container_stats(cur, prev=prev, interval=2.0)
    assert out["cpu"] == {"percent": 80.0, "cores": 4}          # 100/500 * 4 cores * 100
    assert out["memory"] == {"percent": 25.0, "used_mb": 500.0, "limit_mb": 2000.0}
    assert out["disk"] == {"read_total_mb": 12.0, "write_total_mb": 26.0, "read_mb_per_s": 1.0, "write_mb_per_s": 3.0}
    assert out["network"] == {"received_total_mb": 3.0, "sent_total_mb": 6.0,
                              "received_mb_per_s": 1.0, "sent_mb_per_s": 2.0}


def test_parse_handles_missing_sections():
    out = stats.parse_container_stats({"cpu_stats": {}, "precpu_stats": {}})
    assert out["cpu"]["percent"] == 0.0 and out["memory"]["percent"] is None
    assert out["disk"]["read_total_mb"] == 0 and out["network"]["sent_total_mb"] == 0


def test_container_stats_with_fake_docker():
    snaps = iter([snapshot(0, 0, 0, 0, 0, 0, 0, 0), snapshot(50, 100, 0, 0, MB, MB, MB, MB)])

    class C:
        name, status = "hazelcast", "running"
        def stats(self, stream): return next(snaps)

    class Client:
        containers = type("X", (), {"get": staticmethod(lambda n: C())})()

    out = stats.container_stats("hazelcast", interval=0.01, client=Client())
    assert out["container"] == "hazelcast" and out["status"] == "running"
    assert out["cpu"]["percent"] == 200.0 and out["network"]["received_mb_per_s"] > 0


def test_host_stats_real():
    out = stats.host_stats(interval=0.1)
    assert 0 <= out["cpu"]["percent"] <= 100 * out["cpu"]["cores"]
    assert out["memory"]["total_mb"] > 0
    assert "received_mb_per_s" in out["network"]


# ---- endpoints ----
@pytest.fixture
def client(monkeypatch):
    @asynccontextmanager
    async def noop(_app):
        yield
    monkeypatch.setattr(app.router, "lifespan_context", noop)
    with TestClient(app) as c:
        yield c


def test_stats_host_endpoint(client):
    r = client.get("/api/v1/stats/host?interval=0.1")
    assert r.status_code == 200 and r.json()["source"] == "host"


def _raise(exc):
    def f(*_a, **_k):
        raise exc
    return f


def test_container_not_found_maps_docker_error():
    class NotFound(Exception): ...

    def get(_name):
        raise NotFound("404")

    class Client:
        containers = type("X", (), {"get": staticmethod(get)})()

    with pytest.raises(stats.ContainerNotFound):
        stats.container_stats("nope", interval=0.01, client=Client())


def test_docker_down_maps_to_unavailable():
    class Client:
        containers = type("X", (), {"get": staticmethod(_raise(ConnectionError("no docker")))})()

    with pytest.raises(stats.DockerUnavailable):
        stats.container_stats("hazelcast", interval=0.01, client=Client())


def test_stats_hazelcast_not_found(client, monkeypatch):
    monkeypatch.setattr(stats, "container_stats", _raise(stats.ContainerNotFound("Docker container 'nope' not found")))
    r = client.get("/api/v1/stats/hazelcast?interval=0.1&container=nope")
    assert r.status_code == 404 and "not found" in r.json()["detail"]


def test_stats_hazelcast_docker_down(client, monkeypatch):
    monkeypatch.setattr(stats, "container_stats", _raise(stats.DockerUnavailable("Can't read Docker stats")))
    r = client.get("/api/v1/stats/hazelcast?interval=0.1")
    assert r.status_code == 503 and "Docker" in r.json()["detail"]


def test_stats_combined_survives_missing_docker(client, monkeypatch):
    monkeypatch.setattr(stats, "container_stats", _raise(stats.DockerUnavailable("Can't read Docker stats")))
    body = client.get("/api/v1/stats?interval=0.1").json()
    assert body["host"]["source"] == "host"
    assert body["hazelcast_container"] == {"available": False, "error": "Can't read Docker stats"}


def test_stats_combined_with_container(client, monkeypatch):
    fake = {"source": "container", "container": "hazelcast", "status": "running", "sample_seconds": 0.1,
            "cpu": {"percent": 5.0, "cores": 2}, "memory": {"percent": 10.0, "used_mb": 100.0, "limit_mb": 1000.0},
            "disk": {"read_total_mb": 0.0, "write_total_mb": 0.0},
            "network": {"received_total_mb": 1.0, "sent_total_mb": 2.0}}
    monkeypatch.setattr(stats, "container_stats", lambda name, interval: {**fake, "container": name})
    body = client.get("/api/v1/stats?interval=0.1").json()
    assert body["hazelcast_container"]["container"] == "hazelcast"
    assert "total_mb" not in body["hazelcast_container"]["memory"]   # None fields are dropped


def test_docker_client_is_closed_after_each_call(monkeypatch):
    import docker

    made = []

    class C:
        name, status = "hazelcast", "running"
        def stats(self, stream): return snapshot(0, 0, 0, 0, 0, 0, 0, 0)

    class FakeDocker:
        def __init__(self):
            self.closed = False
            self.containers = type("X", (), {"get": staticmethod(lambda n: C())})()
            made.append(self)
        def close(self): self.closed = True

    monkeypatch.setattr(docker, "from_env", FakeDocker)
    for _ in range(5):
        stats.container_stats("hazelcast", interval=0)
    assert len(made) == 5 and all(c.closed for c in made)


def test_docker_client_closed_even_when_container_missing(monkeypatch):
    import docker

    class NotFound(Exception): ...

    def get(_name):
        raise NotFound("404")

    holder = {}

    class FakeDocker:
        def __init__(self):
            self.closed = False
            self.containers = type("X", (), {"get": staticmethod(get)})()
            holder["c"] = self
        def close(self): self.closed = True

    monkeypatch.setattr(docker, "from_env", FakeDocker)
    with pytest.raises(stats.ContainerNotFound):
        stats.container_stats("nope", interval=0)
    assert holder["c"].closed
