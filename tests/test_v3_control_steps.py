import httpx
import pytest

from remnant.v3.runner import RunStatus, ScenarioRunner
from remnant.v3.scenarios import ScenarioLoader


SCENARIO = """
scenario:
  id: lifecycle
  name: Lifecycle
steps:
  - type: control
    name: grant
    operation: grant
    via: origin
    principal: alice
  - name: read
    via: proxy
    path: /private
    expect_status: 200
  - type: control
    name: revoke
    operation: revoke
    via: origin
    principal: alice
  - type: control
    name: purge
    operation: purge
    via: proxy
    path: /private
"""


@pytest.mark.asyncio
async def test_control_steps_require_explicit_opt_in_and_use_fixed_endpoints():
    seen = []

    def origin_handler(request):
        seen.append((request.method, request.url.path, request.read()))
        return httpx.Response(200, json={"ok": True})

    def proxy_handler(request):
        seen.append((request.method, request.url.path, request.read()))
        if request.method == "GET":
            return httpx.Response(200, headers={"X-Cache": "HIT"}, text="ok")
        return httpx.Response(200, text="purged")

    origin = httpx.AsyncClient(base_url="http://origin.test", transport=httpx.MockTransport(origin_handler))
    proxy = httpx.AsyncClient(base_url="http://proxy.test", transport=httpx.MockTransport(proxy_handler))
    scenario = ScenarioLoader().loads(SCENARIO)
    try:
        guarded = ScenarioRunner(origin_client=origin, proxy_client=proxy)
        with pytest.raises(PermissionError, match="allow_control_operations"):
            await guarded.run(scenario)

        runner = ScenarioRunner(
            origin_client=origin, proxy_client=proxy, allow_control_operations=True
        )
        result = await runner.run(scenario)
    finally:
        await origin.aclose()
        await proxy.aclose()

    assert result.status is RunStatus.PASSED
    assert [item[0] for item in seen] == ["POST", "GET", "POST", "PURGE"]
    assert seen[0][1] == "/__remnant__/control/grant"
    assert seen[2][1] == "/__remnant__/control/revoke"
    assert seen[3][1] == "/private"
    assert b'"principal":"alice"' in seen[0][2]


def test_loader_rejects_control_operation_on_wrong_client():
    scenario = SCENARIO.replace("via: origin", "via: proxy", 1)
    with pytest.raises(ValueError, match="grant/revoke require origin"):
        ScenarioLoader().loads(scenario)
