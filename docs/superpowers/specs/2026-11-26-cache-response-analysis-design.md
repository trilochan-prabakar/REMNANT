# REMNANT V2 Phase 2 — Cache and Response Analysis Design

**Status:** Draft implementation specification  
**Branch:** `remnant-v2-development`  
**Depends on:** Phase 1 authorization and scenario foundation

## Purpose

Make cache observations explicit and comparable with an independently evaluated protected origin. Phase 2 improves the reliability and inspectability of the cache/origin analysis without introducing time-based revocation experiments or fault injection.

## Goals

1. Represent cache outcomes distinctly: `HIT`, `MISS`, `EXPIRED`, `UNKNOWN`, `BACKEND_ERROR`, and `INVALID_METADATA`.
2. Keep cache mechanics independent from authorization policy.
3. Define a small cache adapter contract and retain Redis as the first implementation.
4. Define an origin adapter contract and retain the existing FastAPI protected origin as the first implementation.
5. Record enough cache metadata to identify the principal, tenant (when known), resource, response status, creation/expiry information, and a content digest.
6. Compare an origin response and a cached response using explicit, deterministic comparison results.
7. Preserve and strengthen the V1 three-condition finding oracle: origin denies AND cache returns a hit AND the expected canary matches.
8. Add negative controls so partial matches cannot be reported as confirmed findings.
9. Preserve V1 public imports and behaviour wherever possible.

## Non-goals

- Cache invalidation or revocation propagation strategies.
- Revocation latency, TTL-vs-invalidation benchmarking, or monotonic-time experiments.
- Concurrent request races, distributed replicas, network partitions, delayed/lost invalidations, or restart recovery.
- CLI redesign, dashboards, HTML reporting, or evidence-store redesign.
- AI/ML.

These belong to later phases and must not be pulled into Phase 2.

## Design principles

- **Independent authorization:** the origin evaluates authorization independently. A cache hit must never be treated as proof that the request is authorized.
- **No policy inside cache adapters:** adapters store and retrieve response snapshots and metadata; they do not grant, revoke, or evaluate permissions.
- **Explicit uncertainty:** unavailable or malformed cache state must not be silently converted into a miss or a security finding.
- **Deterministic analysis:** comparison and finding logic must be pure functions over explicit inputs.
- **Safe Redis use:** integration tests use unique key prefixes and never flush the Redis database.
- **Compatibility:** retain `RedisCacheManager`, `CacheStatus.HIT`, `CacheStatus.MISS`, `CachedHTTPResponse`, and existing V1 experiment interfaces unless an additive compatibility layer is provided.

## Proposed components

### Cache model and adapter

Introduce a cache observation model with:
- outcome state;
- optional cached response;
- optional metadata;
- optional diagnostic category/message suitable for reports (never raw credentials or secrets).

Define a protocol for `get`, `put`, and (if needed for tests/inspection) `delete`. The protocol must not include authorization-policy operations. Redis is the first adapter.

Metadata should include a schema version, cache key identity dimensions (principal/resource and optional tenant), creation timestamp, expiry/TTL information where available, response status, and SHA-256 digest of the stored body. Validate metadata on read. Unknown schema versions and malformed metadata produce `INVALID_METADATA`, not `MISS`.

### Origin adapter

Define a small protocol for requesting a protected resource and returning a normalized response snapshot. Wrap the existing FastAPI ASGI origin so tests can use deterministic in-process requests. The adapter must not share cache state and must not bypass the origin's authorization check.

### Differential response analysis

Add a pure analyzer that compares normalized origin and cache observations. It should report individual dimensions (status, selected security-relevant headers, body digest, canary presence/match) and a structured overall comparison. It must distinguish a legitimate content difference from an unavailable observation. Do not log full protected response bodies by default.

### Finding validation

Keep the existing positive oracle exact:
1. Direct origin request after revocation is denied (HTTP 403).
2. Normal cache path returns `HIT`.
3. Cached body contains the expected resource canary.

Only the conjunction confirms the existing replay finding. Add explicit negative-control tests for origin allow, cache miss, expired/unknown/error/invalid cache state, missing canary, and mismatched canary. Differential comparison is supporting evidence; it must not weaken or silently replace the three-condition oracle.

## Testing requirements

- Pure unit tests for metadata serialization, schema validation, digest verification, cache-state mapping, and response comparison.
- Adapter contract tests shared by the fake and Redis adapters.
- Oracle tests for the positive case and each negative control independently.
- Isolation tests for different principals, tenants, and resources.
- Redis integration tests use unique prefixes, skip only when Redis is unavailable, and never issue `FLUSHDB` or `FLUSHALL`.
- Full regression suite must continue to pass, including V1 import/API compatibility.

## Acceptance criteria

- All six cache states are represented and tested.
- Malformed metadata and backend failures remain distinguishable from a cache miss.
- Redis remains a storage-only adapter.
- Origin authorization remains independent of cache lookup.
- Differential results are structured and deterministic.
- The original three-condition oracle remains intact with negative controls.
- Existing tests pass without weakening or deleting V1 coverage.
- No Phase 3/4/5 features are introduced in this phase.
