"""
Load fake bankers into the Hazelcast `bankers` map.

Each entry is keyed by a lowercase SOEID (e.g. "ab12345") and stored as JSON,
in the same format the API uses, so you can read them back with
GET /maps/bankers/entries/{soeid}.

Usage (from the project folder):
    uv run python scripts/load_bankers.py                  # 10,000 bankers
    uv run python scripts/load_bankers.py --count 500
    uv run python scripts/load_bankers.py --clear          # empty the map first
    uv run python scripts/load_bankers.py --help

All data is randomly generated. Use --seed for the same bankers every run.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import string
import sys
import time

FIRST_NAMES = [
    "Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Jamie", "Avery", "Quinn", "Drew",
    "Sam", "Robin", "Cameron", "Reese", "Hayden", "Parker", "Rowan", "Emerson", "Logan", "Blake",
    "Priya", "Wei", "Mateo", "Amara", "Kenji", "Lena", "Omar", "Sofia", "Arjun", "Nadia",
]
LAST_NAMES = [
    "Smith", "Chen", "Patel", "Garcia", "Kim", "Nguyen", "Rossi", "Muller", "Okafor", "Silva",
    "Johnson", "Brown", "Lee", "Martin", "Clark", "Lewis", "Walker", "Young", "Hall", "Allen",
    "Khan", "Tanaka", "Novak", "Dubois", "Haddad", "Larsen", "Costa", "Ivanova", "Reyes", "Shah",
]
DEPARTMENTS = ["Coverage", "M&A", "ECM", "DCM", "Leveraged Finance", "Restructuring", "Corporate Banking"]
SECTORS = ["Technology", "Healthcare", "Energy", "Financials", "Industrials", "Consumer", "Real Estate", "Media"]
REGIONS = ["NAM", "EMEA", "APAC", "LATAM"]
TITLES = ["Analyst", "Associate", "Vice President", "Director", "Managing Director"]


def make_soeid(rng: random.Random) -> str:
    """Two lowercase letters + five digits, e.g. 'ab12345'."""
    return "".join(rng.choices(string.ascii_lowercase, k=2)) + f"{rng.randrange(100000):05d}"


def generate_bankers(count: int, seed: int | None = None) -> dict[str, dict]:
    """Return {soeid: banker} for `count` unique, randomly generated bankers."""
    rng = random.Random(seed)
    soeids: list[str] = []
    seen: set[str] = set()
    while len(soeids) < count:
        s = make_soeid(rng)
        if s not in seen:
            seen.add(s)
            soeids.append(s)

    bankers = {}
    for soeid in soeids:
        teammates = [t for t in rng.sample(soeids, k=min(len(soeids), 7)) if t != soeid][: rng.randint(0, 6)]
        bankers[soeid] = {
            "soeid": soeid,
            "name": f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
            "title": rng.choice(TITLES),
            "dept": rng.choice(DEPARTMENTS),
            "sector": rng.choice(SECTORS),
            "region": rng.choice(REGIONS),
            "active": rng.random() > 0.05,
            "gfcids": sorted({str(rng.randrange(1_000_000_000, 10_000_000_000)) for _ in range(rng.randint(1, 15))}),
            "deal_team": teammates,
        }
    return bankers


def load(bankers_map, bankers: dict[str, dict], batch_size: int = 1000) -> int:
    """put_all in batches; returns the number written. `bankers_map` is a blocking map proxy."""
    from hazelcast.core import HazelcastJsonValue

    items = list(bankers.items())
    written = 0
    for i in range(0, len(items), batch_size):
        chunk = items[i:i + batch_size]
        bankers_map.put_all({k: HazelcastJsonValue(json.dumps(v)) for k, v in chunk})
        written += len(chunk)
        print(f"  loaded {written:,}/{len(items):,}", flush=True)
    return written


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Load fake bankers into a Hazelcast map.")
    p.add_argument("--count", type=int, default=10_000, help="number of bankers (default 10000)")
    p.add_argument("--map", default="bankers", help="map name (default bankers)")
    p.add_argument("--batch-size", type=int, default=1000, help="entries per put_all (default 1000)")
    p.add_argument("--seed", type=int, default=42, help="random seed; same seed = same bankers (default 42)")
    p.add_argument("--clear", action="store_true", help="remove existing entries from the map first")
    p.add_argument("--members", default=os.getenv("HZ_MEMBERS", "127.0.0.1:5701"),
                   help="comma-separated member addresses (default HZ_MEMBERS or 127.0.0.1:5701)")
    p.add_argument("--cluster", default=os.getenv("HZ_CLUSTER_NAME", "dev"),
                   help="cluster name (default HZ_CLUSTER_NAME or dev)")
    args = p.parse_args(argv)

    if args.count < 1 or args.batch_size < 1:
        p.error("--count and --batch-size must be at least 1")

    import hazelcast

    members = [m.strip() for m in args.members.split(",") if m.strip()]
    print(f"Connecting to cluster '{args.cluster}' at {members} ...")
    try:
        client = hazelcast.HazelcastClient(cluster_members=members, cluster_name=args.cluster,
                                           cluster_connect_timeout=15)
    except Exception as e:  # noqa: BLE001
        print(f"Could not connect to Hazelcast: {e}\nIs it running? Try: docker ps", file=sys.stderr)
        return 1

    try:
        m = client.get_map(args.map).blocking()
        if args.clear:
            print(f"Clearing map '{args.map}' ({m.size():,} entries) ...")
            m.clear()

        print(f"Generating {args.count:,} bankers (seed {args.seed}) ...")
        bankers = generate_bankers(args.count, args.seed)

        start = time.perf_counter()
        load(m, bankers, args.batch_size)
        elapsed = time.perf_counter() - start

        sample = next(iter(bankers))
        print(f"\nDone: {args.count:,} bankers in {elapsed:.1f}s. Map '{args.map}' now has {m.size():,} entries.")
        print(f"Try:  curl http://localhost:8000/maps/{args.map}/entries/{sample}")
    finally:
        client.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
