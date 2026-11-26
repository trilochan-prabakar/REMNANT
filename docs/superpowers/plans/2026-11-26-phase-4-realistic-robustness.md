# REMNANT V2 Phase 4 — Realistic Testing and Robustness Plan

> **Status:** Task 1 complete; Task 2 implementation committed, validation pending.

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

**Exit:** implementation and tests committed; focused WSL and GitHub Actions validation pending. Initial-read recovery also verifies SQLite persistence and JSON oracle output.

## Task 3 — Concurrent isolation and race behavior

- [ ] Run bounded simultaneous experiments against shared Redis.
- [ ] Cover same principal/resource, different principals, and different resources.
- [ ] Assert unique experiment IDs/cache keys and correct metadata identity.
- [ ] Verify no cross-run cache consumption or cross-run finding.
- [ ] Test concurrent store/observe on a deliberately shared key.
- [ ] State exactly which guarantees come from Redis atomic SET; avoid unsupported linearizability claims.
- [ ] Document shared mutable policy limitations if observed.

**Exit:** deterministic bounded concurrency tests pass repeatedly without cross-run contamination.

## Task 4 — V2 PolicyEngine end-to-end tenant path

- [ ] Finalize additive policy adapter/controller seam before implementation.
- [ ] Resolve tenant context from IdentityRegistry, never a caller-supplied tenant field.
- [ ] Resolve resource tenant/owner from ResourceRegistry.
- [ ] Integrate PolicyEngine and PermissionStore grant/revoke behavior.
- [ ] Include trusted tenant context in cache key and metadata.
- [ ] Test tenant A cannot access tenant B's resource via origin or cache.
- [ ] Test tenant-admin boundary, explicit deny, inactive tenant, suspended/removed identity, and unknown resource.
- [ ] Preserve the existing V1 default experiment path and public API.

**Exit:** tenant-isolation scenarios pass through origin, cache, evidence persistence, and reports.

## Task 5 — Evidence, reporting, and documentation

- [ ] Add only safe, necessary tenant/failure evidence.
- [ ] Keep bodies, secrets, arbitrary headers, and full cache keys out of persistence/reports.
- [ ] Distinguish NOT_FOUND from indeterminate backend failure.
- [ ] Add transactional/idempotent migration only if the approved evidence schema requires it.
- [ ] Update architecture, security limitations, README, and Phase 4 completion record.

**Exit:** V1 and V2 report/storage compatibility tests pass; limitations match implemented behavior.

## Task 6 — Full validation and review

- [ ] Run focused tests after each task.
- [ ] Run the complete WSL suite; record user-reported output.
- [ ] Run GitHub Actions on Python 3.12 / Redis 7.
- [ ] Repeat service-boundary and concurrency tests to check determinism.
- [ ] Review changed files, security boundaries, and regressions.
- [ ] Confirm PR #1 remains Draft and main is untouched.

**Completion gate:** all Phase 4 acceptance criteria in the spec are met; local and CI results are recorded independently.
