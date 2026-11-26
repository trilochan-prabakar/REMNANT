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
            INSERT INTO v3_runs VALUES (
                'legacy-run', 'legacy-scenario', 'Legacy scenario',
                '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:01+00:00',
                'passed', '{}'
            );
            PRAGMA user_version = 1;
        """)

    store = V3EvidenceStore(database)
    with sqlite3.connect(database) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='v3_identity_isolation'"
        ).fetchone()
    assert version == 2
    assert table is not None
    assert store.get("legacy-run") == {}


def test_identity_isolation_evidence_is_linked_and_body_free(tmp_path):
    from remnant.v3.identity_isolation import evaluate_identity_isolation
    from remnant.v3.runner import RunStatus, ScenarioRun

    run = ScenarioRun(
        run_id="identity-run",
        scenario_id="identity-scenario",
        scenario_name="Identity isolation",
        started_at="2026-11-26T00:00:00+00:00",
        completed_at="2026-11-26T00:00:01+00:00",
        status=RunStatus.PASSED,
        traces=(),
    )
    secret_canary = "owner-private-marker-7f3c"
    result = evaluate_identity_isolation(
        requester_id="alice",
        owner_id="bob",
        origin_status=403,
        proxy_status=200,
        proxy_cache_state="hit",
        proxy_body=(f'{{"canary":"{secret_canary}"}}').encode(),
        expected_owner_canary=secret_canary,
    )

    database = tmp_path / "evidence.sqlite3"
    store = V3EvidenceStore(database)
    store.save(run)
    store.save_identity_isolation(run.run_id, result)

    saved = store.get_identity_isolation(run.run_id)
    assert saved is not None
    assert saved["status"] == "confirmed"
    assert saved["requester_id"] == "alice"
    assert saved["owner_id"] == "bob"
    assert saved["foreign_canary_match"] is True
    assert secret_canary not in str(saved)

    with sqlite3.connect(database) as connection:
        persisted = connection.execute(
            "SELECT payload_json FROM v3_identity_isolation WHERE run_id = ?",
            (run.run_id,),
        ).fetchone()[0]
    assert secret_canary not in persisted
    assert "proxy_body" not in persisted


def test_identity_isolation_evidence_requires_an_existing_run(tmp_path):
    from remnant.v3.identity_isolation import evaluate_identity_isolation

    store = V3EvidenceStore(tmp_path / "evidence.sqlite3")
    result = evaluate_identity_isolation(
        requester_id="alice",
        owner_id="bob",
        origin_status=403,
        proxy_status=200,
        proxy_cache_state="hit",
        proxy_body=b'{"canary":"owner-marker"}',
        expected_owner_canary="owner-marker",
    )
    with pytest.raises(sqlite3.IntegrityError):
        store.save_identity_isolation("missing-run", result)
