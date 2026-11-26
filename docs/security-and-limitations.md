# REMNANT V2 security scope and limitations

## What REMNANT tests

REMNANT V2 runs one controlled cache/origin consistency experiment. It grants a test principal access to a sample resource, obtains an authorized response, stores that response in Redis, revokes the grant, asks the origin directly, and then attempts the normal cache path. It checks whether the direct origin denies access while the cache still returns the same resource's expected canary.

The result is confirmed only when all three independent observations are true:

- The cache-bypassed origin returns HTTP 403.
- The normal cache path returns `HIT`.
- The cached response body contains the expected canary for the selected resource.

A cache `HIT` alone is not a finding: it says only that a response snapshot exists. It does not establish that the origin currently denies access or that the returned content is the protected resource under test.

## Controlled experiment assumptions

- The default origin is the REMNANT FastAPI app and runs in-process through HTTPX `ASGITransport` behind the `OriginAdapter` protocol. An adapter can be injected, but arbitrary deployed services are not automatically discovered or scanned.
- The policy and the experiment use the same `AuthorizationPolicy` instance. The standard setup creates an isolated policy; when a custom origin is supplied, the engine uses its app-state policy or validates an explicitly supplied policy against it.
- The policy is a mutable, in-memory set of principal/resource grants. Revocation changes subsequent origin decisions immediately in this process.
- The sample origin has two fixed resources with stable canaries. The test route creates every request principal as `Role.USER`.
- The cache keys are scoped by a unique experiment ID, principal ID, and resource ID. This prevents the experiment runner's runs and tested identity/resource pairs from sharing a response key.
- Cached responses have a finite TTL. The experiment does not invalidate the entry on revocation; it remains subject to normal expiry.
- Redis is expected at the configured URL (the integration setup uses `redis://localhost:6379/0`). Unit tests use controlled fakes implementing the small Redis client interface.
- V2 cache observations distinguish HIT, MISS, EXPIRED, UNKNOWN, BACKEND_ERROR, and INVALID_METADATA. These states describe the experiment's adapter observations; they do not model every cache platform's semantics.

These assumptions make the replay sequence reproducible; they do not reproduce every target application's request routing, authorization model, cache key, TTL, invalidation behavior, or deployment topology.

## Why principal/resource scoped cache keys matter

A cache key that omits the principal or resource can cause responses to be shared across identities or resources. That is a separate class of isolation error and can make an experiment ambiguous. REMNANT includes experiment, principal, and resource identifiers in the key so the result is attributable to the exact run and pair being tested. The key design is part of this harness; it is not a claim about how an external application constructs its own cache keys.

## Why origin authorization is independent

The origin is called directly after revocation, bypassing the Redis lookup. It checks the current `AuthorizationPolicy` for that request. That independent response provides the origin side of the comparison; without it, a stale cached response would not establish that the origin now denies the caller.

## What REMNANT does not test

- It does not scan arbitrary websites, APIs, caches, or source code.
- It does not detect every cache-related authorization vulnerability or prove that an untested system is secure.
- It does not test real browser or proxy caches, CDN behavior, HTTP cache directives, distributed invalidation, concurrency races, or production service boundaries.
- It does not test authentication, identity federation, real user/tenant lifecycle, roles submitted by clients, or persistent policy changes.
- It does not test policies beyond the small grant/revoke model, nor enumerate arbitrary resource identifiers.
- It does not automatically discover endpoints or cache keys. The experiment targets the fixed protected resources and cache flow implemented in REMNANT.
- It does not persist authorization policy state. SQLite stores completed experiment results, the six compatibility evidence stages, finding conditions, and an additive V2 analysis record when supplied.
- Differential response analysis compares selected dimensions and records diagnostic evidence. It is not proof of exploitability and never overrides the exact three-condition finding oracle.
- V2 analysis persistence is designed to be body-free: it records statuses, comparison values, metadata summaries and SHA-256 digests, not raw response bodies or full cache keys.

## Identity, resource, and canary limitations

The current origin accepts `principal_id` as a query parameter and constructs a `USER` principal; this is test input, not an authentication mechanism. The in-memory policy and fixed resource data are demonstration fixtures. They must not be treated as a production authorization service or as a source of real confidential data. The canaries are stable identifiers used to determine whether the selected resource's response body was replayed.

## Interpreting outcomes

- `CONFIRMED` means the three oracle conditions were observed during this run.
- `NOT_FOUND` means those three conditions were not all observed. It does not establish the absence of another vulnerability or a flaw outside the tested path.
- A report can label an experiment incomplete or failed when persisted stage evidence is missing or indicates an error. Reports reflect stored evidence and do not recreate the experiment.
- V2 JSON reports use schema `2.0` when analysis is present; legacy records remain reportable with schema `1.0` and an explicit missing-analysis state.

Use the framework only against systems and data you are authorized to test. The included demonstration is self-contained and targets the included sample origin.
