# Changelog

Notable changes to REMNANT are documented here.

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
