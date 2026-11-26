# REMNANT V2 Phase 4 — Realistic Testing and Robustness Plan

> **Status:** COMPLETE — all six tasks implemented, CI passed, and consolidated local WSL validation passed (201 tests).

**Specification:** [2026-11-26-phase-4-realistic-robustness-design.md](../specs/2026-11-26-phase-4-realistic-robustness-design.md)

## Global guardrails

- [x] Work only on `remnant-v2-development`.
- [x] Keep PR #1 open and Draft; do not merge or mark ready.
- [x] Do not modify `main`.
- [x] Preserve V1-compatible constructors, runner, finding oracle, evidence stages, and legacy reports.
- [x] No arbitrary external targets, AI/ML, V3, or production-readiness claims.
- [x] Never use Redis `FLUSHDB` or `FLUSHALL`; isolate test keys with unique prefixes.

## Task 1 — Loopback origin and real Redis integration profile

- [x] Design explicit network-origin adapter lifecycle and timeout behavior.
- [x] Implement `LoopbackHTTPOriginAdapter` with literal-loopback-only URLs, bounded timeouts, no environment proxies/redirects, and per-request client cleanup.
- [x] Add a real Uvicorn-hosted FastAPI origin on loopback and an ephemeral port in integration tests.
- [x] Add a full experiment test using the existing Redis 7 CI service.
- [x] Pull and run the focused and full test suites in local WSL (user-reported full suite: **188 passed**).
- [x] Confirm GitHub Actions passes with the loopback/Redis integration tests (run 45812298565: **188 passed in 3.17s**, Python 3.12 / Redis 7).
- [x] Verify readiness, deterministic shutdown, and failure cleanup through the managed Uvicorn fixture.
- [x] Keep in-process ASGI as the fast default.
- [x] Restrict adapter to literal loopback IPs and test rejection of external/ambiguous targets.

**Exit:** focused and full local tests pass; GitHub Actions passes with real loopback HTTP and Redis 7. Server/client cleanup is managed by fixtures and context managers.

## Task 2 — Redis transient failure and recovery

- [x] Test read unavailable at prime followed by recovery using real Redis and a fault-injection proxy.
- [x] Test prime write failure followed by a successful independent run.
- [x] Test replay read failure after a successful prime.
- [x] Assert the failed cache operation is retained as `BACKEND_ERROR` in the corresponding analysis evidence.
- [x] Assert failed prime/replay cannot confirm the finding.
- [x] Assert a later recovered run can confirm the controlled replay.
- [x] Preserve unrelated Redis keys: tests use unique prefixes and delete only their own experiment keys.

**Exit:** complete. User-reported WSL full suite: **191 passed**. GitHub Actions run 45812812842: **191 passed in 2.98s** (Python 3.12 / Redis 7). Initial-read recovery also verifies SQLite persistence and JSON oracle output.

## Task 3 — Concurrent isolation and race behavior

- [x] Run bounded simultaneous experiments against shared Redis using separate experiment/policy instances.
- [x] Cover same principal/resource, different principals, and different resources.
- [x] Assert unique experiment IDs/cache keys and correct metadata identity.
- [x] Verify no cross-run cache consumption or cross-run finding.
- [x] Test concurrent store/observe on a deliberately shared key; assert response and metadata remain paired.
- [x] State exactly which guarantees come from Redis atomic SET; avoid unsupported linearizability claims.
- [x] Document that shared mutable policy objects are outside the concurrency guarantee.

**Exit:** complete. Final PR-head GitHub Actions run 45814641214 passed 201 tests; user-reported consolidated local WSL suite also passed **201 tests**.

## Task 4 — V2 PolicyEngine end-to-end tenant path

- [x] Finalize additive PolicyEngineAdapter seam without changing the V1 default path.
- [x] Resolve tenant context from IdentityRegistry; caller-supplied tenant data is not used.
- [x] Resolve resource tenant/owner from ResourceRegistry through PolicyEngine.
- [x] Integrate PolicyEngine and PermissionStore grant/revoke behavior.
- [x] Include trusted tenant context in cache key and metadata.
- [x] Test cross-tenant access is denied before cache priming/replay.
- [x] Test tenant-admin boundary, explicit-deny precedence, inactive tenant, suspended/removed/unknown identity, unknown tenant, and unknown resource.
- [x] Preserve the existing V1 default experiment path and public API.

**Exit:** complete. Tenant-isolation scenarios and SQLite/JSON evidence persistence passed the final consolidated WSL and CI suites.

## Task 5 — Evidence, reporting, and documentation

- [x] Add safe tenant context to existing allow-listed cache metadata evidence; no schema migration was needed.
- [x] Keep bodies, secrets, arbitrary headers, and full cache keys out of persistence/reports.
- [x] Preserve existing NOT_FOUND vs BACKEND_ERROR observation distinction and oracle behaviour.
- [x] No migration required: existing analysis JSON schema already supports optional tenant_id.
- [x] Update architecture, security limitations, README, and tenant-aware experiment documentation.

**Exit:** V1 and V2 report/storage compatibility tests pass; limitations match implemented behavior.

## Task 6 — Full validation and review

- [x] Add focused tests for the implemented tasks; focused execution is covered by the consolidated CI suite.
- [x] Run the complete WSL suite after all Phase 4 tasks; user-reported result: **201 passed**.
- [x] Run GitHub Actions after all Phase 4 tasks on Python 3.12 / Redis 7 (run 45814641214: 201 passed in 3.29s).
- [x] Include bounded service-boundary and concurrency tests in the final full CI suite.
- [x] Review changed implementation, security boundaries, failure semantics, compatibility, and PR scope.
- [x] Confirm PR #1 remains open and Draft, based on main; branch comparison is ahead 101 / behind 0 and no main changes were made.

**Completion gate:** COMPLETE. Full local WSL validation and GitHub Actions both pass (201 tests each); PR #1 remains Draft and `main` remains untouched.
