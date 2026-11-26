import asyncio

import httpx

from remnant.v3.runner import RunStatus, ScenarioRunner
from remnant.v3.scenarios import ScenarioLoader


def _scenario():
    return ScenarioLoader().loads("""
scenario:
  id: bounded
  name: Bounded transport
steps:
  - name: response
    via: origin
    path: /resource
""")


def test_response_body_capture_is_bounded():
    async def exercise():
        origin = httpx.AsyncClient(
            base_url="http://origin.test",
            transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 500)),
        )
        proxy = httpx.AsyncClient(base_url="http://proxy.test")
        try:
            result = await ScenarioRunner(
                origin_client=origin, proxy_client=proxy, max_response_bytes=32
            ).run(_scenario())
        finally:
            await origin.aclose()
            await proxy.aclose()
        assert result.status is RunStatus.PASSED
        assert result.traces[0].body_bytes == 32
        assert result.traces[0].body_truncated is True
        assert len(result.traces[0].body_sha256) == 64

    asyncio.run(exercise())


def test_transport_timeout_is_recorded_as_error_without_leaking_request_data():
    async def exercise():
        def timeout(request):
            raise httpx.ReadTimeout("sensitive query=do-not-store", request=request)

        origin = httpx.AsyncClient(
            base_url="http://origin.test",
            transport=httpx.MockTransport(timeout),
        )
        proxy = httpx.AsyncClient(base_url="http://proxy.test")
        scenario = ScenarioLoader().loads("""
scenario:
  id: timeout
  name: Timeout
steps:
  - name: timeout
    via: origin
    path: /resource?token=private-value
""")
        try:
            result = await ScenarioRunner(
                origin_client=origin, proxy_client=proxy
            ).run(scenario)
        finally:
            await origin.aclose()
            await proxy.aclose()
        assert result.status is RunStatus.ERROR
        assert result.traces[0].error.startswith("ReadTimeout:")
        assert "do-not-store" not in result.traces[0].error
        assert "private-value" not in result.traces[0].path
        assert "[REDACTED]" in result.traces[0].path

    asyncio.run(exercise())
