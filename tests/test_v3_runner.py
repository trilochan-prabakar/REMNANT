import asyncio

import httpx
import pytest

from remnant.v3.runner import RunStatus, ScenarioRunner, run_to_json
from remnant.v3.scenarios import ScenarioLoader


def test_runner_executes_origin_and_proxy_and_redacts_secrets():
    async def exercise():
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
    path: /protected/report?token=do-not-log
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
        assert "do-not-log" not in serialized
        assert "[REDACTED]" in result.traces[1].path
        assert result.traces[1].cache_analysis["cache_state"].value == "hit"

    asyncio.run(exercise())


def test_runner_marks_assertion_failure():
    async def exercise():
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

    asyncio.run(exercise())


def test_run_many_respects_supported_concurrency_and_returns_all_results():
    async def exercise():
        client = httpx.AsyncClient(
            base_url="http://origin.test",
            transport=httpx.MockTransport(lambda request: httpx.Response(200, text="ok")),
        )
        proxy = httpx.AsyncClient(
            base_url="http://proxy.test",
            transport=httpx.MockTransport(lambda request: httpx.Response(200, text="ok")),
        )
        scenario = ScenarioLoader().loads("""
scenario:
  id: parallel
  name: Parallel
steps:
  - name: health
    via: origin
    path: /health
    expect_status: 200
""")
        try:
            runner = ScenarioRunner(origin_client=client, proxy_client=proxy)
            results = await runner.run_many([scenario, scenario, scenario], max_concurrency=2)
        finally:
            await client.aclose()
            await proxy.aclose()
        assert len(results) == 3
        assert all(result.status is RunStatus.PASSED for result in results)

    asyncio.run(exercise())


def test_run_many_rejects_unbounded_concurrency():
    async def exercise():
        client = httpx.AsyncClient(base_url="http://origin.test")
        proxy = httpx.AsyncClient(base_url="http://proxy.test")
        try:
            runner = ScenarioRunner(origin_client=client, proxy_client=proxy)
            with pytest.raises(ValueError, match="max_concurrency"):
                await runner.run_many([], max_concurrency=1000)
        finally:
            await client.aclose()
            await proxy.aclose()

    asyncio.run(exercise())
