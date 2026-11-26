# Changelog

Notable changes to REMNANT are documented here.

## 3.0.0 — REMNANT V3

V3 extends the controlled authorization-replay experiment into a repeatable HTTP cache testing harness. It is additive to the V1/V2 implementation.

### Added

- HTTP cache directive, freshness, Vary, Set-Cookie, and observed cache-state analysis.
- Validated YAML scenarios and a bounded asynchronous origin/proxy request runner.
- Separate four-condition cross-identity isolation oracle.
- Explicit fixture lifecycle controls for grant, revoke, resource update, and proxy PURGE.
- V3-specific transactional SQLite evidence and run-to-run comparison.
- Optional persistence of identity-isolation decisions linked to a V3 run.
- Real Varnish 7.6 integration for stale authorization replay, cross-identity cache-key collision, resource update staleness, and PURGE invalidation.
- Read-only scenario batches support bounded concurrency; state-changing lifecycle scenarios are rejected by batch execution to prevent shared-fixture interleaving.
- GitHub Actions validation for the full regression suite, V3 compilation, and real Varnish integration on pull requests and pushes to `main`.

### Compatibility and scope

- V1 and V2 source modules, result/report contracts, and evidence schemas remain unchanged.
- V2 remains frozen.
- V3 protocol diagnostics are not vulnerability findings by themselves; strict finding oracles remain separate.
- REMNANT remains a controlled testing harness, not an unrestricted internet scanner.

### Validation

- The V3 pull request completed all five checks successfully before merge.
- The post-merge `main` workflow completed successfully.
- See [V3 scope](docs/v3-scope.md) and [V3 architecture](docs/v3-architecture.md) for validation boundaries and limitations.

## 2.0.0 — REMNANT V2

REMNANT V2 expands the original controlled cache-replay experiment while preserving its V1-compatible finding oracle and legacy result/report fields.

### Added

- Explicit cache observation states: HIT, MISS, EXPIRED, UNKNOWN, BACKEND_ERROR, and INVALID_METADATA.
- Schema-versioned cache metadata with principal, resource, optional tenant, response status, timestamps, and a SHA-256 response-body consistency digest.
- Differential response analysis for HTTP status, selected headers, body digest, and expected canary.
- Origin adapter protocol with in-process ASGI and loopback-only HTTP implementations.
- Transactional, versioned SQLite persistence for body-free analysis evidence alongside the six legacy evidence stages.
- JSON report schema 2.0 and standalone HTML analysis reporting, while retaining legacy schema 1.0 report support.
- A separately selectable tenant-aware PolicyEngine experiment path with registry-derived tenant context, tenant-scoped authorization, and tenant-aware cache metadata.
- Integration coverage for real Redis and loopback HTTP, transient Redis failure and recovery, and bounded concurrent experiment isolation.

### Compatibility

- The original V1-compatible AuthorizationPolicy path remains the default.
- The exact three-condition finding oracle remains unchanged: origin HTTP 403, cache HIT, and expected resource canary match.
- Differential analysis is diagnostic evidence only and cannot independently confirm a finding.
- Legacy result fields, six-stage evidence, and schema 1.0 report support are retained.

### Security and scope notes

- The SHA-256 digest is a consistency check, not an authenticity guarantee; response and digest are stored together in Redis.
- Tenant-aware authorization uses in-memory registries and is a controlled fixture, not a production identity provider.
- REMNANT is a controlled testing harness, not an arbitrary website scanner or production security product.
- See [Security and limitations](docs/security-and-limitations.md) for assumptions, trust boundaries, and interpretation guidance.

### Validation record

- GitHub Actions: 215 tests passed on the V2 development branch (Python 3.12 / Redis 7).
- Local WSL: 215 tests passed, as reported by the project maintainer.
