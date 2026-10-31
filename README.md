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

From this folder, in Command Prompt:

```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open **http://localhost:8000/docs** for Swagger. Use **Try it out** on any endpoint.

Settings (optional, defaults shown):

| Variable | Default | Meaning |
|---|---|---|
| `HZ_MEMBERS` | `127.0.0.1:5701` | Comma-separated Hazelcast member addresses |
| `HZ_CLUSTER_NAME` | `dev` | Cluster name (`dev` is Hazelcast's default) |

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

## 5. Run the tests

The tests use a fake Hazelcast client, so no cluster is needed:

```cmd
pytest -q
```

## Troubleshooting

- **App hangs at startup, then fails:** Hazelcast isn't reachable. Check `docker ps` shows the `hazelcast` container, and that `HZ_MEMBERS` points to it.
- **`docker` is not recognized:** Docker Desktop isn't installed or isn't running.
- **Corporate proxy:** the Hazelcast client connects directly to `127.0.0.1`, so the proxy shouldn't affect it. If `curl` goes through the proxy, add `--noproxy localhost`.
