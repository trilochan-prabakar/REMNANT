import json
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from remnant.cache.manager import CacheStatus
from remnant.analysis.models import (
    CacheMetadataEvidence,
    ComparisonState,
    DifferentialComparison,
    DimensionComparison,
    ExperimentAnalysisEvidence,
)
from remnant.engine.experiment import ExperimentResult
from remnant.storage import SQLiteEvidenceStore


def make_result(*, confirmed=True, experiment_id="experiment-1"):
    return ExperimentResult(
        experiment_id=experiment_id,
        principal_id="alice",
        resource_id="document-1",
        initial_authorization_status=200,
        cache_prime_status=CacheStatus.MISS,
        cache_primed=True,
        cached_canary="canary-1",
        permission_revoked=True,
        origin_status_after_revocation=403,
        cache_status=CacheStatus.HIT if confirmed else CacheStatus.MISS,
        canary_match=confirmed,
        oracle_origin_denies=True,
        oracle_cache_hit=confirmed,
        oracle_canary_matches=confirmed,
        finding_status="CONFIRMED" if confirmed else "NOT_FOUND",
    )


def test_initialize_creates_relational_schema_and_enables_foreign_keys(tmp_path):
    store = SQLiteEvidenceStore(tmp_path / "evidence.sqlite3")

    store.initialize()

    with store._connect() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = ?", ("table",)
            )
        }
        assert {"experiments", "experiment_evidence", "findings"} <= tables
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_save_successful_experiment_and_retrieve_structured_evidence(tmp_path):
    store = SQLiteEvidenceStore(tmp_path / "evidence.sqlite3")
    store.initialize()

    store.save_experiment(make_result())
    retrieved = store.get_experiment("experiment-1")

    assert retrieved["experiment_id"] == "experiment-1"
    assert retrieved["principal_id"] == "alice"
    assert retrieved["overall_outcome"] == "COMPLETED"
    assert retrieved["finding_status"] == "CONFIRMED"
    assert len(retrieved["evidence"]) == 6
    oracle_evidence = next(
        row for row in retrieved["evidence"] if row["stage_type"] == "finding_oracle"
    )
    assert json.loads(oracle_evidence["details_json"])["finding_confirmed"] is True
    assert retrieved["finding"]["canary_match"] == 1


def test_save_non_finding_experiment(tmp_path):
    store = SQLiteEvidenceStore(tmp_path / "evidence.sqlite3")
    store.initialize()

    store.save_experiment(make_result(confirmed=False))

    assert store.get_confirmed_findings() == []
    assert store.get_experiment("experiment-1")["finding_status"] == "NOT_FOUND"


def test_retrieve_missing_experiment_returns_none(tmp_path):
    store = SQLiteEvidenceStore(tmp_path / "evidence.sqlite3")
    store.initialize()

    assert store.get_experiment("missing") is None


def test_list_experiments_returns_multiple_experiments(tmp_path):
    store = SQLiteEvidenceStore(tmp_path / "evidence.sqlite3")
    store.initialize()
    store.save_experiment(make_result(experiment_id="one"))
    store.save_experiment(make_result(experiment_id="two"))

    results = store.list_experiments()

    assert [item["experiment_id"] for item in results] == ["one", "two"]


def test_get_confirmed_findings_returns_only_confirmed_findings(tmp_path):
    store = SQLiteEvidenceStore(tmp_path / "evidence.sqlite3")
    store.initialize()
    store.save_experiment(make_result(experiment_id="yes"))
    store.save_experiment(make_result(confirmed=False, experiment_id="no"))

    findings = store.get_confirmed_findings()

    assert [finding["experiment_id"] for finding in findings] == ["yes"]
    assert findings[0]["classification"] == "CACHE_AUTHORIZATION_INCONSISTENCY"


def test_schema_enforces_evidence_foreign_key(tmp_path):
    store = SQLiteEvidenceStore(tmp_path / "evidence.sqlite3")
    store.initialize()

    with store._connect() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO experiment_evidence
                   (experiment_id, stage_type, stage_outcome, timestamp, details_json)
                   VALUES (?, ?, ?, ?, ?)""",
                ("missing", "stage", "ok", "2026-01-01T00:00:00+00:00", "{}"),
            )


def test_evidence_persistence_failure_rolls_back_all_rows(tmp_path):
    store = SQLiteEvidenceStore(tmp_path / "evidence.sqlite3")
    store.initialize()
    with store._connect() as connection:
        connection.execute(
            """CREATE TRIGGER fail_evidence BEFORE INSERT ON experiment_evidence
               BEGIN SELECT RAISE(ABORT, 'evidence write failed'); END"""
        )

    with pytest.raises(sqlite3.IntegrityError, match="evidence write failed"):
        store.save_experiment(make_result())

    with store._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM experiments").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM findings").fetchone()[0] == 0


def test_experiment_persists_across_store_instances(tmp_path):
    database_path = tmp_path / "evidence.sqlite3"
    SQLiteEvidenceStore(database_path).save_experiment(make_result())

    retrieved = SQLiteEvidenceStore(database_path).get_experiment("experiment-1")

    assert retrieved["principal_id"] == "alice"
    assert len(retrieved["evidence"]) == 6


def test_in_memory_database_remains_available_across_store_connections():
    store = SQLiteEvidenceStore(":memory:")

    store.save_experiment(make_result())

    assert store.get_experiment("experiment-1")["finding_status"] == "CONFIRMED"


def test_inconsistent_oracle_result_cannot_be_stored_as_confirmed(tmp_path):
    store = SQLiteEvidenceStore(tmp_path / "evidence.sqlite3")
    inconsistent = replace(
        make_result(confirmed=False),
        oracle_origin_denies=False,
        oracle_cache_hit=False,
        oracle_canary_matches=False,
        finding_status="CONFIRMED",
    )

    with pytest.raises(ValueError, match="finding_status must match the finding oracle"):
        store.save_experiment(inconsistent)

    assert store.list_experiments() == []


def test_timestamps_are_utc_iso_values_and_structured_details_are_json(tmp_path):
    store = SQLiteEvidenceStore(tmp_path / "evidence.sqlite3")
    store.save_experiment(make_result())

    retrieved = store.get_experiment("experiment-1")

    started = datetime.fromisoformat(retrieved["started_at"])
    completed = datetime.fromisoformat(retrieved["completed_at"])
    assert started.tzinfo == timezone.utc
    assert completed.tzinfo == timezone.utc
    for evidence in retrieved["evidence"]:
        assert datetime.fromisoformat(evidence["timestamp"]).tzinfo == timezone.utc
        assert isinstance(json.loads(evidence["details_json"]), dict)


def test_experiment_timestamps_are_preserved_when_present(tmp_path):
    store = SQLiteEvidenceStore(tmp_path / "evidence.sqlite3")
    result = replace(
        make_result(),
        started_at="2026-01-02T03:04:05+00:00",
        completed_at="2026-01-02T03:04:06+00:00",
    )

    store.save_experiment(result)
    saved = store.get_experiment(result.experiment_id)

    assert saved["started_at"] == result.started_at
    assert saved["completed_at"] == result.completed_at
    assert {row["timestamp"] for row in saved["evidence"]} == {result.completed_at}



def make_analysis_evidence():
    indeterminate = DimensionComparison(ComparisonState.INDETERMINATE)
    differential = DifferentialComparison(
        state=ComparisonState.DIFFERENT,
        status_code=DimensionComparison(ComparisonState.DIFFERENT, 403, 200),
        selected_headers=indeterminate,
        body_digest=DimensionComparison(ComparisonState.DIFFERENT, "a" * 64, "b" * 64),
        canary=DimensionComparison(ComparisonState.MATCH, True, True),
        compared_headers=("content-type",),
    )
    metadata = CacheMetadataEvidence(
        present=True,
        valid=True,
        schema_version=1,
        principal_id="alice",
        resource_id="document-1",
        response_status=200,
        body_sha256="b" * 64,
    )
    return ExperimentAnalysisEvidence(
        schema_version=1,
        initial_origin_status=200,
        cache_prime_observation_status="HIT",
        cache_prime_metadata=metadata,
        post_revocation_origin_status=403,
        replay_observation_status="HIT",
        replay_metadata=metadata,
        differential=differential,
        diagnostic_categories=(),
    )


def test_analysis_evidence_is_saved_and_reloaded_as_additive_row(tmp_path):
    store = SQLiteEvidenceStore(tmp_path / "analysis.sqlite3")
    result = replace(make_result(), analysis_evidence=make_analysis_evidence())

    store.save_experiment(result)
    saved = store.get_experiment(result.experiment_id)

    assert saved["analysis"]["cache_observation_status"] == "HIT"
    assert saved["analysis"]["differential_state"] == "DIFFERENT"
    payload = json.loads(saved["analysis"]["analysis_json"])
    assert payload["replay_metadata"]["valid"] is True
    assert payload["differential"]["status_code"]["origin_value"] == 403
    assert len(saved["evidence"]) == 6


def test_legacy_result_persists_without_analysis_row(tmp_path):
    store = SQLiteEvidenceStore(tmp_path / "legacy.sqlite3")
    result = make_result()

    store.save_experiment(result)

    saved = store.get_experiment(result.experiment_id)
    assert saved["analysis"] is None
    assert len(saved["evidence"]) == 6


def test_schema_version_is_recorded_and_repeated_initialization_is_idempotent(tmp_path):
    store = SQLiteEvidenceStore(tmp_path / "versioned.sqlite3")

    store.initialize()
    store.initialize()

    with store._connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='experiment_analysis'"
        ).fetchone()[0] == 1


def test_existing_legacy_database_is_migrated_without_losing_records(tmp_path):
    database = tmp_path / "pre-migration.sqlite3"
    connection = sqlite3.connect(database)
    from remnant.storage.sqlite import _SCHEMA

    for statement in _SCHEMA.split(";"):
        if statement.strip():
            connection.execute(statement)
    connection.execute(
        """INSERT INTO experiments
           (experiment_id, principal_id, resource_id, started_at, completed_at,
            overall_outcome, finding_status)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("legacy-existing", "alice", "document-1", "2026-01-01T00:00:00+00:00",
         "2026-01-01T00:00:01+00:00", "COMPLETED", "NOT_FOUND"),
    )
    connection.commit()
    connection.close()

    store = SQLiteEvidenceStore(database)
    store.initialize()

    assert store.get_experiment("legacy-existing")["analysis"] is None
    with store._connect() as migrated:
        assert migrated.execute("PRAGMA user_version").fetchone()[0] == 1


def test_future_database_schema_version_is_rejected(tmp_path):
    database = tmp_path / "future.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA user_version = 999")
    connection.commit()
    connection.close()

    with pytest.raises(RuntimeError, match="newer than supported"):
        SQLiteEvidenceStore(database)


def test_analysis_insert_failure_rolls_back_entire_experiment_transaction(tmp_path):
    store = SQLiteEvidenceStore(tmp_path / "rollback-analysis.sqlite3")
    with store._connect() as connection:
        connection.execute(
            """CREATE TRIGGER fail_analysis BEFORE INSERT ON experiment_analysis
               BEGIN SELECT RAISE(ABORT, 'analysis write failed'); END"""
        )
    result = replace(make_result(), analysis_evidence=make_analysis_evidence())

    with pytest.raises(sqlite3.IntegrityError, match="analysis write failed"):
        store.save_experiment(result)

    with store._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM experiments").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM experiment_evidence").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM findings").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM experiment_analysis").fetchone()[0] == 0
