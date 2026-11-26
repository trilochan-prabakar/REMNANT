# REMNANT V2 Phase 4 — Realistic Testing and Robustness Plan

 > **Status:** Tasks 1–5 implementation complete; consolidated local validation and final review pending.

**Specification:** [2026-11-26-phase-4-realistic-robustness-design.md](../specs/2026-11-26-phase-4-realistic-robustness-design.md)

## Global guardrails

- [ ] Work only on `remnant-v2-development`.
- [ ] Keep PR #1 open and Draft; do not merge or mark ready.
- [ ] Do not modify `main`.
- [ ] Preserve V1-compatible constructors, runner, finding oracle, evidence stages, and legacy reports.
- [ ] No arbitrary external targets, AI/ML, V3, or production-readiness claims.
- [ ] Never use Redis `FLUSHDB` or `FLUSHALL`; isolate test keys with unique prefixes.

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

**Exit:** implemented; GitHub Actions has passed the initial concurrency suite (201 total tests). The final expanded suite will be rerun after the tenant evidence/report regression addition. Local WSL verification is pending.

## Task 4 — V2 PolicyEngine end-to-end tenant path

- [x] Finalize additive PolicyEngineAdapter seam without changing the V1 default path.
- [x] Resolve tenant context from IdentityRegistry; caller-supplied tenant data is not used.
- [x] Resolve resource tenant/owner from ResourceRegistry through PolicyEngine.
- [x] Integrate PolicyEngine and PermissionStore grant/revoke behavior.
- [x] Include trusted tenant context in cache key and metadata.
- [x] Test cross-tenant access is denied before cache priming/replay.
- [x] Test tenant-admin boundary, explicit-deny precedence, inactive tenant, suspended/removed/unknown identity, unknown tenant, and unknown resource.
- [x] Preserve the existing V1 default experiment path and public API.

**Exit:** tenant-isolation scenarios and SQLite/JSON evidence persistence are implemented; consolidated validation pending.

## Task 5 — Evidence, reporting, and documentation

- [x] Add safe tenant context to existing allow-listed cache metadata evidence; no schema migration was needed.
- [x] Keep bodies, secrets, arbitrary headers, and full cache keys out of persistence/reports.
- [x] Preserve existing NOT_FOUND vs BACKEND_ERROR observation distinction and oracle behaviour.
- [x] No migration required: existing analysis JSON schema already supports optional tenant_id.
- [x] Update architecture, security limitations, README, and tenant-aware experiment documentation.

**Exit:** V1 and V2 report/storage compatibility tests pass; limitations match implemented behavior.

## Task 6 — Full validation and review

- [ ] Run focused tests after each task.
- [ ] Run the complete WSL suite after all Phase 4 tasks; record user-reported output.
- [ ] Run GitHub Actions after all Phase 4 tasks on Python 3.12 / Redis 7.
- [ ] Repeat service-boundary and concurrency tests to check determinism.
- [ ] Review changed files, security boundaries, and regressions.
- [ ] Confirm PR #1 remains Draft and main is untouched.

**Completion gate:** all Phase 4 acceptance criteria in the spec are met; local and CI results are recorded independently.
