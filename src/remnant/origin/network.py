"""Loopback-only HTTP adapter for realistic local origin integration tests."""

import ipaddress
import math
from urllib.parse import quote, urlsplit

import httpx

from remnant.origin.fastapi import OriginTransportError
from remnant.origin.protocols import OriginResponse


class LoopbackHTTPOriginAdapter:
    """Call a protected origin over HTTP while restricting targets to loopback.

    A new HTTPX client is opened and closed for each request. This keeps the
    adapter compatible with the experiment runner's per-run event-loop
    lifecycle and prevents client resources leaking across runs.
    """

    def __init__(self, base_url: str, *, timeout_seconds: float = 2.0) -> None:
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a positive number")
        try:
            parsed = urlsplit(base_url)
            hostname = parsed.hostname
            port = parsed.port
        except (TypeError, ValueError) as exc:
            raise ValueError("base_url must be a valid loopback HTTP(S) URL") from exc

        if (
            parsed.scheme not in {"http", "https"}
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("base_url must be a plain loopback HTTP(S) origin URL")

        is_loopback_name = hostname.lower() == "localhost"
        try:
            is_loopback_ip = ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            is_loopback_ip = False
        if not (is_loopback_name or is_loopback_ip):
            raise ValueError("origin adapter only permits loopback destinations")
        if port is None:
            raise ValueError("base_url must include an explicit port")

        self._base_url = f"{parsed.scheme}://{parsed.netloc}"
        self._timeout_seconds = float(timeout_seconds)

    async def get_protected(
        self, resource_id: str, *, principal_id: str
    ) -> OriginResponse:
        if not isinstance(resource_id, str) or not resource_id.strip():
            raise ValueError("resource_id must be a non-empty string")
        if not isinstance(principal_id, str) or not principal_id.strip():
            raise ValueError("principal_id must be a non-empty string")

        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout_seconds),
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = await client.get(
                    f"/protected/{quote(resource_id, safe='')}",
                    params={"principal_id": principal_id},
                )
        except httpx.HTTPError as exc:
            raise OriginTransportError("loopback origin request failed") from exc

        return OriginResponse(
            status_code=response.status_code,
            headers=tuple(response.headers.multi_items()),
            body=response.content,
        )
