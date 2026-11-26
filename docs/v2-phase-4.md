# REMNANT V2 — Phase 4 completion record

## Scope delivered

Phase 4 implemented realistic service-boundary coverage, Redis recovery, concurrent isolation, and a separately selectable tenant-aware V2 replay path while preserving the V1 default experiment path and exact three-condition finding oracle.

### Task 1 — Loopback origin and real Redis

- Implemented a loopback-only HTTP origin adapter with literal loopback IP validation, finite timeouts, disabled environment proxies/redirects, and managed client/server cleanup.
- Added a real Uvicorn-hosted FastAPI origin and full replay against Redis 7.
- User-reported WSL full suite: 188 passed. GitHub Actions run 45812298565: 188 passed in 3.17s.

### Task 2 — Redis failure and recovery

- Added transient read failure, cache-prime write failure, and replay-read failure scenarios using a fault-injection proxy over real Redis.
- Verified failures remain BACKEND_ERROR / NOT_FOUND rather than false findings, and later independent runs recover.
- User-reported WSL full suite: 191 passed. GitHub Actions run 45812812842: 191 passed in 2.98s.

### Task 3 — Concurrent isolation

- Added bounded concurrent runs for identical principal/resource pairs, different principals on the same resource, and different resources.
- Verified unique experiment IDs/cache keys, expected identity metadata, and no cross-run confirmed finding contamination.
- Added concurrent store/observe coverage for a deliberately shared key. Redis SET replaces the serialized response-plus-metadata value atomically; competing writers may overwrite, and no deterministic winner or end-to-end linearizability is claimed.
- Shared mutable policy objects are outside the supported concurrency guarantee.

### Task 4 — V2 PolicyEngine experiment path

- Added PolicyEngineAdapter and create_v2_protected_origin_app as an additive selectable path; the default V1 constructor and AuthorizationPolicy path remain unchanged.
- Tenant context is resolved from IdentityRegistry, resource ownership from ResourceRegistry, and grant/revoke operations from PermissionStore.
- Tenant context is included in V2 cache keys and CacheMetadata and validated during cache replay.
- Added end-to-end same-tenant replay and cross-tenant denial tests, plus tenant-admin boundary, explicit-deny precedence, inactive tenant, suspended/removed/unknown identity, unknown tenant, and unknown resource tests.
- Verified tenant evidence persists through SQLite and JSON reports using the existing allow-listed analysis record; no schema migration was needed.

### Task 5 — Evidence, reporting, and documentation

- Updated README, architecture, security limitations, and the V2 tenant-aware path guide.
- Documented cache digest trust boundary, Redis SET concurrency guarantee limits, and the fact that shared mutable policies are not declared thread-safe.
- Kept response bodies, secrets, arbitrary headers, and full cache keys out of persisted analysis and reports.

## Consolidated CI validation

- Latest PR-head GitHub Actions run: 45814641214.
- Environment: Python 3.12 / Redis 7.
- Result: 201 passed in 3.29s.
- Workflow URL: https://github.com/trilochan-prabakar/REMNANT/actions/runs/45814641214

## Final local verification

Consolidated WSL verification of the complete Phase 4 branch is still pending. Earlier user-reported WSL results (188 and 191) apply to Tasks 1 and 2 at their respective commits, not to the final 201-test branch.

## Scope and release boundary

- The exact V1 finding oracle is unchanged: origin HTTP 403 AND cache HIT AND expected canary present.
- Differential analysis remains diagnostic evidence, not a second finding oracle.
- REMNANT remains a controlled test harness, not a production identity provider, arbitrary website scanner, CDN-wide validator, or claim of distributed linearizability.
- PR #1 remains open and Draft on remnant-v2-development. No merge or main-branch change was made.