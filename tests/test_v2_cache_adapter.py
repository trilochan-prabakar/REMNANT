import json

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from remnant.cache.manager import (
    CacheStatus,
    CachedHTTPResponse,
    RedisCacheBackendError,
    RedisCacheError,
    RedisCacheManager,
)
from remnant.cache.metadata import CacheMetadata
from remnant.cache.models import CacheObservationStatus
from remnant.cache.protocols import CacheAdapter


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.deleted = []

    def set(self, key, value, *, ex):
        self.values[key] = value
        return True

    def get(self, key):
        return self.values.get(key)

    def delete(self, key):
        self.deleted.append(key)
        return int(self.values.pop(key, None) is not None)


def response():
    return CachedHTTPResponse(200, (("content-type", "application/json"),), b'{"canary":"abc"}')


def metadata(*, now=100.0, ttl=30):
    return CacheMetadata.create(
        principal_id="alice", resource_id="document-1",
        response_status=200, body=response().body, ttl_seconds=ttl, now=now,
    )


def test_redis_manager_satisfies_storage_only_adapter_contract():
    cache = RedisCacheManager(client=FakeRedis())
    assert isinstance(cache, CacheAdapter)


def test_v2_metadata_round_trips_through_redis_manager():
    redis = FakeRedis()
    cache = RedisCacheManager(client=redis, key_prefix="contract:")
    cache.store("entry", response(), ttl_seconds=30, metadata=metadata())

    result = cache.lookup("entry")

    assert result.status is CacheStatus.HIT
    assert result.response == response()
    assert result.metadata == metadata()


def test_observe_returns_hit_with_verified_metadata():
    cache = RedisCacheManager(client=FakeRedis())
    cache.store("entry", response(), ttl_seconds=30, metadata=metadata())

    observation = cache.observe("entry", now=101.0)

    assert observation.status is CacheObservationStatus.HIT
    assert observation.response == response()
    assert observation.metadata == metadata()


def test_observe_distinguishes_metadata_expiry_from_missing_key():
    cache = RedisCacheManager(client=FakeRedis())
    cache.store("entry", response(), ttl_seconds=30, metadata=metadata(now=100, ttl=2))

    observation = cache.observe("entry", now=102.0)

    assert observation.status is CacheObservationStatus.EXPIRED
    assert observation.response is None
    assert observation.metadata is not None


def test_observe_maps_missing_key_to_miss():
    observation = RedisCacheManager(client=FakeRedis()).observe("missing")
    assert observation.status is CacheObservationStatus.MISS


def test_observe_maps_backend_failure_without_calling_it_a_miss():
    class BrokenRedis:
        def get(self, key):
            raise RedisConnectionError("offline")

    observation = RedisCacheManager(client=BrokenRedis()).observe("entry")
    assert observation.status is CacheObservationStatus.BACKEND_ERROR


def test_observe_maps_corrupt_payload_to_invalid_metadata():
    redis = FakeRedis()
    redis.values["remnant:entry"] = '{"status_code":200,"headers":[],"body":"not base64"}'
    observation = RedisCacheManager(client=redis).observe("entry")
    assert observation.status is CacheObservationStatus.INVALID_METADATA


def test_metadata_mismatch_is_rejected_before_write():
    cache = RedisCacheManager(client=FakeRedis())
    bad_metadata = CacheMetadata.create(
        principal_id="alice", resource_id="doc", response_status=200,
        body=b"different", ttl_seconds=30, now=100,
    )
    with pytest.raises(ValueError, match="does not match response"):
        cache.store("entry", response(), ttl_seconds=30, metadata=bad_metadata)


def test_metadata_digest_tampering_is_detected_on_read():
    redis = FakeRedis()
    cache = RedisCacheManager(client=redis)
    cache.store("entry", response(), ttl_seconds=30, metadata=metadata())
    payload = json.loads(redis.values["remnant:entry"])
    payload["body"] = "dGFtcGVyZWQ="
    redis.values["remnant:entry"] = json.dumps(payload)

    assert cache.observe("entry").status is CacheObservationStatus.INVALID_METADATA


def test_delete_only_removes_the_requested_namespaced_key():
    redis = FakeRedis()
    cache = RedisCacheManager(client=redis, key_prefix="isolated:")
    cache.store("one", response(), ttl_seconds=30)
    cache.store("two", response(), ttl_seconds=30)

    assert cache.delete("one") is True
    assert "isolated:one" in redis.deleted
    assert "isolated:two" in redis.values
    assert "isolated:two" not in redis.deleted


@pytest.mark.parametrize("timestamp", [True, "101", float("nan"), float("inf"), float("-inf")])
def test_observe_rejects_invalid_explicit_clock_values(timestamp):
    cache = RedisCacheManager(client=FakeRedis())

    with pytest.raises(ValueError, match="finite numeric Unix timestamp"):
        cache.observe("missing", now=timestamp)


def test_observe_accepts_integer_explicit_clock_value():
    cache = RedisCacheManager(client=FakeRedis())
    cache.store("entry", response(), ttl_seconds=30, metadata=metadata(now=100))

    observation = cache.observe("entry", now=101)

    assert observation.status is CacheObservationStatus.HIT
