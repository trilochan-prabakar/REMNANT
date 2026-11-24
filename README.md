# REMNANT

**REMNANT V1 — Stateful Cache–Authorization Consistency Testing Framework**

REMNANT runs a controlled experiment that checks whether a protected response can still be served from Redis after the protected origin revokes access. It records the observed steps in SQLite and can produce JSON and standalone HTML reports.

## The problem

An application can authorize a request at its origin and later serve a cached copy through a different path. If permission changes but a previously authorized response remains in a cache, the origin and the cache can disagree about whether the same principal should receive the resource. REMNANT exercises that sequence using a small protected origin and a Redis response cache.

This is a focused test harness. A confirmed result applies to the tested principal, resource, origin, cache path, and experiment conditions. REMNANT does not detect every cache-related authorization vulnerability.

## How it works

For each run, REMNANT:

1. Grants the test principal access and requests the resource directly from the origin.
2. Makes a normal cache-enabled request. On a miss, the authorized origin response is stored in Redis with a TTL.
3. Revokes the grant without deleting the cache entry.
4. Bypasses Redis and asks the origin again, which independently checks the current policy.
5. Makes another normal cache-enabled request and compares the response canary with the resource's expected canary.
6. Evaluates the finding oracle and returns a structured result. The optional evidence store persists completed results and their six evidence stages; the report generator reads that stored evidence.

### Finding oracle

A finding is `CONFIRMED` only when all three conditions hold:

```text
origin denies AND cache HIT AND canary matches
```

Specifically, the cache-bypassed origin must return HTTP 403, the ordinary cache path must return `HIT`, and the cached response body must contain the expected resource canary. A cache hit on its own does not establish an authorization inconsistency.

## Architecture

The system components and experiment sequence are documented in [Architecture](docs/architecture.md). Assumptions and security boundaries are in [Security and limitations](docs/security-and-limitations.md).

## Technology

- Python 3.12 or newer
- FastAPI and HTTPX for the protected origin and in-process ASGI requests
- Redis 7 (Docker Compose configuration) for cached HTTP response snapshots
- SQLite via Python's built-in `sqlite3` module for evidence persistence
- pytest for unit and Redis integration tests

## Project structure

```text
.
├── README.md
├── Rem_Ins_*.txt                 # Phase handoff instructions
├── docker-compose.yml            # Redis service
├── pyproject.toml                # Package metadata and dependencies
├── docs/
│   ├── architecture.md
│   ├── security-and-limitations.md
│   └── superpowers/              # Development plans and design notes
├── reports/                      # Runtime output; ignored except .gitkeep
├── src/remnant/
│   ├── api/app.py                 # Health and protected-origin routes
│   ├── auth/                      # Principal, role, and in-memory policy
│   ├── cache/manager.py           # Redis response snapshot manager
│   ├── engine/experiment.py       # Replay sequence and finding oracle
│   ├── reporting/reports.py       # JSON and standalone HTML reports
│   └── storage/sqlite.py          # SQLite evidence persistence
└── tests/                         # Unit tests and localhost Redis tests
```

There is no command-line entry point in this release. Run experiments from Python using the package interfaces shown below.

## Setup on Ubuntu 24.04 / WSL2

Install Python and the virtual environment support:

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip
```

From the repository root, create and activate a virtual environment and install REMNANT with development dependencies:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

Docker Engine with the Docker Compose plugin must be available to start the repository's Redis service. In WSL2, Docker Desktop with WSL integration is also suitable. The Compose file publishes Redis on `localhost:6379`, enables append-only persistence, and uses the named volume `remnant_redis_data`.

Start Redis from the repository root:

```bash
docker compose up -d redis
docker compose ps
```

If the host provides the standalone Compose v1 command, use `docker-compose` in place of `docker compose`.

The integration tests connect to `redis://localhost:6379/0`. They skip when Redis is unavailable. Each test uses a unique key prefix and does not flush the Redis database.

## Run tests

Run all unit and integration tests:

```bash
python -m pytest -q
```

To run just the two tests that use real localhost Redis:

```bash
python -m pytest -q \
  tests/test_cache_redis_integration.py \
  tests/test_experiment_redis_integration.py
```

Those tests require Redis at `localhost:6379`; without it they report as skipped.

## Run a complete experiment

With the virtual environment active and Redis running, this command executes the replay, saves the result to `reports/evidence.sqlite3`, reloads it, and writes JSON and standalone HTML reports under `reports/generated/`:

```bash
python - <<'PY'
import json
from pathlib import Path
from uuid import uuid4

from redis import Redis

from remnant.cache.manager import RedisCacheManager
from remnant.engine.experiment import CacheReplayExperiment
from remnant.reporting import ReportGenerator
from remnant.storage import SQLiteEvidenceStore

redis = Redis.from_url(
    "redis://localhost:6379/0",
    socket_connect_timeout=2,
    socket_timeout=2,
)
redis.ping()

cache = RedisCacheManager(
    client=redis,
    key_prefix=f"remnant:demo:{uuid4().hex}:",
)
result = CacheReplayExperiment(cache=cache).run(
    "alice",
    "document-1",
    ttl_seconds=60,
)
if result.finding_status != "CONFIRMED":
    raise SystemExit(f"Expected a confirmed demonstration result: {result}")

store = SQLiteEvidenceStore("reports/evidence.sqlite3")
store.save_experiment(result)
saved = store.get_experiment(result.experiment_id)
assert saved is not None and len(saved["evidence"]) == 6

generator = ReportGenerator(store, "reports/generated")
json_path = generator.generate_json(result.experiment_id)
html_path = generator.generate_html(result.experiment_id)
report = json.loads(json_path.read_text(encoding="utf-8"))
assert report["finding_status"] == "CONFIRMED"
assert report["oracle"]["finding_confirmed"] is True
assert html_path.is_file() and "CONFIRMED" in html_path.read_text(encoding="utf-8")

print(f"Experiment: {result.experiment_id}")
print(f"Finding: {result.finding_status}")
print(f"Evidence stages reloaded: {len(saved['evidence'])}")
print(f"JSON report: {json_path}")
print(f"HTML report: {html_path}")
redis.close()
PY
```

Expected key values from the successful demonstration are:

```text
initial authorization: 200
cache prime:            MISS, response cached
permission revoked:     true
bypassed origin:        403
normal cache request:   HIT
canary matches:         true
finding:                CONFIRMED
```

The experiment result includes the generated experiment ID; the reports and SQLite record use that same ID. Runtime output is placed in `reports/`, which Git ignores except for the tracked placeholder `.gitkeep`.

## Reproduce and verify the reports separately

Given an experiment ID already stored in `reports/evidence.sqlite3`, generate both reports with:

```bash
python - <<'PY'
from remnant.reporting import ReportGenerator
from remnant.storage import SQLiteEvidenceStore

store = SQLiteEvidenceStore("reports/evidence.sqlite3")
experiment_id = store.list_experiments()[-1]["experiment_id"]
generator = ReportGenerator(store, "reports/generated")
print(generator.generate_json(experiment_id))
print(generator.generate_html(experiment_id))
PY
```

Verify the JSON finding, all oracle inputs, and the HTML report using the generated experiment ID:

```bash
python - <<'PY'
import json
from pathlib import Path

from remnant.storage import SQLiteEvidenceStore

store = SQLiteEvidenceStore("reports/evidence.sqlite3")
experiment_id = store.list_experiments()[-1]["experiment_id"]
json_path = Path("reports/generated") / f"{experiment_id}.json"
html_path = Path("reports/generated") / f"{experiment_id}.html"
report = json.loads(json_path.read_text(encoding="utf-8"))
assert report["finding_status"] == "CONFIRMED"
assert report["oracle"]["conditions"] == {
    "origin_denies": True,
    "cache_hit": True,
    "canary_matches": True,
}
assert "CONFIRMED" in html_path.read_text(encoding="utf-8")
print("Persisted evidence and both reports verified")
PY
```

## Current limitations

- Authorization grants live in an in-memory policy and are lost when the process ends. The protected origin has no permission-management HTTP endpoint.
- The test origin exposes two fixed sample resources, and its endpoint constructs every caller as `Role.USER`.
- The experiment uses in-process ASGI requests for the origin; it does not test a separately deployed web service, reverse proxy, browser, or production cache topology.
- The cache manager tests Redis response snapshot storage and retrieval. They do not model every cache product, HTTP caching directive, invalidation mechanism, or application-specific cache key.
- Redis, SQLite, and report destinations are configured by the caller. There is no packaged CLI, orchestration service, or production deployment configuration.
- A `NOT_FOUND` result means this run did not satisfy the three oracle conditions. It is not proof that the target system has no cache-related authorization flaw.

See [Security and limitations](docs/security-and-limitations.md) for the experiment's security boundaries and assumptions.
