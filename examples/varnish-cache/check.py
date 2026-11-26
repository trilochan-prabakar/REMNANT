"""Run the V3 scenario runner against the real local Varnish fixture."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import httpx

from remnant.v3 import RunStatus, ScenarioLoader, ScenarioRunner, run_to_json


async def main() -> None:
    varnish_url = os.environ.get("REMNANT_VARNISH_URL", "http://127.0.0.1:8088")
    origin_url = os.environ.get("REMNANT_VARNISH_ORIGIN_URL", "http://127.0.0.1:8000")
    scenario_path = Path("examples/varnish-cache/scenario.yml")
    scenario = ScenarioLoader().loads(scenario_path.read_text(encoding="utf-8"))

    async with (
        httpx.AsyncClient(base_url=origin_url) as origin,
        httpx.AsyncClient(base_url=varnish_url) as proxy,
    ):
        runner = ScenarioRunner(
            origin_client=origin,
            proxy_client=proxy,
            timeout_seconds=5,
            allow_control_operations=True,
        )
        result = await runner.run(scenario)

    print(run_to_json(result))
    if result.status is not RunStatus.PASSED:
        raise SystemExit(f"Varnish V3 scenario did not pass: {result.status.value}")


if __name__ == "__main__":
    asyncio.run(main())
