# REMNANT V2 Phase 2 — Cache and Response Analysis Implementation Plan

> **Status:** Complete — implementation and validation recorded in [v2-phase-2.md](../../v2-phase-2.md).

**Goal:** Make cache state and response comparison explicit while preserving independent origin authorization and the V1 replay-finding oracle.

**Specification:** [2026-11-26-cache-response-analysis-design.md](../specs/2026-11-26-cache-response-analysis-design.md)

## Global constraints

- Do not change `main` or merge PR #1 during implementation.
- Preserve V1 public imports and current experiment behaviour.
- Keep authorization decisions out of cache adapters.
- The protected origin must continue to authorize independently.
- Keep the finding oracle exactly: origin denies AND cache HIT AND expected canary matches.
- Do not implement invalidation, temporal measurements, concurrency/fault injection, CLI redesign, or new reporting surfaces in Phase 2.
- Redis integration tests must use unique key prefixes and must never flush the database.

## Task 1 — Cache observation model and metadata

**Likely files:** `src/remnant/cache/models.py`, `src/remnant/cache/metadata.py`, `src/remnant/cache/manager.py`, cache tests.

1. Add an additive cache outcome model for HIT, MISS, EXPIRED, UNKNOWN, BACKEND_ERROR, and INVALID_METADATA.
2. Add versioned metadata with principal/resource identity dimensions, optional tenant identity, creation/expiry information, response status, and body digest.
3. Validate schema version, field types, identity consistency, and digest when reading.
4. Preserve the legacy `CacheStatus` and `CacheResult` API through compatibility aliases/adapters where practical.
5. Add unit tests for valid round trips, malformed JSON/metadata, unknown schema versions, digest mismatch, expiration and invalid TTL inputs.

**Exit:** all cache-state distinctions have deterministic tests; legacy tests still pass.

## Task 2 — Cache adapter contract and Redis adapter

**Likely files:** `src/remnant/cache/protocols.py`, `src/remnant/cache/redis.py` (or a carefully scoped refactor of `manager.py`), adapter tests.

1. Define a minimal storage-only cache adapter protocol.
2. Adapt the existing Redis implementation without moving policy logic into it.
3. Map Redis absence, expiry, malformed records and backend errors to their distinct observation states.
4. Add a deterministic in-memory/fake adapter for unit tests if existing test fakes cannot satisfy the contract.
5. Run the same contract tests against fake and Redis adapters where available.

**Exit:** cache adapter contract tests pass; Redis integration tests are isolated and safe.

## Task 3 — Origin adapter

**Likely files:** `src/remnant/origin/protocols.py`, `src/remnant/origin/fastapi.py`, origin tests.

1. Define a small origin request/response contract.
2. Wrap the current protected FastAPI ASGI app with an in-process adapter.
3. Preserve the origin's independent authorization check and existing HTTP semantics.
4. Test allow, deny, unknown resource, malformed request and transport error handling.

**Exit:** existing origin behaviour remains compatible and adapter tests pass.

## Task 4 — Differential response analyzer

**Likely files:** `src/remnant/analysis/models.py`, `src/remnant/analysis/differential.py`, new analyzer tests.

1. Normalize origin and cache response observations.
2. Compare status code, selected security-relevant headers, body digest and canary result.
3. Return per-dimension results plus an explicit overall state (MATCH, DIFFERENT, or INDETERMINATE).
4. Do not treat missing/error observations as ordinary differences.
5. Avoid storing or logging full protected response bodies in analyzer output.

**Exit:** pure analyzer tests cover matches, meaningful differences and indeterminate inputs.

## Task 5 — Finding oracle integration and negative controls

**Likely files:** `src/remnant/engine/experiment.py`, `src/remnant/analysis/oracle.py` (if separation is useful), experiment tests.

1. Integrate the richer cache observation without breaking `CacheReplayExperiment.run` or `ExperimentResult` consumers.
2. Preserve the exact three-condition positive oracle.
3. Add independent negative controls for origin allow, cache miss, expired/unknown/backend-error/invalid-metadata states, missing canary and canary mismatch.
4. Add principal/tenant/resource isolation tests.
5. Keep differential comparison as supporting evidence; it must not independently confirm a replay finding.

**Exit:** positive and negative oracle tests pass; no false positive from a partial condition.

## Task 6 — Full regression and evidence

1. Run focused tests after each task.
2. Run the complete test suite.
3. Run Redis integration tests against localhost Redis when available; record skips accurately.
4. Inspect the diff for compatibility regressions, unsafe Redis cleanup, accidental body logging and scope creep.
5. Update the Phase 2 status document with actual implemented capabilities and exact test counts only after verification.

**Phase 2 completion gate:** all acceptance criteria in the specification are met, the full suite passes, and the implementation is reviewed. Keep PR #1 draft until then.


## Final validation

See [Phase 2 completion record](../../v2-phase-2.md) for the exact local and GitHub Actions test results and review boundaries. The full suite passed with 148 tests locally and in CI, including both real-Redis integration tests. PR #1 remains Draft and `main` remains unchanged.
