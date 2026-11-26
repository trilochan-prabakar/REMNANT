"""End-to-end Varnish stale-authorization and identity-key collision check."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

VARNISH = os.environ.get("REMNANT_VARNISH_URL", "http://127.0.0.1:8088")
ORIGIN = os.environ.get("REMNANT_VARNISH_ORIGIN_URL", "http://127.0.0.1:8000")


def request(url: str, *, method: str = "GET", payload: dict | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def control(action: str, principal: str) -> None:
    status, _, body = request(
        f"{ORIGIN}/control/{action}", method="POST", payload={"principal": principal}
    )
    assert status == 200, (status, body)


def main() -> None:
    # Fresh fixture starts with Alice granted and Bob denied.
    control("grant", "alice")
    control("revoke", "bob")

    alice_url = f"{VARNISH}/protected/report?principal=alice"
    bob_url = f"{VARNISH}/protected/report?principal=bob"

    status, headers, body = request(alice_url)
    assert status == 200, (status, body)
    assert json.loads(body)["canary"] == "alice-private-report"

    # Same identity: the origin now denies, but Varnish replays its cached 200.
    control("revoke", "alice")
    origin_status, _, _ = request(f"{ORIGIN}/protected/report?principal=alice")
    assert origin_status == 403, origin_status
    replay_status, replay_headers, replay_body = request(alice_url)
    assert replay_status == 200, (replay_status, replay_body)
    assert replay_headers.get("X-Cache-Status") == "HIT", replay_headers
    assert json.loads(replay_body)["canary"] == "alice-private-report"

    # Cross identity: Bob is denied at origin but receives Alice's cached body
    # because this intentionally vulnerable VCL omits principal from its key.
    bob_origin_status, _, _ = request(f"{ORIGIN}/protected/report?principal=bob")
    bob_proxy_status, bob_headers, bob_body = request(bob_url)
    assert bob_origin_status == 403, bob_origin_status
    assert bob_proxy_status == 200, (bob_proxy_status, bob_body)
    assert bob_headers.get("X-Cache-Status") == "HIT", bob_headers
    assert json.loads(bob_body)["canary"] == "alice-private-report"

    # Exercise Varnish's explicit PURGE lifecycle operation. The cached object
    # is removed; Bob's next request reaches the origin and is denied.
    purge_status, _, _ = request(
        f"{VARNISH}/protected/report?principal=bob", method="PURGE"
    )
    assert purge_status == 200, purge_status
    after_purge_status, _, _ = request(bob_url)
    assert after_purge_status == 403, after_purge_status

    print("Varnish fixture passed:")
    print("- stale authorization replay: origin 403 / Varnish HIT / expected canary")
    print("- cross-identity cache-key collision: Bob received Alice's cached representation")
    print("- explicit PURGE invalidation: subsequent request reached origin and returned 403")


if __name__ == "__main__":
    main()
