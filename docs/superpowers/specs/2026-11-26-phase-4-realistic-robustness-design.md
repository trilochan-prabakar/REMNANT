# REMNANT V2 Phase 4 — Realistic Testing and Robustness Design

**Status:** Design proposed for review; implementation not started  
**Branch:** `remnant-v2-development`  
**Parent:** Phase 3 evidence integration and stabilization follow-up

## 1. Goal

Validate REMNANT V2 across realistic local service boundaries, concurrent experiment execution, transient Redis failures/recovery, and tenant-aware authorization/replay isolation. Phase 4 strengthens the reliability and credibility of the harness; it does not turn REMNANT into a general-purpose scanner or production authorization product.

## 2. Existing behavior and constraints

- `CacheReplayExperiment` is a synchronous orchestration API. Its three async origin calls within one run share one `asyncio.Runner` loop, which closes at run completion.
- The default origin is an in-process FastAPI app behind `FastAPIOriginAdapter`. An `OriginAdapter` can be injected.
- The current integrated replay path uses V1 `AuthorizationPolicy` grant/revoke. V2 `PolicyEngine` and its registries are independently tested, not yet used by the integrated experiment.
- The V2 cache manager uses Redis and exposes explicit observation states. A write failure during priming is retained as `BACKEND_ERROR`; it cannot be represented as a successful cache HIT.
- Each run creates a unique cache key containing experiment, principal, and resource identifiers. Concurrent independent runs should therefore not overwrite each other's cache entries.
- Cache metadata SHA-256 is a body/digest consistency check, not authentication. Redis is currently inside the trusted test boundary.
- The exact finding oracle remains unchanged:
  `origin HTTP 403 AND normal cache path HIT AND cached response contains the expected resource canary`.
- V1 APIs, legacy evidence stages, report compatibility, and existing constructors must remain compatible unless an explicitly additive interface is approved.

## 3. Scope

### Workstream A — Real service-boundary integration

Add a deterministic integration profile that exercises:
1. A real Redis 7 service (the existing CI Redis service may be reused).
2. A protected origin reached over an actual loopback HTTP connection, rather than only in-process ASGI transport.
3. The same cache manager and experiment orchestration contracts used by the default tests.

The loopback origin must bind to an ephemeral local port, have explicit startup/readiness/shutdown handling, and be restricted to loopback. Tests must not contact arbitrary external hosts. Keep the in-process ASGI adapter as the fast default.

If an HTTP network adapter is added, it must accept an explicit base URL, enforce HTTP(S), apply bounded connect/read timeouts, close its client deterministically within the per-run lifecycle, and avoid logging credentials, response bodies, or full cache keys. No endpoint discovery, URL crawling, or arbitrary target scanning.

### Workstream B — Redis failure and recovery

Extend fault tests to cover transient failures at the boundaries that matter:
- Initial cache read unavailable, followed by recovery.
- Cache prime write failure, followed by successful later run.
- Cache replay read failure after a successful prime.
- Redis becoming available again without requiring a database flush or deleting unrelated keys.

Define expected semantics before implementation:
- A failed operation is recorded as `BACKEND_ERROR`, never silently normalized into a cache HIT.
- A failed prime cannot confirm a finding.
- A failed replay read cannot confirm a finding, even if an entry may still exist.
- A subsequent independent run after recovery can complete normally and confirm the controlled replay if all three oracle conditions are observed.
- Tests use unique prefixes/keys and never call `FLUSHDB` or `FLUSHALL`.

### Workstream C — Concurrent experiment isolation and race coverage

Exercise simultaneous runs using a shared real Redis service and independent experiment contexts:
- Same principal/resource across separate runs.
- Different principals against the same resource.
- Different resources for the same principal.
- Bounded bursts (small fixed concurrency, not a performance benchmark).

Acceptance criteria:
- Experiment IDs and cache keys are unique per run.
- One run cannot consume another run's cached response or metadata.
- Every result's metadata identity matches its own principal/resource.
- No run is confirmed from another run's cache entry.
- Redis state outside the test prefix is not modified.

Also test cache-manager-level concurrent store/observe behavior for one deliberately shared test key. Define only the guarantees supported by Redis atomic `SET` semantics; do not claim a transaction across separate cache and policy operations. Do not claim the experiment is linearizable or race-free for arbitrary shared mutable policy instances. If shared policy mutation causes nondeterministic outcomes, document the limitation and isolate test policy instances rather than hiding the race.

### Workstream D — End-to-end V2 tenant-aware authorization and cache isolation

Integrate the existing V2 `PolicyEngine` into a separately selectable V2 experiment path while preserving the current V1-compatible default path.

Design requirements:
- Identity and tenant identity must come from the trusted `IdentityRegistry`, not from a caller-controlled tenant query parameter.
- Resource ownership/tenant association must come from `ResourceRegistry`.
- Authorization decisions must be made by `PolicyEngine`; explicit deny and tenant-boundary precedence must remain intact.
- Grant/revoke transitions must use the V2 `PermissionStore` interfaces.
- Cache identity must include the trusted tenant context in addition to experiment/principal/resource identity, and metadata must record that tenant context.
- A tenant administrator must not cross a tenant boundary.
- A principal from tenant A must not receive tenant B's resource through either origin or cache path.
- Unknown, suspended/removed identities, inactive/unknown tenants, unknown resources, and explicit denials must fail closed.
- Tests must demonstrate isolation end-to-end through origin, Redis, evidence persistence, and reports.

Before implementation, choose and document the additive integration seam (for example, a policy adapter/controller abstraction plus a separately selectable V2 configuration). Do not silently change the meaning of existing `policy=`, `origin_app=`, or `run(principal_id, resource_id)` V1 call patterns. Do not trust a tenant ID supplied by the request as authorization context.

The tenant fixture must use unambiguous resource ownership. Since the current resource registry indexes resource IDs globally, either use globally unique tenant-qualified resource IDs in the controlled fixture or propose a separately reviewed registry key model. Do not quietly allow duplicate resource IDs across tenants.

## 4. Evidence and reporting

- Preserve the exact three-condition oracle.
- Add only the minimum safe tenant and failure-state evidence required to explain the experiment.
- Do not persist raw response bodies, credentials, authorization secrets, arbitrary headers, or full cache keys.
- Ensure tenant identifiers are handled as test identity data and are not confused with authenticated claims.
- Reports must distinguish a negative result from an indeterminate backend failure.
- If schema changes are necessary, they must be additive, transactional, idempotent, and tested against legacy databases. Prefer using the existing analysis JSON schema versioning only when compatible; otherwise increment the analysis schema explicitly and document it.

## 5. Explicit non-goals

- No arbitrary internet targets, crawling, endpoint discovery, or scanning.
- No CDN, browser cache, or distributed invalidation product integrations.
- No production authentication, identity federation, secrets management, or enterprise tenant directory.
- No benchmark claims, high-throughput load testing, or broad performance optimization.
- No MAC/signature implementation for cache metadata in this phase; the Redis trust boundary remains explicit.
- No AI/ML.
- No V3 planning or implementation.
- No merge, PR readiness transition, or changes to `main`.

## 6. Task sequence and acceptance gates

1. **Service-boundary adapter and integration harness:** loopback origin + real Redis test profile; deterministic lifecycle and cleanup.
2. **Redis recovery semantics:** transient read/write/replay failures and successful subsequent recovery, end-to-end.
3. **Concurrency isolation:** bounded concurrent runs and deliberately shared cache-key behavior with precise guarantees.
4. **V2 policy integration design + implementation:** additive policy seam, trusted identity/tenant resolution, end-to-end tenant isolation.
5. **Evidence/reporting and docs:** additive safe evidence, migration only if required, limitations and reproducible integration instructions.
6. **Full validation and review:** local WSL full suite, GitHub Actions, repeated integration run, regression and compatibility review.

Each task is reviewed and validated before the next. If a design decision changes the existing public API or the security trust boundary, stop and revise this spec before coding.

## 7. Completion criteria

Phase 4 is complete only when:
- The local service-boundary profile is deterministic and cleans up resources.
- Failure/recovery tests prove backend errors are never misreported as HITs or confirmed findings.
- Concurrent runs preserve experiment/principal/resource/tenant isolation under the stated test conditions.
- The V2 policy path demonstrates tenant isolation end-to-end through origin, cache, SQLite, and reports.
- Existing V1 behavior and legacy report/storage compatibility remain green.
- User-reported local WSL validation and GitHub Actions results are recorded separately.
- PR #1 remains Draft and `main` remains untouched.
