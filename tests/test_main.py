"""API tests against an in-memory fake Hazelcast client (no cluster needed)."""
import pytest
from fastapi.testclient import TestClient
from hazelcast.core import HazelcastJsonValue

from app.main import MAP_SERVICE, app, get_hz


class FakeMap:
    def __init__(self):
        self.d, self.ttls = {}, {}

    def blocking(self): return self
    def get(self, k): return self.d.get(k)
    def set(self, k, v, ttl=None): self.d[k] = v; self.ttls[k] = ttl
    def put_all(self, m): self.d.update(m)
    def remove(self, k): return self.d.pop(k, None)
    def size(self): return len(self.d)
    def clear(self): self.d.clear()
    def key_set(self): return list(self.d)

    def entry_set(self, predicate=None):
        items = list(self.d.items())
        if predicate is None:
            return items
        # hazelcast.predicate.equal stores the attribute and value
        field, value = predicate.attribute, predicate.value
        return [(k, v) for k, v in items if v.loads().get(field) == value]


class Obj:
    def __init__(self, name): self.name, self.service_name = name, MAP_SERVICE


class Member:
    address = "127.0.0.1:5701"


class FakeHz:
    def __init__(self):
        self.maps = {}
        self.cluster_service = type("CS", (), {"get_members": lambda _: [Member()]})()
        self.lifecycle_service = type("LS", (), {"is_running": lambda _: True})()

    def get_map(self, name): return self.maps.setdefault(name, FakeMap())
    def get_distributed_objects(self): return [Obj(n) for n in self.maps]


@pytest.fixture
def client():
    fake = FakeHz()
    app.dependency_overrides[get_hz] = lambda: fake
    with TestClient(app) as c:   # no lifespan: we don't enter it, so no real connection
        yield c, fake
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def no_real_lifespan(monkeypatch):
    # Prevent TestClient from opening a real Hazelcast connection.
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def noop(_app):
        yield
    monkeypatch.setattr(app.router, "lifespan_context", noop)


ALICE = {"name": "Alice", "dept": "Risk", "level": 3}


def test_health(client):
    c, _ = client
    r = c.get("/health")
    assert r.status_code == 200 and r.json()["connected"] is True


def test_put_get_delete(client):
    c, fake = client
    assert c.put("/maps/bankers/entries/ab12345", json=ALICE).status_code == 200
    assert isinstance(fake.maps["bankers"].d["ab12345"], HazelcastJsonValue)
    assert c.get("/maps/bankers/entries/ab12345").json()["value"] == ALICE
    assert c.delete("/maps/bankers/entries/ab12345").json()["deleted"] is True
    assert c.get("/maps/bankers/entries/ab12345").status_code == 404
    assert c.delete("/maps/bankers/entries/ab12345").status_code == 404


def test_scalar_values_round_trip(client):
    c, _ = client
    for key, value in [("s", "hello"), ("n", 42), ("b", True), ("l", [1, 2])]:
        c.put(f"/maps/misc/entries/{key}", json=value)
        assert c.get(f"/maps/misc/entries/{key}").json()["value"] == value


def test_ttl_passed_through(client):
    c, fake = client
    c.put("/maps/bankers/entries/ab1?ttl=60", json=ALICE)
    assert fake.maps["bankers"].ttls["ab1"] == 60


def test_bulk_list_size_keys_clear(client):
    c, _ = client
    r = c.post("/maps/bankers/entries", json={"a": ALICE, "b": {**ALICE, "name": "Bob"}, "c": {"name": "Cara"}})
    assert r.json()["written"] == 3
    assert c.get("/maps/bankers/size").json()["size"] == 3
    assert c.get("/maps/bankers/keys").json() == ["a", "b", "c"]
    listing = c.get("/maps/bankers?limit=2").json()
    assert listing["size"] == 3 and listing["returned"] == 2
    assert c.get("/maps").json() == ["bankers"]
    assert c.delete("/maps/bankers").json()["removed"] == 3
    assert c.get("/maps/bankers/size").json()["size"] == 0


def test_search(client):
    c, _ = client
    c.post("/maps/bankers/entries", json={"a": ALICE, "b": {"name": "Bob", "dept": "Quant", "level": 3}})
    assert set(c.get("/maps/bankers/search", params={"field": "dept", "value": "Risk"}).json()) == {"a"}
    assert set(c.get("/maps/bankers/search", params={"field": "level", "value": "3"}).json()) == {"a", "b"}


def test_swagger_available(client):
    c, _ = client
    assert c.get("/docs").status_code == 200
    paths = c.get("/openapi.json").json()["paths"]
    assert "/maps/{map_name}/entries/{key}" in paths
