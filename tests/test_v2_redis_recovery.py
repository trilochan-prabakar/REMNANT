"""Transient Redis failure and recovery through the real Redis service."""

from uuid import uuid4

import pytest
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError, RedisError

from remnant.cache.manager import RedisCacheManager
from remnant.engine.experiment import CacheReplayExperiment
from remnant.reporting import ReportGenerator
from remnant.storage import SQLiteEvidenceStore


class IntermittentRedis:
    """Test proxy that fails selected Redis operations, then recovers."""

    def __init__(self, client, *, fail_get_calls=(), fail_set_calls=()):
        self.client = client
        self.fail_get_calls = set(fail_get_calls)
        self.fail_set_calls = set(fail_set_calls)
        self.get_calls = 0
        self.set_calls = 0

    def get(self, key):
        self.get_calls += 1
        if self.get_calls in self.fail_get_calls:
            raise RedisConnectionError("injected transient Redis read failure")
        return self.client.get(key)

    def set(self, key, value, *, ex):
        self.set_calls += 1
        if self.set_calls in self.fail_set_calls:
            raise RedisConnectionError("injected transient Redis write failure")
        return self.client.set(key, value, ex=ex)

    def delete(self, key):
        return self.client.delete(key)


@pytest.fixture
def real_redis_client():
    client = Redis.from_url(
        "redis://localhost:6379/0",
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    try:
        try:
            client.ping()
        except RedisError as exc:
            pytest.skip(f"localhost:6379 Redis is unavailable: {exc}")
        yield client
    finally:
        client.close()


def make_experiment(client, prefix):
    cache = RedisCacheManager(client=client, key_prefix=prefix)
    return cache, CacheReplayExperiment(cache=cache)


def remove_run_key(cache, experiment, result):
    cache.delete(
        experiment._cache_key(
            result.experiment_id, result.principal_id, result.resource_id
        )
    )


def test_initial_read_failure_is_indeterminate_then_independent_run_recovers(
    real_redis_client, tmp_path
):
    proxy = IntermittentRedis(real_redis_client, fail_get_calls={1})
    cache, experiment = make_experiment(proxy, f"remnant:recovery-read:{uuid4().hex}:")
    first = None
    recovered = None
    store = SQLiteEvidenceStore(tmp_path / "read-recovery.sqlite3")

    try:
        first = experiment.run("alice", "document-1")
        assert first.finding_status == "NOT_FOUND"
        assert first.analysis_evidence.cache_prime_observation_status == "BACKEND_ERROR"
        assert first.cache_observation_status == "MISS"
        # The initial read failure prevents cache priming. The replay then
        # observes a miss and receives the independently denied origin response.
        assert first.oracle_origin_denies is True
        assert first.oracle_cache_hit is False
        assert first.oracle_canary_matches is False

        recovered = experiment.run("alice", "document-1")
        assert recovered.finding_status == "CONFIRMED"
        assert recovered.cache_observation_status == "HIT"
        assert recovered.oracle_origin_denies
        assert recovered.oracle_cache_hit
        assert recovered.oracle_canary_matches

        store.save_experiment(first)
        store.save_experiment(recovered)
        first_saved = store.get_experiment(first.experiment_id)
        recovered_saved = store.get_experiment(recovered.experiment_id)
        assert first_saved["finding_status"] == "NOT_FOUND"
        assert recovered_saved["finding_status"] == "CONFIRMED"

        report = ReportGenerator(store, tmp_path / "reports")
        first_json = report.generate_json(first.experiment_id).read_text()
        recovered_json = report.generate_json(recovered.experiment_id).read_text()
        assert '"finding_confirmed": false' in first_json
        assert '"finding_confirmed": true' in recovered_json
    finally:
        if first is not None:
            remove_run_key(cache, experiment, first)
        if recovered is not None:
            remove_run_key(cache, experiment, recovered)


def test_failed_prime_write_is_indeterminate_then_later_write_recovers(
    real_redis_client
):
    proxy = IntermittentRedis(real_redis_client, fail_set_calls={1})
    cache, experiment = make_experiment(proxy, f"remnant:recovery-write:{uuid4().hex}:")
    first = None
    recovered = None

    try:
        first = experiment.run("alice", "document-1")
        assert first.cache_primed is False
        assert first.analysis_evidence.cache_prime_observation_status == "BACKEND_ERROR"
        assert first.finding_status == "NOT_FOUND"
        assert first.oracle_cache_hit is False

        recovered = experiment.run("alice", "document-1")
        assert recovered.cache_primed is True
        assert recovered.finding_status == "CONFIRMED"
        assert recovered.oracle_origin_denies
        assert recovered.oracle_cache_hit
        assert recovered.oracle_canary_matches
    finally:
        if first is not None:
            remove_run_key(cache, experiment, first)
        if recovered is not None:
            remove_run_key(cache, experiment, recovered)


def test_replay_read_failure_after_successful_prime_is_not_a_finding_then_recovers(
    real_redis_client
):
    # Reads: pre-prime MISS, post-prime HIT, replay read failure.
    proxy = IntermittentRedis(real_redis_client, fail_get_calls={3})
    cache, experiment = make_experiment(proxy, f"remnant:recovery-replay:{uuid4().hex}:")
    first = None
    recovered = None

    try:
        first = experiment.run("alice", "document-1")
        assert first.cache_primed is True
        assert first.cache_observation_status == "BACKEND_ERROR"
        assert first.finding_status == "NOT_FOUND"
        assert first.oracle_origin_denies is True
        assert first.oracle_cache_hit is False
        assert first.oracle_canary_matches is False

        recovered = experiment.run("alice", "document-1")
        assert recovered.cache_primed is True
        assert recovered.cache_observation_status == "HIT"
        assert recovered.finding_status == "CONFIRMED"
        assert recovered.oracle_origin_denies
        assert recovered.oracle_cache_hit
        assert recovered.oracle_canary_matches
    finally:
        if first is not None:
            remove_run_key(cache, experiment, first)
        if recovered is not None:
            remove_run_key(cache, experiment, recovered)
