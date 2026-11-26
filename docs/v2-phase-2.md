# REMNANT V2 — Phase 2 completion record

**Status:** Implementation and validation complete  
**Branch:** `remnant-v2-development`  
**Validation date:** 2026-11-26  
**Pull request:** [#1 — REMNANT V2 Phase 1: tenant-aware authorization and scenarios](https://github.com/trilochan-prabakar/REMNANT/pull/1) (remains Draft)

## Delivered

### Cache observations and metadata
- Added explicit `HIT`, `MISS`, `EXPIRED`, `UNKNOWN`, `BACKEND_ERROR`, and `INVALID_METADATA` observation states.
- Added schema-versioned metadata carrying principal/resource identity, optional tenant, response status, creation/expiry timestamps, and SHA-256 body digest.
- Added metadata validation and body-digest verification.
- Preserved the V1 `CacheStatus` and `CacheResult` interface; metadata-free Redis payloads retain the legacy shape.

### Cache and origin adapters
- Added a storage-only cache adapter protocol and extended the Redis manager with observation and single-key deletion.
- Redis integration tests use unique per-test prefixes and do not flush the database.
- Added an origin response contract and an HTTPX/ASGI adapter around the protected FastAPI origin.
- The origin continues to make its own authorization decision; cache code contains no authorization policy.

### Differential analysis and finding validation
- Added deterministic comparison of status, selected security headers, body SHA-256 digests, and expected-canary presence.
- Comparison results distinguish `MATCH`, `DIFFERENT`, and `INDETERMINATE`; response bodies are not retained in comparison results.
- Expected-canary comparison only matches when the expected marker is present in both responses. A regression test covers the case where both omit it.
- Preserved the exact finding conjunction: origin returns HTTP 403, cache observation is a HIT, and the cached JSON canary equals the expected value.
- Added negative controls for origin allow, non-HIT cache states, malformed/missing/mismatched canaries, and unexpected origin status.
- Kept the legacy `evaluate_finding` signature and `FindingOracle` result type as a compatibility adapter.

## Validation evidence

### Local WSL validation
The user pulled commit `70c6502567bc29e8a7bfa293bfb8be0000f936a8` and ran the complete suite from the project virtual environment on Python 3.12.3:

```
collected 148 items
148 passed in 3.92s
```

Both real-Redis integration tests passed locally:
- `tests/test_cache_redis_integration.py::test_redis_cache_round_trip_and_ttl_expiration`
- `tests/test_experiment_redis_integration.py::test_real_redis_replays_cached_response_after_permission_revocation`

### GitHub Actions validation
The same branch head completed the Python 3.12 / Redis 7 workflow successfully:
- [Workflow run 45806161961](https://github.com/trilochan-prabakar/REMNANT/actions/runs/45806161961)
- Result: `148 passed in 2.05s`
- Redis 7 service initialized successfully and both Redis integration tests ran.

## Review and boundaries

- Existing V1 tests and public compatibility paths remain in the passing full suite.
- Redis integration tests use unique key namespaces; no `FLUSHDB` or `FLUSHALL` is used.
- The differential result contains response digests and comparison values, not protected response bodies.
- Phase 2 did not add cache invalidation/revocation propagation, temporal benchmarking, concurrency/race experiments, distributed fault injection, CLI/dashboard/report redesign, or AI/ML.
- Phase 1's in-memory tenant and identity registries remain test/framework components, not production identity infrastructure.

## Completion decision

Phase 2 implementation, local validation, CI validation, and scoped review are complete against the Phase 2 acceptance criteria. This is a controlled research/testing framework improvement, not a claim of production readiness or novel cache-invalidation research.

**Repository safety:** `main` was not changed. PR #1 remains open and Draft. Do not merge or mark ready for review without explicit approval.
