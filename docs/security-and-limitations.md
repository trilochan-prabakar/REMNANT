# REMNANT V2 threat model, security scope, and limitations

## Threat model

### Protected asset

A response containing data that should be available only while a principal has an active authorization grant.

### Security objective

Determine whether the normal cache path can return a previously authorized response after a direct, cache-bypassed request to the origin denies the same principal. A finding requires the origin denial, a cache HIT, and the expected resource canary in that cached response.

### Adversary and failure assumptions

The test models a caller whose access has been revoked, or whose role/tenant relationship has changed, but who can still make an ordinary application request. The failure under study is stale authorization at a cache boundary: the origin has changed its decision while a cached representation may remain available. The harness also checks identity/resource/tenant metadata mismatches in its own cache adapter.

### Trust boundaries

- **Origin:** authoritative for the current authorization decision in this controlled experiment.
- **Cache:** stores a previously authorized response and may outlive a grant until TTL expiry; it is not an authorization authority.
- **Harness:** independently observes the direct origin response and normal cache-path result, then evaluates the strict oracle.
- **Redis infrastructure:** trusted for the test. The body digest and response are stored together and are not authenticated against a malicious Redis writer.

### Cache-key dimensions and deliberate coverage

REMNANT's own cache key includes experiment ID, principal ID, and resource ID. The separately selectable V2 tenant-aware path adds the tenant resolved from the trusted in-memory identity registry. Replay metadata is checked against those same request-context dimensions.

These are isolation dimensions in REMNANT's harness, not an audit of an external application's cache key. V2 does not systematically inject omitted-principal, omitted-resource, or omitted-tenant key bugs into Nginx, Varnish, a CDN, or a framework cache. Nor does it test every HTTP Vary, cookie, authorization-header, invalidation, or shared-cache directive interaction.

### Weakness association

The scenario is conceptually related to [MITRE CWE-524](https://cwe.mitre.org/data/definitions/524.html), whose current description concerns a cache containing sensitive information that can be read outside its intended control sphere. This is a broad association, not an automatic or definitive CWE mapping for every cache-replay result. [CWE-613](https://cwe.mitre.org/data/definitions/613.html) is deprecated in the current MITRE catalogue and is not used as a V2 mapping. A REMNANT finding is an experimental observation, not a vulnerability classification for an external product.



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
- The cache keys are scoped by a unique experiment ID, principal ID, and resource ID; the V2 policy-engine path also includes the tenant resolved from the identity registry. This prevents separate runs and tested identity/resource/tenant contexts from sharing a response key.
- Cached responses have a finite TTL. The experiment does not invalidate the entry on revocation; it remains subject to normal expiry.
- Redis is expected at the configured URL (the integration setup uses `redis://localhost:6379/0`). Unit tests use controlled fakes implementing the small Redis client interface.
- V2 cache observations distinguish HIT, MISS, EXPIRED, UNKNOWN, BACKEND_ERROR, and INVALID_METADATA. These states describe the experiment's adapter observations; they do not model every cache platform's semantics.

These assumptions make the replay sequence reproducible; they do not reproduce every target application's request routing, authorization model, cache key, TTL, invalidation behavior, or deployment topology.

## Cache metadata integrity and trust boundary

The `body_sha256` field is an integrity check for consistency between the response bytes and the digest value currently stored in the metadata. It can detect accidental corruption or a response-body change when the metadata remains trustworthy. It is **not an authenticity mechanism**: the digest and response are stored together in the same Redis payload, so an actor able to modify that payload can replace both the body and its digest, and may also alter the metadata fields. The current implementation does not use a keyed MAC, digital signature, or independently protected metadata store.

Accordingly, REMNANT assumes Redis and the cache payload are within the experiment's trusted test boundary. A valid digest means only that the body matches the accompanying digest; it does not prove who created the entry or that its identity fields are genuine. Reports and documentation must not describe the current SHA-256 field as tamper-proof or cryptographically authenticated metadata. A future authenticated-metadata design would need explicit key generation, storage, rotation, and verification rules.

## Why principal/resource scoped cache keys matter

A cache key that omits the principal or resource can cause responses to be shared across identities or resources. That is a separate class of isolation error and can make an experiment ambiguous. REMNANT includes experiment, principal, and resource identifiers in the key so the result is attributable to the exact run and pair being tested. The key design is part of this harness; it is not a claim about how an external application constructs its own cache keys.

## Why origin authorization is independent

The origin is called directly after revocation, bypassing the Redis lookup. It checks the current `AuthorizationPolicy` for that request. That independent response provides the origin side of the comparison; without it, a stale cached response would not establish that the origin now denies the caller.

## Authorization model boundaries

The V2 `PolicyEngine` is a standalone authorization foundation backed by identity, tenant, resource, and permission registries. It provides default-deny decisions, tenant-boundary checks, explicit-deny precedence, ownership rules, and tenant-scoped administrator permissions.

The default `CacheReplayExperiment` path still uses the V1-compatible `AuthorizationPolicy`. A separately selectable V2 path composes `PolicyEngineAdapter` with `create_v2_protected_origin_app`. In that path, tenant context is resolved from the trusted `IdentityRegistry`, resource ownership from `ResourceRegistry`, and grants/revocations from `PermissionStore`; no caller-supplied tenant parameter is used as authorization context. Cache keys and metadata include the registry-derived tenant and replay checks require principal, resource, and tenant identity to match. Tests exercise same-tenant replay, cross-tenant denial, tenant-admin boundaries, explicit-deny precedence, inactive tenants, and suspended/removed/unknown identities. This remains an in-memory controlled fixture, not production authentication or identity lifecycle integration.

## What REMNANT does not test

- It does not scan arbitrary websites, APIs, caches, or source code.
- It does not detect every cache-related authorization vulnerability or prove that an untested system is secure.
- It does not test real browser or proxy caches, CDN behavior, HTTP cache directives, distributed invalidation, or production service boundaries. Bounded concurrency tests exercise independent experiment runs and atomic replacement of a serialized Redis value, not distributed linearizability.
- It does not test authentication, identity federation, real user/tenant lifecycle, roles submitted by clients, or persistent policy changes.
- It does not test policies beyond the small grant/revoke model, nor enumerate arbitrary resource identifiers.
- It does not automatically discover endpoints or cache keys. The experiment targets the fixed protected resources and cache flow implemented in REMNANT.
- It does not persist authorization policy state. SQLite stores completed experiment results, the six compatibility evidence stages, finding conditions, and an additive V2 analysis record when supplied.
- Differential response analysis compares selected dimensions and records diagnostic evidence. It is not proof of exploitability and never overrides the exact three-condition finding oracle.
- V2 analysis persistence is designed to be body-free: it records statuses, comparison values, metadata summaries and SHA-256 digests, not raw response bodies or full cache keys.

## Identity, resource, and canary limitations

The current origin accepts `principal_id` as a query parameter and constructs a `USER` principal; this is test input, not an authentication mechanism. The in-memory policy and fixed resource data are demonstration fixtures. They must not be treated as a production authorization service or as a source of real confidential data. The canaries are stable identifiers used to determine whether the selected resource's response body was replayed.

## Cache backend failure semantics

A Redis write failure during cache priming is recorded as a `BACKEND_ERROR` observation in the cache-prime evidence. The experiment does not treat the origin response held in process memory as a successful cache write, and that response is never passed to the replay finding oracle as a cache `HIT`. The experiment may continue to the direct post-revocation origin check and replay observation so the result can preserve the backend failure alongside the independent origin outcome. A failed write therefore cannot produce a confirmed cache-replay finding by itself.

The synchronous experiment API currently treats origin transport failures differently: they propagate as exceptions and do not produce a completed experiment result. This distinction is intentional; a cache backend failure is an observation within the tested cache path, while an unavailable origin prevents the required independent authorization observations.

## Interpreting outcomes

- `CONFIRMED` means the three oracle conditions were observed during this run.
- `NOT_FOUND` means those three conditions were not all observed. It does not establish the absence of another vulnerability or a flaw outside the tested path.
- A report can label an experiment incomplete or failed when persisted stage evidence is missing or indicates an error. Reports reflect stored evidence and do not recreate the experiment.
- V2 JSON reports use schema `2.0` when analysis is present; legacy records remain reportable with schema `1.0` and an explicit missing-analysis state.

Use the framework only against systems and data you are authorized to test. The included demonstration is self-contained and targets the included sample origin.


## Concurrency boundaries

The concurrency suite uses independent experiment and policy instances with a shared Redis client. It verifies unique run keys and principal/resource/tenant metadata isolation. For a deliberately shared key, Redis SET atomically replaces the one serialized response-plus-metadata value; concurrent writers may overwrite one another, and REMNANT does not claim which writer wins, a multi-command transaction, or end-to-end linearizability. Sharing one mutable policy object between concurrent experiments is outside the supported guarantee.


## Real-component validation boundary

V2 includes integration tests against a real Redis 7 service and a loopback-only HTTP origin adapter. The Docker Compose lab also exercises a real Nginx `proxy_cache` container against a stateful FastAPI origin: it primes a cached 200, revokes access at the origin, observes a direct 403, then verifies that Nginx returns the cached response with `X-Cache-Status: HIT` and the expected canary. This is one deliberately vulnerable configuration, not broad coverage of Nginx, Varnish, CDN, `Vary`, authorization-header, or production invalidation behavior.
