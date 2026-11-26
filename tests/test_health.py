import asyncio

import httpx

from remnant.api.app import API_VERSION, app


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
        "version": API_VERSION,
    }
    assert app.version == API_VERSION == "2.0.0"
