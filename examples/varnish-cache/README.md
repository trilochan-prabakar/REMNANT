# REMNANT V3 — Varnish integration fixture

This isolated fixture runs a local origin behind Varnish 7.6. It intentionally
contains two cache authorization failures plus a stale resource-version case,
allowing REMNANT to test replay, cross-identity isolation, and invalidation
against a real reverse proxy.

## Run

From the repository root:

```bash
docker compose -f examples/varnish-cache/docker-compose.yml up --build --abort-on-container-exit --exit-code-from check
docker compose -f examples/varnish-cache/docker-compose.yml down -v
```

Varnish is exposed on `127.0.0.1:8088`. The origin is reachable only on the
Compose network. No external target is contacted.

## What the check proves

1. Alice is granted access and requests a protected report through Varnish.
2. Alice's permission is revoked. The origin returns 403, but Varnish returns
   the cached 200 with a HIT marker and Alice's canary.
3. Bob is denied at the origin. Varnish nevertheless returns Alice's cached
   response because the deliberately vulnerable VCL hashes the URL path but
   omits the query string containing the principal.
4. A constrained V3 PURGE control removes the colliding cache object; Bob's next
   request reaches the origin and receives HTTP 403.
5. The origin resource changes from `resource-v1` to `resource-v2`; Varnish
   continues serving the old representation until PURGE, then fetches v2.

The fixture is intentionally vulnerable, not a secure production configuration.
The check is driven by REMNANT's YAML scenario loader and HTTP scenario runner,
including explicit grant/revoke controls and a Varnish PURGE operation. The VCL
must not be deployed as an actual reverse-proxy configuration.

## Reset

The compose stack uses an ephemeral Varnish cache process. Recreate the stack
between independent runs to ensure a clean cache.
