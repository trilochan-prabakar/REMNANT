import json

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from remnant.cache.manager import (
    CacheStatus,
    CachedHTTPResponse,
    RedisCacheError,
    RedisCacheManager,
)


class ExpiringRedis:
    """Small deterministic Redis substitute for unit tests."""

    def __init__(self):
        self.now = 0
        self.values = {}

    def set(self, key, value, *, ex):
        self.values[key] = (value, self.now + ex)
        return True

    def get(self, key):
        item = self.values.get(key)
        if item is None:
            return None
        value, expires_at = item
        if self.now >= expires_at:
            del self.values[key]
            return None
        return value


def test_cache_hit_preserves_http_response_data():
    redis = ExpiringRedis()
    cache = RedisCacheManager(client=redis, key_prefix="test:")
    response = CachedHTTPResponse(
        status_code=200,
        headers=(("content-type", "text/plain"), ("x-tag", "one"), ("x-tag", "two")),
        body=b"private canary",
    )

    cache.store("resource-1", response, ttl_seconds=30)
    result = cache.lookup("resource-1")

    assert result.status is CacheStatus.HIT
    assert result.response == response
    assert "test:resource-1" in redis.values


def test_cache_miss_is_distinct_from_hit():
    cache = RedisCacheManager(client=ExpiringRedis())

    result = cache.lookup("not-cached")

    assert result.status is CacheStatus.MISS
    assert result.response is None


def test_expired_response_is_a_cache_miss():
    redis = ExpiringRedis()
    cache = RedisCacheManager(client=redis)
    response = CachedHTTPResponse(200, (("content-type", "text/plain"),), b"body")
    cache.store("short-lived", response, ttl_seconds=2)

    redis.now = 2
    result = cache.lookup("short-lived")

    assert result.status is CacheStatus.MISS
    assert result.response is None


@pytest.mark.parametrize("operation", ["lookup", "store"])
def test_redis_connection_failure_is_not_reported_as_cache_miss(operation):
    class BrokenRedis:
        def get(self, key):
            raise RedisConnectionError("Redis unavailable")

        def set(self, key, value, *, ex):
            raise RedisConnectionError("Redis unavailable")

    cache = RedisCacheManager(client=BrokenRedis())
    response = CachedHTTPResponse(200, (), b"body")

    with pytest.raises(RedisCacheError, match="Redis operation failed"):
        if operation == "lookup":
            cache.lookup("resource-1")
        else:
            cache.store("resource-1", response, ttl_seconds=10)


@pytest.mark.parametrize("ttl_seconds", [0, -1, 1.5, True])
def test_invalid_ttl_is_rejected_before_writing(ttl_seconds):
    redis = ExpiringRedis()
    cache = RedisCacheManager(client=redis)
    response = CachedHTTPResponse(200, (), b"body")

    with pytest.raises(ValueError, match="ttl_seconds must be a positive integer"):
        cache.store("resource-1", response, ttl_seconds=ttl_seconds)

    assert redis.values == {}


def test_stored_response_uses_replayable_json_payload():
    redis = ExpiringRedis()
    cache = RedisCacheManager(client=redis)
    response = CachedHTTPResponse(403, (("x-check", "denied"),), b"forbidden")

    cache.store("resource-1", response, ttl_seconds=5)
    payload, _ = redis.values["remnant:resource-1"]
    decoded = json.loads(payload)

    assert decoded == {
        "status_code": 403,
        "headers": [["x-check", "denied"]],
        "body": "Zm9yYmlkZGVu",
    }


def test_corrupt_cached_response_is_not_reported_as_a_miss():
    redis = ExpiringRedis()
    redis.values["remnant:resource-1"] = ('{"body":"not-base64!"}', 100)
    cache = RedisCacheManager(client=redis)

    with pytest.raises(RedisCacheError, match="Cached response data is invalid"):
        cache.lookup("resource-1")
