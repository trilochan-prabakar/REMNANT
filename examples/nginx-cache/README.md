# Nginx proxy_cache integration target

This optional Docker lab exercises a real Nginx `proxy_cache` configuration against a small stateful FastAPI origin. It is a deliberately vulnerable test fixture, not a production configuration.

## What it demonstrates

1. Grant principal `alice` access to a protected report.
2. Request the report through Nginx; the origin returns HTTP 200 and Nginx stores it (`MISS`).
3. Revoke Alice directly at the origin.
4. Request the same URL directly from the origin; it returns HTTP 403.
5. Request the same URL through Nginx; the cached response is returned (`HIT`) with the original resource canary.

The Nginx cache key includes the full request URI, including `principal_id`. This fixture is therefore **not** demonstrating cross-principal cache-key collision. It demonstrates the distinct stale-authorization failure where the same principal's cached representation survives an origin-side revocation because the proxy serves a fresh cache entry without re-authorizing at the origin.

## Run

From the repository root:

```bash
docker compose run --build --rm nginx-check
```

The check exits non-zero unless it observes the expected MISS → origin 403 → HIT + canary sequence.

The general demo is separate:

```bash
docker compose run --build --rm demo
```

## Scope

This is one reproducible Nginx proxy-cache configuration test. It does not imply coverage of every Nginx directive, Vary behavior, authorization-header handling, cache-control policy, reverse-proxy version, CDN, or production topology. The fixture intentionally contains an unsafe policy and must not be copied into production.
