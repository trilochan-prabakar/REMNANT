# Cache–Origin Replay Experiment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run and inspect a controlled authorization revocation and cached response replay experiment.

**Architecture:** Add an engine-level orchestration class that calls the existing origin app independently and routes the normal request through the cache manager. Return explicit step results and the three-part finding oracle.

**Tech Stack:** Python 3.12, FastAPI, HTTPX ASGI transport, Redis, pytest.

**Spec:** `docs/superpowers/specs/2026-11-23-cache-origin-replay-design.md`

## Global Constraints

- Do not invalidate or delete the cached response when Alice's permission is revoked.
- The origin authorization check remains independent of the cache.
- Finding condition is exactly ORIGIN DENIES AND CACHE HIT AND CANARY MATCH.
- Do not add evidence storage, reporting, dashboard, or later phase features.
- Preserve existing files and workspace state; do not switch branches or reset.

## Review Focus

- Principal/resource cache-key isolation — test independent principals and resources.
- False positives from partial oracle matches — test origin allow, cache miss, and canary mismatch separately.
- Origin error and permission sequence — assert direct origin denial after revocation.
- Redis test isolation — use unique per-test key prefixes and do not flush the database.
- Result inspectability — assert each oracle boolean and final status.

---

### Task 1: Experiment orchestration and deterministic oracle

**Files:**
- Create: `src/remnant/engine/experiment.py`
- Modify: `src/remnant/engine/__init__.py`
- Test: `tests/test_experiment.py`

**Interfaces:**
- Consumes: `AuthorizationPolicy`, `remnant.api.app.app`, `PROTECTED_RESOURCES`, `RedisCacheManager`, `CachedHTTPResponse`.
- Produces: `CacheReplayExperiment.run(principal_id, resource_id, *, ttl_seconds=60) -> ExperimentResult`; `ExperimentResult` exposes initial status, priming state/canary, revocation state, bypassed origin status, normal cache status, canary match, each oracle boolean, and finding status.

- [ ] **Step 1: Write failing unit tests** for authorized priming, preserved cached entry and origin 403 after revocation, cached replay and positive finding, each individual negative oracle condition, and principal/resource isolation. Use the existing deterministic fake Redis pattern.
- [ ] **Step 2: Run** `pytest tests/test_experiment.py -q`; expect failures because the experiment API does not exist.
- [ ] **Step 3: Implement** the runner with isolated ASGI requests. The cache key must encode both principal and resource. Only a successful origin response is stored. Never delete or rewrite an entry during revoke. Compute finding as the conjunction of the three explicit condition fields.
- [ ] **Step 4: Run** `pytest tests/test_experiment.py -q`; expect all focused unit tests to pass.
- [ ] **Step 5: Run** `pytest -q`; expect the full suite to pass.

### Task 2: Real Redis replay integration and verification

**Files:**
- Create: `tests/test_experiment_redis_integration.py`
- Modify: none

**Interfaces:**
- Consumes: `CacheReplayExperiment` and the existing localhost Redis integration convention.
- Produces: Real Redis coverage of the complete experiment using a unique key prefix.

- [ ] **Step 1: Write failing integration coverage** for the complete positive replay sequence and verify the cached entry retains a positive TTL after revocation.
- [ ] **Step 2: Run** `pytest tests/test_experiment_redis_integration.py -q`; expect failure because the integration test is not implemented.
- [ ] **Step 3: Implement** the integration test with a unique prefix; skip only when localhost Redis is unavailable. Do not flush Redis or delete unrelated keys.
- [ ] **Step 4: Run** `pytest -q`; record the exact pass/fail/skip counts.
- [ ] **Step 5: Run** the central experiment against real Redis and capture its structured result, including finding=true.
