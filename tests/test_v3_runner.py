import httpx
import pytest

from remnant.v3.runner import RunStatus, ScenarioRunner, run_to_json
from remnant.v3.scenarios import ScenarioLoader


@pytest.mark.asyncio
async def test_runner_executes_origin_and_proxy_and_redacts_secrets():
    def origin_handler(request):
        return httpx.Response(403, headers={"Cache-Control": "no-store"}, json={"error": "denied"})

    def proxy_handler(request):
        return httpx.Response(
            200,
            headers={
                "X-Cache": "HIT", "Cache-Control": "public, max-age=30",
                "Set-Cookie": "session=top-secret",
            },
            json={"canary": "private-report"},
        )

    origin = httpx.AsyncClient(base_url="http://origin.test", transport=httpx.MockTransport(origin_handler))
    proxy = httpx.AsyncClient(base_url="http://proxy.test", transport=httpx.MockTransport(proxy_handler))
    scenario = ScenarioLoader().loads("""
scenario:
  id: replay
  name: Replay test
steps:
  - name: direct
    via: origin
    path: /protected/report
    expect_status: 403
  - name: cached
    via: proxy
    path: /protected/report
    expect_status: 200
    expect_cache_state: hit
    expect_body_contains: private-report
""")
    try:
        result = await ScenarioRunner(origin_client=origin, proxy_client=proxy).run(scenario)
    finally:
        await origin.aclose()
        await proxy.aclose()
    assert result.status is RunStatus.PASSED
    serialized = run_to_json(result)
    assert "top-secret" not in serialized
    assert "session=" not in serialized
    assert result.traces[1].cache_analysis["cache_state"].value == "hit"


@pytest.mark.asyncio
async def test_runner_marks_assertion_failure():
    client = httpx.AsyncClient(base_url="http://origin.test", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, text="ok")
    ))
    proxy = httpx.AsyncClient(base_url="http://proxy.test", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, text="ok")
    ))
    scenario = ScenarioLoader().loads("""
scenario:
  id: fail
  name: Fail
steps:
  - name: wrong-status
    via: origin
    path: /health
    expect_status: 503
""")
    try:
        result = await ScenarioRunner(origin_client=client, proxy_client=proxy).run(scenario)
    finally:
        await client.aclose()
        await proxy.aclose()
    assert result.status is RunStatus.FAILED
