import asyncio
import sqlite3

import httpx
import pytest

from remnant.v3.evidence import V3EvidenceStore
from remnant.v3.runner import ScenarioRunner
from remnant.v3.scenarios import ScenarioLoader


def test_store_and_compare_runs_without_response_bodies(tmp_path):
    async def exercise():
        calls = {"count": 0}

        def handler(request):
            calls["count"] += 1
            return httpx.Response(
                200,
                headers={"X-Cache": "HIT" if calls["count"] > 1 else "MISS"},
                json={"canary": f"version-{calls['count']}"},
            )

        origin = httpx.AsyncClient(
            base_url="http://origin.test",
            transport=httpx.MockTransport(handler),
        )
        proxy = httpx.AsyncClient(
            base_url="http://proxy.test",
            transport=httpx.MockTransport(handler),
        )
        scenario = ScenarioLoader().loads("""
scenario:
  id: compare
  name: Compare
steps:
  - name: response
    via: proxy
    path: /resource
    expect_status: 200
""")
        try:
            runner = ScenarioRunner(origin_client=origin, proxy_client=proxy)
            first = await runner.run(scenario)
            second = await runner.run(scenario)
        finally:
            await origin.aclose()
            await proxy.aclose()
        return first, second

    first, second = asyncio.run(exercise())
    store = V3EvidenceStore(tmp_path / "evidence.sqlite3")
    store.save(first)
    store.save(second)
    assert store.get(first.run_id)["status"] == "passed"
    assert len(store.list_runs(scenario_id="compare")) == 2
    comparison = store.compare(first.run_id, second.run_id)
    assert comparison.changed_steps[0].step_name == "response"
    assert "body_sha256" in comparison.changed_steps[0].changed_fields
    assert "version-1" not in str(store.get(first.run_id))


def test_store_rejects_unknown_run(tmp_path):
    store = V3EvidenceStore(tmp_path / "evidence.sqlite3")
    with pytest.raises(KeyError):
        store.compare("missing-a", "missing-b")


def test_v3_schema_v1_migrates_additively_to_v2(tmp_path):
    import sqlite3

    database = tmp_path / "legacy-v3.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript("""
            CREATE TABLE v3_runs (
                run_id TEXT PRIMARY KEY,
                scenario_id TEXT NOT NULL,
                scenario_name TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('passed', 'failed', 'error')),
                payload_json TEXT NOT NULL
            );
            CREATE INDEX idx_v3_runs_scenario ON v3_runs(scenario_id, completed_at);
            PRAGMA user_version = 1;
        """)

    V3EvidenceStore(database)
    with sqlite3.connect(database) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='v3_identity_isolation'"
        ).fetchone()
    assert version == 2
    assert table is not None
