# REMNANT V2 — Phase 2.1 integration record

**Status:** Integration implementation and validation complete  
**Branch:** `remnant-v2-development`  
**Validation date:** 2026-11-26

## Integrated experiment pipeline

The `CacheReplayExperiment.run()` workflow now uses the V2 observation path end to end:

1. Cache priming creates schema-versioned `CacheMetadata` containing principal/resource identity, response status, timestamps, and a SHA-256 body digest.
2. Cache reads use `RedisCacheManager.observe()` and preserve explicit observation outcomes.
3. A HIT is accepted by the experiment only when metadata is present and its principal/resource identity matches the request.
4. The experiment calls `evaluate_observation_finding()` directly for the exact three-condition finding oracle.
5. The independently obtained origin response and cache observation are passed to `compare_responses()`; the resulting differential state is exposed as additive experiment evidence.

## Compatibility

- Existing `ExperimentResult` fields remain intact; `cache_observation_status` and `differential_state` are additive optional fields.
- The legacy `evaluate_finding()` signature and `FindingOracle` result type remain available.
- Existing V1 cache status/result APIs and metadata-free Redis payload compatibility remain intact.
- The experiment's existing cache-status output remains compatible with V1 consumers.

## Additional regression coverage

- End-to-end experiment emits a HIT observation and differential result.
- Stored cache metadata identifies the expected principal/resource and includes response status and SHA-256 digest.
- Cache metadata with a mismatched principal identity is rejected and cannot confirm a finding.

## Validation evidence

### Local WSL
The user ran the complete suite after pulling the integrated branch:

```
150 passed
```

### GitHub Actions
- [Workflow run 45807085607](https://github.com/trilochan-prabakar/REMNANT/actions/runs/45807085607)
- Python 3.12 / Redis 7
- Result: `150 passed in 2.51s`
- Workflow completed successfully.

## Scope and boundaries

This integration closes the component-to-experiment wiring gap identified during the V2 architecture review. It does not implement cache invalidation/revocation propagation, concurrency/race experiments, temporal benchmarking, distributed fault injection, or production identity infrastructure. Those remain candidates for separately scoped future work.

**Repository safety:** `main` remains unchanged. PR #1 remains open and Draft. No merge or Ready-for-review action has been taken.
