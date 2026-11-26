# REMNANT V3 — scope and implementation boundary

## Objective

Expand REMNANT from a focused cache-authorization replay experiment into a controlled,
repeatable HTTP cache security and behavior testing framework. V3 adopts proven
capabilities from established projects while preserving REMNANT's core authorization
consistency objective.

V3 is not a general-purpose internet scanner. Experiments must be explicitly configured
for controlled systems that the operator owns or is authorized to test.

## Frozen compatibility boundary

- V1 behavior remains available and unchanged.
- V2 is frozen: do not edit, refactor, migrate, or change V2 modules, tests, schemas,
  report contracts, or examples.
- V3 implementation is additive under `src/remnant/v3/`, with V3-specific tests and
  documentation. Shared V1/V2 behavior is consumed through existing public interfaces;
  existing contracts are not changed to accommodate V3.

## Selected feature set

### 1. HTTP cache analysis

- Parse Cache-Control, Expires, Date, Age, Vary, and Set-Cookie.
- Distinguish not-cacheable, private-only, requires-revalidation, cacheable, and
  unspecified freshness.
- Observe common cache-state headers, including Cache-Status and common vendor headers.
- Flag Authorization-bearing request/response combinations that require careful
  shared-cache reuse analysis.
- Keep protocol diagnostics separate from vulnerability findings.

### 2. Controlled security experiments

- Preserve the existing three-condition stale-authorization finding oracle.
- Add explicit identity-isolation experiments to test whether one principal can receive
  another principal's protected representation.
- Add resource-content update, revocation, and explicit cache-invalidation scenarios.
- Use validated, repeatable scenario definitions; no automatic unrestricted crawling.

### 3. Real cache implementations

- Retain the existing Nginx demonstration.
- Add Varnish as a second real reverse-proxy integration.
- Represent proxy capabilities and invalidation semantics explicitly; do not pretend
  that Nginx and Varnish expose identical purge/ban behavior.

### 4. Execution and robustness

- Execute controlled scenarios against configured origin/proxy fixtures.
- Support bounded concurrency, request timeouts, setup/teardown, and clear failure states.
- Preserve per-request traces needed to explain a result.

### 5. Evidence and reporting

- Produce structured, reproducible experiment results.
- Include cache behavior diagnostics, request/response traces with secrets redacted,
  and comparison between runs.
- Do not assign generic severity/CVSS or confidence scores: the framework records
  controlled observations, while impact depends on target-specific asset sensitivity,
  exposure, and business context.
- Never promote a cache HIT, protocol anomaly, or heuristic score into a confirmed
  authorization finding without satisfying the strict oracle.

## Explicit exclusions

- General-purpose arbitrary-target crawling or internet-wide scanning.
- Request smuggling, desynchronization, or other high-impact probing.
- A generic plugin framework without a concrete need.
- ML/AI-based vulnerability classification.
- New novelty claims; V4 is reserved for separately researched novelty.

## Initial implementation sequence

1. Additive HTTP cache response analysis and unit tests.
2. V3 scenario execution model that consumes validated scenario data without altering
   the existing V2 dry-run transition engine.
3. Identity-isolation and resource lifecycle experiment types.
4. Varnish integration fixture and repeatable integration checks.
5. Trace/evidence and run-comparison support, with secret redaction.
6. End-to-end tests, documentation, and a V3 release checklist.

Each stage must have tests and a definition of done. No feature is added merely because a
reference project has it; it must strengthen REMNANT's stated objective.


## Implementation status

The following planned V3 capabilities have been implemented on the `v3-development` branch:

- [x] HTTP cache directive parsing, common cache-state headers, Age/Date/Expires freshness estimate, and Authorization-response diagnostics.
- [x] Strict YAML scenario schema with relative-path-only requests, GET/HEAD allowlist, header validation, bounded step count, and no executable scenario content.
- [x] Asynchronous origin/proxy scenario runner with per-request timeouts, response-size cap, no redirects, redacted evidence, and explicit PASS/FAIL/ERROR outcomes.
- [x] Independent four-condition identity-isolation oracle.
- [x] Explicit grant/revoke, resource-content update, and proxy PURGE lifecycle steps.
- [x] Separate transactional V3 SQLite evidence store and deterministic run comparison.
- [x] Isolated real Varnish fixture covering stale replay, cross-principal cache-key collision, resource update staleness, and PURGE invalidation.
- [x] V3-specific GitHub Actions workflow and tests.

Completion is not declared until the full existing regression suite, the V3-specific suite, and the Varnish integration workflow pass. CI results and any remaining limitations must be recorded before V3 is considered release-ready.
