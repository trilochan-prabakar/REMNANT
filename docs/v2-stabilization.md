# REMNANT V2 — Stabilization Follow-up

**Status:** Implementation updates complete; local validation reported by the user  
**Branch:** `remnant-v2-development`  
**Pull request:** #1 (Draft; not merged)

## 1. Redis cache-write failure semantics

A Redis write failure during cache priming is retained as a `BACKEND_ERROR` observation. The in-memory origin response is not treated as a successful cache entry and is not passed to the finding oracle as a cache `HIT`. The experiment can continue to capture the independent post-revocation origin decision and replay observation.

Regression coverage exercises a Redis client that permits reads but raises a backend error on writes, then verifies the result through SQLite and JSON reporting.

## 2. Origin adapter event-loop lifecycle

The synchronous experiment runner creates one event loop per run and reuses it for every asynchronous origin-adapter request in that run. The loop is closed when the run completes. An adapter may reuse loop-bound asynchronous resources within one run, but must not retain them across separate calls to the synchronous `run()` method. Calling `run()` from an already-running event loop remains unsupported and is rejected.

Regression tests verify that the three origin requests in a run share one loop and that separate runs receive separate loops.

## 3. Explicit security boundaries

- Cache `body_sha256` verifies consistency between the response body and its accompanying digest. Since both are stored in the same Redis payload, it does not authenticate the payload against an actor able to rewrite both values. The current design assumes Redis is within the trusted test boundary; it does not use a MAC or signature.
- V2 `PolicyEngine` is a separately tested authorization foundation. The integrated `CacheReplayExperiment` still uses the V1-compatible `AuthorizationPolicy` grant/revoke flow. End-to-end tenant-aware policy enforcement and tenant-isolated replay remain future work.

These boundaries are also documented in [security-and-limitations.md](security-and-limitations.md) and [architecture.md](architecture.md).

## Validation

The user reported the full local WSL test suite passing after the Redis write-failure and origin lifecycle changes:

```text
171 passed
```

This is a user-reported local result, not a claim that the assistant executed the WSL environment. GitHub Actions validation for the stabilization commits should be checked separately.

## Repository safety

- All changes are confined to `remnant-v2-development`.
- PR #1 remains Draft.
- `main` remains untouched and unmerged.
