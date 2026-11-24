# Cache–Origin Replay Experiment Design

**Intent:** Prove that REMNANT detects an authorized response replayed from Redis after the independent origin denies the same principal.

**Goals:** Reuse `AuthorizationPolicy`, the protected FastAPI origin, and `RedisCacheManager`; scope cache entries to principal and resource; expose each oracle condition and a deterministic result; cover the full sequence and negative oracle cases.

**Non-goals and constraints:** No evidence database, reporting subsystem, dashboard, AI/ML, cache invalidation on revocation, or changes to the origin's independent authorization check. Preserve existing workspace state and use the configured Redis instance only with unique test keys.

**Approaches considered:** A new API endpoint would mix experiment orchestration into the origin app; adding cache responsibilities to `RedisCacheManager` would couple it to authorization. The chosen approach is a small engine-level runner that composes the existing origin ASGI app and cache manager, keeping the cache and origin independent.

**Builder calls:** Use a deterministic experiment ID and a result dataclass; build a principal/resource cache key; represent oracle conditions as explicit booleans and set finding only when all are true. Use fake Redis for deterministic unit tests and unique prefixes against localhost Redis for integration coverage.
