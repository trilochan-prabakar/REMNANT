# REMNANT V2 Phase 3 — Evidence and Architecture Integration Plan

> **Status:** Complete — local and GitHub Actions validation passed.

**Goal:** Complete the experiment's origin-adapter integration and persist/report V2 cache-observation and differential evidence while preserving V1 compatibility.

**Specification:** [2026-11-26-phase-3-evidence-integration-design.md](../specs/2026-11-26-phase-3-evidence-integration-design.md)

## Global constraints

- Work only on `remnant-v2-development`; do not modify `main`.
- Keep PR #1 open and Draft; do not merge or mark ready for review.
- Preserve all existing V1 `ExperimentResult`, `evaluate_finding`, cache, storage, and report contracts.
- The exact finding oracle remains origin HTTP 403 AND cache HIT AND expected canary match.
- Differential analysis is supporting evidence, never an alternate finding oracle.
- Do not persist response bodies, secrets, credentials, full cache keys, or arbitrary headers.
- SQLite changes must be additive, transactional, idempotent, and tested against an existing pre-migration database.
- Do not introduce Phase 4 concurrency/fault injection, temporal benchmarking, distributed cache experiments, CLI redesign, or AI/ML.

## Task 1 — Origin adapter becomes the engine transport boundary

**Files:** `src/remnant/engine/experiment.py`, `src/remnant/origin/fastapi.py`, origin and experiment tests.

1. Add optional `origin_adapter` constructor support.
2. Preserve default origin app and existing `origin_app` / `policy` call patterns by wrapping the app in `FastAPIOriginAdapter`.
3. Route initial authorization, cache-fill, and post-revocation direct requests through the adapter.
4. Keep the synchronous `run()` interface; fail clearly if invoked from an already-running event loop.
5. Ensure transport errors cannot be mistaken for HTTP 403, cache MISS, or a confirmed finding.

**Exit:** fake-adapter engine tests pass and existing constructor/behavior tests remain unchanged.

## Task 2 — Finalize additive experiment evidence

**Files:** `src/remnant/engine/experiment.py`, analysis models, experiment tests.

1. Define a stable, serializable, body-free analysis evidence shape.
2. Include cache observation outcomes and safe metadata validation summary.
3. Include differential overall and per-dimension states.
4. Preserve all existing result fields and defaults.
5. Keep raw response bodies, full cache keys, and secrets out of the evidence.

**Exit:** result evidence serializes deterministically and the legacy result API remains compatible.

## Task 3 — SQLite schema versioning and additive migration

**Files:** `src/remnant/storage/sqlite.py`, storage tests.

1. Introduce explicit schema version tracking.
2. Add `experiment_analysis` as a one-to-one table keyed to existing experiments.
3. Migrate existing databases transactionally and idempotently.
4. Reject unsupported future schema versions clearly.
5. Keep existing tables and query shapes intact.
6. Store analysis evidence in the same transaction as experiment summary/evidence/finding.

**Exit:** fresh DB, pre-migration DB, repeated migration, rollback, and legacy result tests pass.

## Task 4 — JSON and HTML reporting

**Files:** `src/remnant/reporting/reports.py`, reporting tests.

1. Add report schema 2.0 for records with V2 analysis.
2. Preserve existing V1 report fields and six stages.
3. Add cache observation, metadata validation, and differential dimension summaries.
4. Render legacy records with an explicit missing-analysis state.
5. Escape all untrusted strings and prove that bodies, secrets, and full cache keys are absent.

**Exit:** JSON and HTML tests pass for both legacy and V2 records.

## Task 5 — End-to-end evidence and compatibility tests

**Files:** experiment, storage, reporting tests.

1. Run a full fake-origin/fake-cache experiment through persistence and report generation.
2. Verify the same experiment ID, finding result, cache status, metadata identity and differential state survive reload.
3. Verify origin transport and cache backend errors cannot produce a confirmed finding.
4. Verify pre-migration SQLite records remain readable and reportable.
5. Preserve the exact oracle and Redis integration safety.

**Exit:** end-to-end pipeline tests cover positive, negative, indeterminate and legacy cases.

## Task 6 — Documentation and release validation

- [x] Update README to describe the current V2 experiment path and its limits.
- [x] Update architecture and security/limitations docs.
- [x] Add `docs/v2-phase-3.md` with implementation and validation results.
- [x] Run focused tests after each task.
- [x] Run the full local test suite; user-reported result: **168 passed**.
- [x] Confirm GitHub Actions passes on Python 3.12 / Redis 7: 168 passed in 2.07s.
- [x] Review compatibility, migration safety, data minimization, and scope boundaries; see the Phase 3 completion record.

**Completion gate:** all Phase 3 acceptance criteria in the specification are met; exact local and CI counts are recorded; PR remains Draft and `main` remains untouched.
