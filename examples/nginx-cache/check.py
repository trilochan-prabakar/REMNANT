"""Exercise a real Nginx proxy_cache instance and verify stale replay."""

import time

import httpx

NGINX = "http://nginx-cache:8080"
ORIGIN = "http://nginx-origin:8000"
PRINCIPAL = "alice"
CANARY = "remnant-nginx-canary-private-report-8f31"


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
        assert primed.status_code == 200, primed.text
        assert primed.headers.get("x-cache-status") == "MISS"
        assert primed.json().get("canary") == CANARY

        client.post(f"{ORIGIN}/admin/revoke/{PRINCIPAL}").raise_for_status()
        direct = client.get(
            f"{ORIGIN}/protected/report", params={"principal_id": PRINCIPAL}
        )
        assert direct.status_code == 403, direct.text

        replay = client.get(
            f"{NGINX}/protected/report", params={"principal_id": PRINCIPAL}
        )
        assert replay.status_code == 200, replay.text
        assert replay.headers.get("x-cache-status") == "HIT"
        assert replay.json().get("canary") == CANARY

        print("Target: Nginx proxy_cache (real container)")
        print("Prime: HTTP 200 / X-Cache-Status: MISS")
        print("Direct origin after revoke: HTTP 403")
        print("Cached replay: HTTP 200 / X-Cache-Status: HIT")
        print("Expected canary: MATCH")
        print("Result: STALE AUTHORIZATION REPLAY REPRODUCED")


if __name__ == "__main__":
    main()
