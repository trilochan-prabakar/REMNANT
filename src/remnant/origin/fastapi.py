"""In-process HTTPX adapter for the independently-authorizing FastAPI origin."""

from urllib.parse import quote

import httpx
from fastapi import FastAPI

from remnant.origin.protocols import OriginResponse


class OriginTransportError(RuntimeError):
    """The origin could not be reached or its transport failed."""


class FastAPIOriginAdapter:
    """Issue real ASGI HTTP requests; never consults cache or policy directly."""

    def __init__(self, app: FastAPI, *, base_url: str = "http://remnant-origin") -> None:
        self._app = app
        self._base_url = base_url

    async def get_protected(
        self, resource_id: str, *, principal_id: str
    ) -> OriginResponse:
        if not isinstance(resource_id, str) or not resource_id.strip():
            raise ValueError("resource_id must be a non-empty string")
        if not isinstance(principal_id, str) or not principal_id.strip():
            raise ValueError("principal_id must be a non-empty string")
        transport = httpx.ASGITransport(app=self._app)
        try:
            async with httpx.AsyncClient(
                transport=transport, base_url=self._base_url
            ) as client:
                response = await client.get(
                    f"/protected/{quote(resource_id, safe='')}",
                    params={"principal_id": principal_id},
                )
        except httpx.HTTPError as exc:
            raise OriginTransportError("protected origin request failed") from exc
        return OriginResponse(
            status_code=response.status_code,
            headers=tuple(response.headers.multi_items()),
            body=response.content,
        )
