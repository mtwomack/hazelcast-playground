"""Service-layer tests: call app/services/hazelcast_service.py directly (no HTTP, no cluster)."""
import pytest

from app.services import hazelcast_service as svc
from tests.test_main import FakeHz

ALICE = {"name": "Alice", "dept": "Risk", "level": 3}


@pytest.fixture
def hz():
    return FakeHz()


def test_health(hz):
    assert svc.health(hz) == {"connected": True, "cluster_name": "dev", "members": ["127.0.0.1:5701"]}


def test_put_get_delete(hz):
    assert svc.put_entry(hz, "bankers", "ab1", ALICE)["value"] == ALICE
    assert svc.get_entry(hz, "bankers", "ab1")["value"] == ALICE
    assert svc.delete_entry(hz, "bankers", "ab1") == {"map": "bankers", "key": "ab1", "deleted": True}


def test_missing_entry_raises(hz):
    with pytest.raises(svc.EntryNotFound) as e:
        svc.get_entry(hz, "bankers", "nope")
    assert e.value.key == "nope" and "not found" in str(e.value)
    with pytest.raises(svc.EntryNotFound):
        svc.delete_entry(hz, "bankers", "nope")


def test_ttl(hz):
    svc.put_entry(hz, "bankers", "ab1", ALICE, ttl=30)
    assert hz.maps["bankers"].ttls["ab1"] == 30


def test_map_operations(hz):
    assert svc.put_many(hz, "bankers", {"a": ALICE, "b": {"name": "Bob", "dept": "Quant", "level": 3}})["written"] == 2
    assert svc.map_size(hz, "bankers")["size"] == 2
    assert svc.map_keys(hz, "bankers") == ["a", "b"]
    assert svc.list_entries(hz, "bankers", limit=1)["returned"] == 1
    assert svc.list_maps(hz) == ["bankers"]
    assert set(svc.search(hz, "bankers", "dept", "Risk")) == {"a"}
    assert set(svc.search(hz, "bankers", "level", 3)) == {"a", "b"}
    assert svc.clear_map(hz, "bankers")["removed"] == 2


@pytest.mark.parametrize("text,expected", [("42", 42), ("true", True), ("Risk", "Risk"), ("1.5", 1.5)])
def test_parse_search_value(text, expected):
    assert svc.parse_search_value(text) == expected
