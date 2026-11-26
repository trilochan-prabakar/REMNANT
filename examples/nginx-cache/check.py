"""Exercise a real Nginx proxy_cache instance and verify stale replay."""

import time

import httpx

NGINX = "http://nginx-cache:8080"
ORIGIN = "http://nginx-origin:8000"
PRINCIPAL = "alice"
CANARY = "remnant-nginx-canary-private-report-8f31"


def require(condition: bool, message: str) -> None:
    """Enforce an integration assertion even when Python runs with -O."""
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    with httpx.Client(timeout=3.0) as client:
        for attempt in range(30):
            try:
                if client.get(f"{NGINX}/health").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError("Nginx did not become ready")

        client.post(f"{ORIGIN}/admin/grant/{PRINCIPAL}").raise_for_status()
        primed = client.get(
            f"{NGINX}/protected/report", params={"principal_id": PRINCIPAL}
        )
        require(primed.status_code == 200, f"cache prime returned {primed.status_code}: {primed.text}")
        require(
            primed.headers.get("x-cache-status") == "MISS",
            f"expected cache MISS, got {primed.headers.get('x-cache-status')!r}",
        )
        require(primed.json().get("canary") == CANARY, "primed response canary did not match")

        client.post(f"{ORIGIN}/admin/revoke/{PRINCIPAL}").raise_for_status()
        direct = client.get(
            f"{ORIGIN}/protected/report", params={"principal_id": PRINCIPAL}
        )
        require(direct.status_code == 403, f"origin after revocation returned {direct.status_code}")

        replay = client.get(
            f"{NGINX}/protected/report", params={"principal_id": PRINCIPAL}
        )
        require(replay.status_code == 200, f"cached replay returned {replay.status_code}: {replay.text}")
        require(
            replay.headers.get("x-cache-status") == "HIT",
            f"expected cache HIT, got {replay.headers.get('x-cache-status')!r}",
        )
        require(replay.json().get("canary") == CANARY, "replayed response canary did not match")

        print("Target: Nginx proxy_cache (real container)")
        print("Prime: HTTP 200 / X-Cache-Status: MISS")
        print("Direct origin after revoke: HTTP 403")
        print("Cached replay: HTTP 200 / X-Cache-Status: HIT")
        print("Expected canary: MATCH")
        print("Result: STALE AUTHORIZATION REPLAY REPRODUCED")


if __name__ == "__main__":
    main()
