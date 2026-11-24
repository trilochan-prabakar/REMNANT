import json
from html.parser import HTMLParser

import pytest

from remnant.cache.manager import CacheStatus
from remnant.engine.experiment import ExperimentResult
from remnant.reporting import ExperimentNotFoundError, ReportGenerator
from remnant.storage import SQLiteEvidenceStore


def make_result(*, confirmed=True, experiment_id="experiment-1"):
    return ExperimentResult(
        experiment_id=experiment_id,
        principal_id='alice <img src=x onerror="alert(1)">',
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
        started_at="2026-01-02T03:04:05+00:00",
        completed_at="2026-01-02T03:04:06+00:00",
    )


def build_generator(tmp_path, result=None):
    store = SQLiteEvidenceStore(tmp_path / "evidence.sqlite3")
    store.save_experiment(result or make_result())
    return ReportGenerator(store, tmp_path / "reports"), store


def test_json_report_contains_persisted_confirmed_finding_and_oracle_conditions(tmp_path):
    generator, _ = build_generator(tmp_path)

    output_path = generator.generate_json("experiment-1")
    report = json.loads(output_path.read_text())

    assert output_path == tmp_path / "reports" / "experiment-1.json"
    assert report["report_schema_version"] == "1.0"
    assert report["experiment"] == {
        "experiment_id": "experiment-1",
        "principal_id": 'alice <img src=x onerror="alert(1)">',
        "resource_id": "document-1",
        "started_at": "2026-01-02T03:04:05+00:00",
        "completed_at": "2026-01-02T03:04:06+00:00",
    }
    assert report["finding_status"] == "CONFIRMED"
    assert report["oracle"]["conditions"] == {
        "origin_denies": True,
        "cache_hit": True,
        "canary_matches": True,
    }
    assert report["oracle"]["finding_confirmed"] is True
    assert report["stages"][0]["timestamp"] == "2026-01-02T03:04:06+00:00"
    assert report["stages"][0]["http_status"] == 200
    assert report["issues"] == []


def test_json_report_preserves_non_finding_booleans_and_values(tmp_path):
    generator, _ = build_generator(tmp_path, make_result(confirmed=False))

    report = json.loads(generator.generate_json("experiment-1").read_text())

    assert report["finding_status"] == "NOT_FOUND"
    assert report["oracle"]["conditions"] == {
        "origin_denies": True,
        "cache_hit": False,
        "canary_matches": False,
    }
    replay = next(stage for stage in report["stages"] if stage["stage_type"] == "cache_replay")
    assert replay["cache_status"] == "MISS"
    assert replay["canary_match"] is False


def test_html_report_is_standalone_and_escapes_untrusted_text(tmp_path):
    generator, _ = build_generator(tmp_path)
    output_path = generator.generate_html("experiment-1")
    html = output_path.read_text()

    assert output_path == tmp_path / "reports" / "experiment-1.html"
    assert "REMNANT" in html
    assert "CONFIRMED" in html
    assert "origin_denies" in html and "cache_hit" in html and "canary_matches" in html
    assert "alice &lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in html
    assert '<img src=x onerror="alert(1)">' not in html
    assert "<style" in html
    assert "https://" not in html and "http://" not in html
    assert "<script" not in html

    class DocumentParser(HTMLParser):
        pass

    DocumentParser().feed(html)


def test_html_distinguishes_incomplete_report_from_persisted_finding(tmp_path):
    generator, store = build_generator(tmp_path)
    with store._connect() as connection:
        connection.execute(
            "DELETE FROM experiment_evidence WHERE experiment_id = ? AND stage_type = ?",
            ("experiment-1", "finding_oracle"),
        )

    html = generator.generate_html("experiment-1").read_text()

    assert 'class="pill incomplete">INCOMPLETE' in html
    assert "Persisted finding: <strong>CONFIRMED</strong>" in html


def test_unknown_experiment_does_not_write_report(tmp_path):
    store = SQLiteEvidenceStore(tmp_path / "evidence.sqlite3")
    generator = ReportGenerator(store, tmp_path / "reports")

    with pytest.raises(ExperimentNotFoundError, match="missing"):
        generator.generate_json("missing")
    with pytest.raises(ExperimentNotFoundError, match="missing"):
        generator.generate_html("missing")
    assert not (tmp_path / "reports").exists()


def test_missing_and_failed_evidence_are_reported_without_inventing_values(tmp_path):
    generator, store = build_generator(tmp_path)
    with store._connect() as connection:
        connection.execute(
            "DELETE FROM experiment_evidence WHERE experiment_id = ? AND stage_type = ?",
            ("experiment-1", "cache_prime"),
        )
        connection.execute(
            "UPDATE experiment_evidence SET stage_outcome = ?, details_json = ? "
            "WHERE experiment_id = ? AND stage_type = ?",
            ("FAILED", '{"error":"cache backend unavailable"}', "experiment-1", "cache_replay"),
        )

    report = json.loads(generator.generate_json("experiment-1").read_text())
    stages = {stage["stage_type"]: stage for stage in report["stages"]}

    assert report["experiment_status"] == "FAILED"
    assert stages["cache_prime"]["status"] == "MISSING"
    assert stages["cache_prime"]["cache_status"] is None
    assert stages["cache_replay"]["status"] == "FAILED"
    assert report["issues"] == [
        {"type": "incomplete_stage", "stage_type": "cache_prime"},
        {
            "type": "failed_stage",
            "stage_type": "cache_replay",
            "stage_outcome": "FAILED",
        },
        {
            "type": "stage_error",
            "stage_type": "cache_replay",
            "message": "cache backend unavailable",
        },
    ]


def test_failed_stage_without_error_details_is_reported_as_an_issue(tmp_path):
    generator, store = build_generator(tmp_path)
    with store._connect() as connection:
        connection.execute(
            "UPDATE experiment_evidence SET stage_outcome = ?, details_json = ? "
            "WHERE experiment_id = ? AND stage_type = ?",
            ("FAILED", "{}", "experiment-1", "cache_replay"),
        )

    report = json.loads(generator.generate_json("experiment-1").read_text())
    html = generator.generate_html("experiment-1").read_text()

    assert report["issues"] == [
        {
            "type": "failed_stage",
            "stage_type": "cache_replay",
            "stage_outcome": "FAILED",
        }
    ]
    assert "Failed Stage" in html and "cache_replay" in html and "FAILED" in html
    assert "No errors, warnings, or incomplete stages." not in html


def test_incomplete_experiment_and_output_filename_are_safe(tmp_path):
    result = make_result(experiment_id="../outside")
    generator, store = build_generator(tmp_path, result)
    with store._connect() as connection:
        connection.execute(
            "DELETE FROM experiment_evidence WHERE experiment_id = ? AND stage_type = ?",
            ("../outside", "finding_oracle"),
        )
    output_path = generator.generate_json("../outside")
    report = json.loads(output_path.read_text())

    assert output_path.parent == tmp_path / "reports"
    assert report["experiment_status"] == "INCOMPLETE"
    assert report["stages"][-1]["stage_type"] == "finding_oracle"
    assert report["stages"][-1]["status"] == "MISSING"
    assert report["finding_status"] == "CONFIRMED"
    assert report["oracle"]["conditions"] == {
        "origin_denies": True,
        "cache_hit": True,
        "canary_matches": True,
    }


def test_malformed_persisted_details_are_tolerated(tmp_path):
    generator, store = build_generator(tmp_path)
    with store._connect() as connection:
        connection.execute(
            "UPDATE experiment_evidence SET details_json = ? WHERE stage_type = ?",
            ('"<script>alert(1)</script>"', "initial_authorization"),
        )

    report = json.loads(generator.generate_json("experiment-1").read_text())
    assert report["stages"][0]["details"] == {}
