# REMNANT V2 — Tenant-aware replay path

REMNANT keeps the original V1 CacheReplayExperiment construction and default authorization path. A separately selectable V2 path composes the existing PolicyEngine with the replay harness through PolicyEngineAdapter and create_v2_protected_origin_app.

## Trusted tenant resolution

The caller supplies only a principal identifier and resource identifier to the experiment. The adapter resolves the principal from IdentityRegistry; the tenant is taken from that registered identity. No caller-provided tenant query parameter or request field is accepted as authorization context.

PolicyEngine then resolves the resource from ResourceRegistry and enforces, in order: active identity, active tenant, known resource, tenant boundary, explicit denial, ownership, explicit grant, and tenant-admin role. Tenant administrator roles do not bypass tenant boundaries.

The adapter's grant and revoke methods operate on PermissionStore. The experiment's authorization-before-cache / revocation / replay sequence therefore exercises the V2 policy engine end-to-end for the selected principal and resource.

## Cache isolation and evidence

For the V2 path, the cache key includes the registry-derived tenant identifier. Cache metadata stores the same tenant identifier, and replay validation requires principal, resource, and tenant to match the trusted request context. V1 cache keys and metadata retain their prior tenant-null behavior.

The result exposes tenant_id; existing SQLite analysis serialization already carries the tenant field in the allow-listed cache metadata evidence. Reports continue to omit response bodies and full cache keys.

## Selecting the V2 path

Construct the identity, resource, permission, and tenant registries; create a PolicyEngine; wrap it in PolicyEngineAdapter; create the V2 origin app; then pass both the adapter and origin app to CacheReplayExperiment. The existing default constructor remains the V1-compatible path.

## Concurrency guarantees and limits

Each replay run receives a unique experiment ID and therefore a distinct cache key, including when principal and resource are identical across runs. Concurrency tests use separate experiment/policy instances with one thread-safe Redis client; they do not claim shared mutable policy objects are thread-safe.

Redis SET replaces the serialized response-plus-metadata value as one command, so readers do not observe a torn JSON payload from competing writers. Concurrent writers to the same key may overwrite one another; REMNANT does not claim a deterministic winner, multi-command transaction, or end-to-end linearizability.

## Scope

This remains a controlled harness using resources explicitly registered in its in-memory ResourceRegistry. The built-in sample resources retain their sample content; other registered resources receive deterministic fixture content and resource-specific canaries. The harness does not discover or enumerate resources from an external target. It is not a production identity provider, general-purpose web scanner, distributed authorization service, or proof of CDN-wide consistency.