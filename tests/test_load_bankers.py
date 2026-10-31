"""Tests for scripts/load_bankers.py (no cluster needed)."""
import importlib.util
import re
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "load_bankers", Path(__file__).resolve().parents[1] / "scripts" / "load_bankers.py")
load_bankers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(load_bankers)


class FakeMap:
    def __init__(self):
        self.d, self.calls = {}, 0

    def put_all(self, m):
        self.calls += 1
        self.d.update(m)


def test_generates_requested_count_with_unique_soeids():
    bankers = load_bankers.generate_bankers(10_000, seed=1)
    assert len(bankers) == 10_000
    assert all(re.fullmatch(r"[a-z]{2}\d{5}", s) for s in bankers)


def test_banker_shape():
    bankers = load_bankers.generate_bankers(50, seed=1)
    for soeid, b in bankers.items():
        assert b["soeid"] == soeid
        assert set(b) == {"soeid", "name", "title", "dept", "sector", "region", "active", "gfcids", "deal_team"}
        assert 1 <= len(b["gfcids"]) <= 15
        assert soeid not in b["deal_team"]
        assert all(t in bankers for t in b["deal_team"])


def test_same_seed_same_bankers():
    assert load_bankers.generate_bankers(100, seed=7) == load_bankers.generate_bankers(100, seed=7)


def test_load_in_batches_as_json():
    m = FakeMap()
    bankers = load_bankers.generate_bankers(2_500, seed=3)
    assert load_bankers.load(m, bankers, batch_size=1000) == 2_500
    assert m.calls == 3 and len(m.d) == 2_500
    soeid = next(iter(bankers))
    assert m.d[soeid].loads() == bankers[soeid]   # readable by the API's _from_hz


def test_rejects_bad_count():
    import pytest
    with pytest.raises(SystemExit):
        load_bankers.main(["--count", "0"])
