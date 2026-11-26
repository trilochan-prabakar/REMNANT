# REMNANT V3 usage

V3 adds a controlled HTTP scenario runner, protocol-level cache analysis, an
identity-isolation oracle, and a real Varnish reverse-proxy fixture. It is
additive: V1/V2 source modules and their contracts are unchanged.

## Run a scenario

Create separately configured origin and proxy clients. The scenario file selects
only relative paths and whether each request goes to the origin or proxy; it
cannot select a host, execute code, change request methods beyond GET/HEAD, or
follow redirects.

```python
import asyncio
import httpx

from remnant.v3 import ScenarioLoader, ScenarioRunner, run_to_json

scenario = ScenarioLoader().loads(open("scenario.yml", encoding="utf-8").read())

async def main():
    async with (
        httpx.AsyncClient(base_url="http://127.0.0.1:8000") as origin,
        httpx.AsyncClient(base_url="http://127.0.0.1:8080") as proxy,
    ):
        result = await ScenarioRunner(
            origin_client=origin,
            proxy_client=proxy,
            max_response_bytes=1_048_576,
            timeout_seconds=5,
        ).run(scenario)
        print(run_to_json(result))

asyncio.run(main())
```

The caller explicitly chooses the two base URLs. Use this only for systems you
own or are authorized to test. The runner has per-request timeouts, a response
size cap, no redirect following, and only GET/HEAD support. Scenario documents
cannot contain absolute URLs or path traversal segments.

## Scenario format

See [examples/scenarios/stale-authorization.yml](../examples/scenarios/stale-authorization.yml).
Each request may assert an expected status, observed cache state, or body marker.
Assertions are evaluated independently and failures are retained in the run
record. A transport error stops the scenario and produces an ERROR result.

## Evidence and privacy

V3 stores response status, a small allowlist of response headers, elapsed time,
body size, SHA-256 digest, cache diagnostics, and assertion outcomes. It does
not store response bodies or request header values. Sensitive response headers
are omitted. Sensitive query parameter values are redacted in trace paths.

The body marker assertion is evaluated in memory. The marker itself is not
copied into the trace.

## Persist and compare runs

```python
from remnant.v3 import V3EvidenceStore

store = V3EvidenceStore("reports/v3-evidence.sqlite3")
store.save(result)
previous = store.list_runs(scenario_id=scenario.scenario_id, limit=2)
if len(previous) == 2:
    comparison = store.compare(previous[1]["run_id"], previous[0]["run_id"])
    print(comparison)
```

The V3 evidence database is separate from the frozen V2 evidence schema. Writes
are transactional, run IDs are unique, and comparisons report changed steps,
status codes, body digests, cache diagnostics, and assertion outcomes. Response
bodies and secret request values are not persisted.

## Identity isolation

`evaluate_identity_isolation` is a strict, side-effect-free oracle. It confirms
only when:
- requester direct-origin response is HTTP 403;
- proxy response is HTTP 200;
- proxy cache state is HIT; and
- proxy body contains the expected canary belonging to a different identity.

Unknown or incomplete observations remain INDETERMINATE. This oracle is separate
from the V2 stale-replay oracle and does not alter it.

## Real Varnish integration

See [the Varnish fixture README](../examples/varnish-cache/README.md). It runs
an isolated Varnish 7.6 instance and a local test origin. The fixture deliberately
omits the principal query parameter from its cache key, demonstrating both stale
authorization replay and cross-identity cache collision. It is intentionally
vulnerable and must never be deployed as a real proxy configuration.

## Interpretation

Protocol cacheability and observed HIT/MISS state are diagnostic evidence, not
security findings. The V2 three-condition oracle remains unchanged. A V3
identity-isolation result is confirmed only by its own explicit four-condition
oracle. A negative result covers only the requests and cache behavior actually
exercised; it does not establish that a system is free of cache vulnerabilities.
