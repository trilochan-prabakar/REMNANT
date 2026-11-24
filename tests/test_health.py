import asyncio

import httpx

from remnant.api.app import app


def test_health_endpoint():
    async def request_health():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get("/health")

    response = asyncio.run(request_health())

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "project": "REMNANT",
        "version": "0.1.0",
    }
