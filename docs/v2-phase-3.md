# REMNANT V2 — Phase 3 Completion Record

**Status:** Implementation complete; local and CI validation passed  
**Branch:** `remnant-v2-development`  
**Validation date:** 2026-11-26

## Delivered

Phase 3 closes the integration gap between the V2 cache/origin components, experiment execution, durable evidence, and generated reports.

1. **Origin adapter integration:** all experiment origin requests pass through the `OriginAdapter` boundary. The default implementation uses the in-process FastAPI/ASGI origin. The synchronous runner rejects calls from an active event loop; transport errors propagate.
2. **Structured analysis evidence:** each V2 experiment can carry body-free evidence for origin statuses, cache observations, metadata validation, differential comparison dimensions, and allow-listed diagnostic categories.
3. **SQLite migration:** `PRAGMA user_version` tracks schema version. The additive `experiment_analysis` table is migrated transactionally and idempotently. Future schema versions are rejected, and analysis is saved in the same transaction as the experiment summary, stages, and finding.
4. **Reporting:** V2 records produce JSON report schema `2.0` and an HTML analysis section. The six legacy stages and three-condition oracle remain. Legacy records remain reportable as schema `1.0` with an explicit missing-analysis state.
5. **End-to-end coverage:** positive, negative/expired, cache-backend-error, and origin-transport-error cases are exercised through the experiment and persistence/reporting pipeline.

## Finding oracle and data boundaries

The finding oracle is unchanged:

```text
origin returns HTTP 403 AND cache path is HIT AND cached response contains expected canary
```

Differential analysis is supporting diagnostic evidence, not an alternate finding oracle. Persisted V2 analysis excludes raw response bodies and full cache keys. The implementation does not claim to scan arbitrary applications or prove the absence of vulnerabilities.

## Validation

### Local WSL

User-reported full-suite result after pulling the completed Phase 3 implementation:

```text
168 passed
```

### GitHub Actions

- [Workflow run 45810259829](https://github.com/trilochan-prabakar/REMNANT/actions/runs/45810259829)
- Environment: Python 3.12 / Redis 7
- Result: `168 passed in 2.07s`
- Job conclusion: success

## Repository safety

- Changes are on `remnant-v2-development`.
- PR #1 remains open and Draft.
- `main` was not modified or merged.
- No Ready-for-review transition was performed.

## Deferred work

Phase 3 does not add distributed cache experiments, concurrency/race testing, temporal invalidation benchmarking, production identity infrastructure, arbitrary target discovery, or AI/ML. Those require separate designs and validation before a later phase.
