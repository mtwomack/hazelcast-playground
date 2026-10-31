# Hazelcast Playground

A small Python FastAPI app for testing a Hazelcast cluster. Put, get, list, search and delete entries with curl or the Swagger UI.

## 1. Start Hazelcast

With Docker Desktop running:

```cmd
docker run -d --name hazelcast -p 5701:5701 hazelcast/hazelcast:5.5
```

Or start Hazelcast plus Management Center (web UI at http://localhost:8080):

```cmd
docker compose up -d
```

## 2. Install and run the API

This project uses [uv](https://docs.astral.sh/uv/). Install it once:

```cmd
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

(or `pip install uv`). Then, from this folder:

```cmd
uv sync
uv run uvicorn app.main:app --reload
```

`uv sync` creates `.venv` and installs the exact versions in `uv.lock`, including Python itself if you don't have a suitable version.

Open **http://localhost:8000/docs** for Swagger. Use **Try it out** on any endpoint.

### Settings (`.env`)

Settings are read from a `.env` file in the project folder. Create yours from the example:

```cmd
copy .env.example .env
```

| Variable | Default | Meaning |
|---|---|---|
| `HZ_MEMBERS` | `127.0.0.1:5701` | Comma-separated Hazelcast member addresses |
| `HZ_CLUSTER_NAME` | `dev` | Cluster name (`dev` is Hazelcast's default) |
| `HZ_CONTAINER` | `hazelcast` | Docker container name used by `/stats/hazelcast` |

Without a `.env` file, the defaults above are used. Real environment variables override `.env`. Your `.env` isn't committed to git, so it's safe for machine-specific values.

### Project layout

```
app/main.py              FastAPI endpoints
app/stats.py             CPU / memory / disk / network stats
app/util/hazelcast.py    Hazelcast settings and helpers (client, maps, JSON values)
scripts/load_bankers.py  Loads test bankers
tests/                   Tests (no cluster needed)
```

## 3. Endpoints

| Method | Path | What it does |
|---|---|---|
| GET | `/health` | Connection status and cluster members |
| GET | `/maps` | List map names |
| GET | `/maps/{map}` | List entries (`?limit=100`) |
| GET | `/maps/{map}/size` | Number of entries |
| GET | `/maps/{map}/keys` | List keys |
| GET | `/maps/{map}/search?field=&value=` | Entries where a JSON field equals a value |
| POST | `/maps/{map}/entries` | Put many entries (JSON object of key → value) |
| DELETE | `/maps/{map}` | Remove all entries |
| PUT | `/maps/{map}/entries/{key}` | Create or replace an entry (`?ttl=60` to expire it) |
| GET | `/maps/{map}/entries/{key}` | Get an entry |
| DELETE | `/maps/{map}/entries/{key}` | Delete an entry |

Values can be any JSON. Keys are strings.

## 4. curl examples (Windows Command Prompt)

Inline JSON in Command Prompt needs `\"` around strings. The `samples` folder has JSON files you can send with `-d @file` instead.

```cmd
:: Check the connection
curl http://localhost:8000/health

:: Put one entry (from a file)
curl -X PUT http://localhost:8000/maps/bankers/entries/ab12345 -H "Content-Type: application/json" -d @samples\alice.json

:: Put one entry (inline JSON)
curl -X PUT http://localhost:8000/maps/bankers/entries/zz11111 -H "Content-Type: application/json" -d "{\"name\": \"Zoe\", \"dept\": \"Ops\"}"

:: Put an entry that expires after 60 seconds
curl -X PUT "http://localhost:8000/maps/bankers/entries/temp1?ttl=60" -H "Content-Type: application/json" -d "{\"note\": \"gone in a minute\"}"

:: Load several entries
curl -X POST http://localhost:8000/maps/bankers/entries -H "Content-Type: application/json" -d @samples\bankers.json

:: Read
curl http://localhost:8000/maps/bankers/entries/ab12345
curl http://localhost:8000/maps/bankers
curl http://localhost:8000/maps/bankers/size
curl http://localhost:8000/maps/bankers/keys
curl "http://localhost:8000/maps/bankers/search?field=dept&value=Risk"

:: Delete one entry, then clear the map
curl -X DELETE http://localhost:8000/maps/bankers/entries/ab12345
curl -X DELETE http://localhost:8000/maps/bankers
```

In PowerShell, use `curl.exe` instead of `curl`, because `curl` there is an alias for `Invoke-WebRequest`.

## 5. Load test data (10,000 bankers)

`scripts/load_bankers.py` fills the `bankers` map with randomly generated bankers, keyed by SOEID, in the same JSON format the API uses:

```cmd
uv run python scripts/load_bankers.py
```

Options:

| Option | Default | Meaning |
|---|---|---|
| `--count` | `10000` | How many bankers to load |
| `--clear` | off | Empty the map before loading |
| `--map` | `bankers` | Map name |
| `--batch-size` | `1000` | Entries sent per `put_all` call |
| `--seed` | `42` | Same seed gives the same bankers every run |
| `--members`, `--cluster` | `HZ_MEMBERS`, `HZ_CLUSTER_NAME` | Where Hazelcast is |

Each banker looks like:

```json
{"soeid": "qa36048", "name": "Alex Dubois", "title": "Analyst", "dept": "Leveraged Finance",
 "sector": "Industrials", "region": "NAM", "active": true,
 "gfcids": ["3074165225", "4578950639"], "deal_team": ["dh41947", "dr84922"]}
```

Then try:

```cmd
curl http://localhost:8000/maps/bankers/size
curl http://localhost:8000/maps/bankers/entries/qa36048
curl "http://localhost:8000/maps/bankers/search?field=region&value=EMEA"
```

The data is fake: names, SOEIDs and GFCIDs are random.

## 6. Resource stats (CPU, memory, disk, network)

| Endpoint | What it measures |
|---|---|
| `GET /stats` | Both of the below in one response |
| `GET /stats/host` | The machine running this API (via `psutil`) |
| `GET /stats/hazelcast` | The Hazelcast Docker container, the same numbers as `docker stats` |

Each returns CPU %, memory used, disk read/write and network received/sent, both as **per-second rates** measured over a short sample window and as **totals** since start.

```cmd
curl http://localhost:8000/stats
curl "http://localhost:8000/stats/host?interval=2"
curl "http://localhost:8000/stats/hazelcast?container=hazelcast"
```

- `interval` (default `1`, up to `10`) is how many seconds to measure over. The Hazelcast call takes a couple of seconds longer, because Docker samples CPU itself.
- Container CPU % is per core, like `docker stats`: 200% means two full cores.
- The container name defaults to `hazelcast`. Change it with `?container=` or the `HZ_CONTAINER` variable.
- Container stats need Docker Desktop running. If it isn't, `/stats/hazelcast` returns 503 and `/stats` still returns the host stats.
- Disk I/O inside Docker Desktop containers is often reported as 0. Hazelcast keeps data in memory, so this is expected.

To see the effect of a load, run `/stats/hazelcast` while `scripts/load_bankers.py` is running.

## 7. Run the tests

The tests use a fake Hazelcast client, so no cluster is needed:

```cmd
uv run pytest -q
```

To add a package: `uv add <package>` (or `uv add --dev <package>` for test-only tools).

## Troubleshooting

- **App hangs at startup, then fails:** Hazelcast isn't reachable. Check `docker ps` shows the `hazelcast` container, and that `HZ_MEMBERS` points to it.
- **`docker` is not recognized:** Docker Desktop isn't installed or isn't running.
- **`uv sync` fails behind the corporate proxy:** set `HTTPS_PROXY`, and if your firm inspects TLS, run `set UV_SYSTEM_CERTS=1` so uv trusts the Windows certificate store (on older uv versions, `set UV_NATIVE_TLS=1`).
- **Corporate proxy:** the Hazelcast client connects directly to `127.0.0.1`, so the proxy shouldn't affect it. If `curl` goes through the proxy, add `--noproxy localhost`.
