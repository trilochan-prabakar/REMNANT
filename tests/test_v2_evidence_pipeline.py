"""End-to-end V2 evidence pipeline: engine -> SQLite -> JSON/HTML reports."""

import json
from uuid import uuid4

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from remnant.auth.policy import AuthorizationPolicy
from remnant.cache.manager import CacheStatus, RedisCacheManager
from remnant.engine.experiment import CacheReplayExperiment
from remnant.reporting import ReportGenerator
from remnant.storage import SQLiteEvidenceStore


class ExpiringRedis:
    def __init__(self):
        self.now = 0
        self.values = {}

    def set(self, key, value, *, ex):
        self.values[key] = (value, self.now + ex)

    def get(self, key):
        item = self.values.get(key)
        if item is None:
            return None
        value, expires_at = item
        if self.now >= expires_at:
            self.values.pop(key, None)
            return None
        return value


class UnavailableRedis:
    def get(self, key):
        raise RedisConnectionError("redis is unavailable")

    def set(self, key, value, *, ex):
        raise RedisConnectionError("redis is unavailable")


class WriteFailingRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, *, ex):
        raise RedisConnectionError("redis write is unavailable")


def make_store(tmp_path):
    return SQLiteEvidenceStore(tmp_path / "pipeline.sqlite3")


def test_confirmed_experiment_survives_engine_storage_and_both_reports(tmp_path):
    redis = ExpiringRedis()
    cache = RedisCacheManager(client=redis, key_prefix=f"pipeline:{uuid4().hex}:")
    result = CacheReplayExperiment(cache=cache).run("alice", "document-1")
    store = make_store(tmp_path)

    store.save_experiment(result)
    saved = store.get_experiment(result.experiment_id)
    generator = ReportGenerator(store, tmp_path / "reports")
    json_report = json.loads(generator.generate_json(result.experiment_id).read_text())
    html_report = generator.generate_html(result.experiment_id).read_text()
    analysis = json.loads(saved["analysis"]["analysis_json"])

    assert saved["experiment_id"] == result.experiment_id
    assert saved["finding_status"] == result.finding_status == "CONFIRMED"
    assert saved["analysis"]["cache_observation_status"] == "HIT"
    assert analysis["replay_observation_status"] == "HIT"
    assert analysis["replay_metadata"]["valid"] is True
    assert analysis["replay_metadata"]["principal_id"] == result.principal_id
    assert analysis["replay_metadata"]["resource_id"] == result.resource_id
    assert analysis["differential"]["state"] == result.differential_state
    assert json_report["experiment"]["experiment_id"] == result.experiment_id
    assert json_report["report_schema_version"] == "2.0"
    assert json_report["finding_status"] == "CONFIRMED"
    assert json_report["analysis"] == analysis
    assert len(json_report["stages"]) == 6
    assert "V2 analysis evidence" in html_report
    assert "DIFFERENT" in html_report
    assert result.oracle_origin_denies and result.oracle_cache_hit
    assert result.oracle_canary_matches


def test_cache_backend_error_remains_indeterminate_through_storage_and_reports(tmp_path):
    cache = RedisCacheManager(
        client=UnavailableRedis(), key_prefix=f"pipeline:{uuid4().hex}:"
    )
    result = CacheReplayExperiment(cache=cache).run("alice", "document-1")
    store = make_store(tmp_path)

    store.save_experiment(result)
    saved = store.get_experiment(result.experiment_id)
    report = json.loads(
        ReportGenerator(store, tmp_path / "reports")
        .generate_json(result.experiment_id)
        .read_text()
    )
    analysis = json.loads(saved["analysis"]["analysis_json"])

    assert result.finding_status == "NOT_FOUND"
    assert result.cache_observation_status == "BACKEND_ERROR"
    assert result.oracle_cache_hit is False
    assert saved["finding_status"] == "NOT_FOUND"
    assert saved["analysis"]["cache_observation_status"] == "BACKEND_ERROR"
    assert analysis["differential"]["state"] == "INDETERMINATE"
    assert "CACHE_BACKEND_ERROR" in analysis["diagnostic_categories"]
    assert report["analysis"]["replay_observation_status"] == "BACKEND_ERROR"
    assert report["oracle"]["finding_confirmed"] is False


def test_cache_write_failure_is_recorded_and_never_reported_as_a_prime(tmp_path):
    cache = RedisCacheManager(
        client=WriteFailingRedis(), key_prefix=f"pipeline:{uuid4().hex}:"
    )
    result = CacheReplayExperiment(cache=cache).run("alice", "document-1")
    store = make_store(tmp_path)

    store.save_experiment(result)
    saved = store.get_experiment(result.experiment_id)
    report = json.loads(
        ReportGenerator(store, tmp_path / "reports")
        .generate_json(result.experiment_id)
        .read_text()
    )
    analysis = json.loads(saved["analysis"]["analysis_json"])

    assert result.cache_primed is False
    assert result.cache_prime_status is CacheStatus.MISS
    assert analysis["cache_prime_observation_status"] == "BACKEND_ERROR"
    assert analysis["cache_prime_metadata"]["present"] is False
    assert "CACHE_BACKEND_ERROR" in analysis["diagnostic_categories"]
    assert result.permission_revoked is True
    assert result.origin_status_after_revocation == 403
    assert result.oracle_cache_hit is False
    assert result.finding_status == "NOT_FOUND"
    assert saved["finding_status"] == "NOT_FOUND"
    assert report["analysis"]["cache_prime_observation_status"] == "BACKEND_ERROR"
    assert report["oracle"]["finding_confirmed"] is False


def test_expired_cache_negative_result_survives_full_pipeline(tmp_path):
    redis = ExpiringRedis()
    policy = AuthorizationPolicy()
    original_revoke = policy.revoke

    def revoke_and_expire(principal_id, resource_id):
        original_revoke(principal_id, resource_id)
        redis.now += 2

    policy.revoke = revoke_and_expire
    cache = RedisCacheManager(client=redis, key_prefix=f"pipeline:{uuid4().hex}:")
    result = CacheReplayExperiment(cache=cache, policy=policy).run(
        "alice", "document-1", ttl_seconds=1
    )
    store = make_store(tmp_path)

    store.save_experiment(result)
    saved = store.get_experiment(result.experiment_id)
    report = json.loads(
        ReportGenerator(store, tmp_path / "reports")
        .generate_json(result.experiment_id)
        .read_text()
    )

    assert result.cache_status is CacheStatus.MISS
    assert result.finding_status == "NOT_FOUND"
    assert result.cache_observation_status == "MISS"
    assert saved["finding_status"] == "NOT_FOUND"
    assert saved["analysis"]["cache_observation_status"] == "MISS"
    assert report["analysis"]["differential"]["state"] == "INDETERMINATE"
    assert report["oracle"]["finding_confirmed"] is False


def test_origin_transport_error_propagates_without_creating_a_finding(tmp_path):
    class FailingOrigin:
        async def get_protected(self, resource_id, *, principal_id):
            raise RuntimeError("origin transport unavailable")

    cache = RedisCacheManager(
        client=ExpiringRedis(), key_prefix=f"pipeline:{uuid4().hex}:"
    )
    experiment = CacheReplayExperiment(cache=cache, origin_adapter=FailingOrigin())
    store = make_store(tmp_path)

    with pytest.raises(RuntimeError, match="origin transport unavailable"):
        experiment.run("alice", "document-1")

    assert store.list_experiments() == []
    assert store.get_confirmed_findings() == []
