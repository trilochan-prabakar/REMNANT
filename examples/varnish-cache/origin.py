"""Small stateful origin used only by the isolated Varnish integration fixture."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

GRANTS: set[str] = {"alice"}
CANARIES = {"alice": "alice-private-report", "bob": "bob-private-report"}
RESOURCE_CONTENT = "resource-v1"


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict, *, cache_control: str = "no-store") -> None:
        body = json.dumps(payload, sort_keys=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/health":
            self._send(200, {"status": "ok"})
            return
        if parsed.path != "/protected/report":
            self._send(404, {"error": "not_found"})
            return
        principal = parse_qs(parsed.query).get("principal", [""])[0]
        if principal not in GRANTS or principal not in CANARIES:
            self._send(403, {"error": "forbidden"})
            return
        self._send(
            200,
            {"principal": principal, "canary": CANARIES[principal], "content": RESOURCE_CONTENT},
            cache_control="public, max-age=120",
        )

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path not in {
            "/__remnant__/control/grant", "/__remnant__/control/revoke",
            "/__remnant__/control/update",
        }:
            self._send(404, {"error": "not_found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length > 4096:
            self._send(413, {"error": "payload_too_large"})
            return
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send(400, {"error": "invalid_json"})
            return
        if not isinstance(payload, dict):
            self._send(400, {"error": "invalid_payload"})
            return
        if parsed.path.endswith("/update"):
            global RESOURCE_CONTENT
            content = payload.get("content")
            if content not in {"resource-v1", "resource-v2"}:
                self._send(400, {"error": "invalid_resource_content"})
                return
            RESOURCE_CONTENT = content
            self._send(200, {"content": RESOURCE_CONTENT})
            return
        principal = payload.get("principal")
        if principal not in CANARIES:
            self._send(400, {"error": "unknown_principal"})
            return
        if parsed.path.endswith("/grant"):
            GRANTS.add(principal)
        else:
            GRANTS.discard(principal)
        self._send(200, {"principal": principal, "granted": principal in GRANTS})

    def log_message(self, _format: str, *_args) -> None:
        pass


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 8000), Handler)
    server.serve_forever()
