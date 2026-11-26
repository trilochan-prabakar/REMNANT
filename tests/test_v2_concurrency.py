"""Bounded concurrency tests for experiment isolation and Redis atomic writes."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from redis import Redis

from remnant.auth.policy import AuthorizationPolicy
from remnant.cache.manager import CachedHTTPResponse, RedisCacheManager
from remnant.cache.metadata import CacheMetadata
from remnant.engine.experiment import CacheReplayExperiment


@pytest.fixture
def shared_redis():
    client = Redis.from_url("redis://localhost:6379/0")
    client.ping()
    try:
        yield client
    finally:
        client.close()


def test_concurrent_experiments_are_isolated_for_same_identity_and_resource(shared_redis):
    prefix = f"remnant:concurrency-same:{uuid4().hex}:"
    cache = RedisCacheManager(client=shared_redis, key_prefix=prefix)
    barrier = Barrier(4)

    def execute(_):
        experiment = CacheReplayExperiment(cache=cache, policy=AuthorizationPolicy())
        barrier.wait(timeout=5)
        return experiment.run("alice", "document-1")

    results = []
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(execute, range(4)))

        assert len({result.experiment_id for result in results}) == 4
        keys = {
            CacheReplayExperiment._cache_key(
                result.experiment_id, result.principal_id, result.resource_id
            )
            for result in results
        }
        assert len(keys) == 4
        assert all(result.cache_primed for result in results)
        assert all(result.finding_status == "CONFIRMED" for result in results)
        assert all(result.analysis_evidence.replay_metadata.valid for result in results)
        assert all(
            result.analysis_evidence.replay_metadata.principal_id == "alice"
            and result.analysis_evidence.replay_metadata.resource_id == "document-1"
            for result in results
        )
    finally:
        for result in results:
            cache.delete(
                CacheReplayExperiment._cache_key(
                    result.experiment_id, result.principal_id, result.resource_id
                )
            )


@pytest.mark.parametrize(
    "cases",
    [
        (("alice", "document-1"), ("bob", "document-1"),
         ("carol", "document-1"), ("dave", "document-1")),
        (("alice", "document-1"), ("alice", "document-2"),
         ("bob", "document-1"), ("bob", "document-2")),
    ],
)
def test_concurrent_different_principals_or_resources_do_not_cross_contaminate(
    shared_redis, cases
):
    prefix = f"remnant:concurrency-mixed:{uuid4().hex}:"
    cache = RedisCacheManager(client=shared_redis, key_prefix=prefix)
    barrier = Barrier(len(cases))

    def execute(case):
        principal_id, resource_id = case
        experiment = CacheReplayExperiment(cache=cache, policy=AuthorizationPolicy())
        barrier.wait(timeout=5)
        return experiment.run(principal_id, resource_id)

    results = []
    try:
        with ThreadPoolExecutor(max_workers=len(cases)) as pool:
            results = list(pool.map(execute, cases))

        assert len({result.experiment_id for result in results}) == len(cases)
        assert all(result.finding_status == "CONFIRMED" for result in results)
        assert all(result.cache_primed for result in results)
        for result in results:
            evidence = result.analysis_evidence.replay_metadata
            assert evidence.valid is True
            assert evidence.principal_id == result.principal_id
            assert evidence.resource_id == result.resource_id
    finally:
        for result in results:
            cache.delete(
                CacheReplayExperiment._cache_key(
                    result.experiment_id, result.principal_id, result.resource_id
                )
            )


def test_concurrent_store_and_observe_on_shared_key_never_returns_torn_payload(shared_redis):
    prefix = f"remnant:concurrency-shared-key:{uuid4().hex}:"
    cache = RedisCacheManager(client=shared_redis, key_prefix=prefix)
    key = "shared"
    barrier = Barrier(8)
    payloads = {
        f"principal-{index}": f"complete-response-{index}".encode()
        for index in range(8)
    }

    def write(item):
        principal_id, body = item
        response = CachedHTTPResponse(200, (("content-type", "text/plain"),), body)
        metadata = CacheMetadata.create(
            principal_id=principal_id,
            resource_id="document-1",
            response_status=200,
            body=body,
            ttl_seconds=30,
        )
        barrier.wait(timeout=5)
        cache.store(key, response, ttl_seconds=30, metadata=metadata)
        return cache.observe(key)

    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            observations = list(pool.map(write, payloads.items()))

        # Redis SET replaces the serialized response+metadata value atomically.
        # Concurrent writers may overwrite one another; no winner/order is promised.
        for observation in observations:
            if observation.status.value == "HIT":
                assert observation.response is not None
                assert observation.metadata is not None
                assert observation.metadata.verify_body(observation.response.body)
                assert observation.metadata.response_status == observation.response.status_code
                assert observation.response.body in payloads.values()
                assert observation.metadata.principal_id in payloads
        final = cache.observe(key)
        assert final.status.value == "HIT"
        assert final.metadata is not None and final.response is not None
        assert final.metadata.verify_body(final.response.body)
    finally:
        cache.delete(key)
