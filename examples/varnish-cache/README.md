# REMNANT V3 — Varnish integration fixture

This isolated fixture runs a local origin behind Varnish 7.6. It intentionally
contains two cache authorization failures so REMNANT can test both stale replay
and cross-identity isolation using a real reverse proxy.

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

The fixture is intentionally vulnerable, not a secure production configuration.
It validates REMNANT's ability to observe these two controlled conditions. The
VCL must not be deployed as an actual reverse-proxy configuration.

## Reset

The compose stack uses an ephemeral Varnish cache process. Recreate the stack
between independent runs to ensure a clean cache.
