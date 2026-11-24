"""Integration coverage for RedisCacheManager against localhost Redis."""

import time
from uuid import uuid4

import pytest
from redis import Redis
from redis.exceptions import RedisError

from remnant.cache.manager import CacheStatus, CachedHTTPResponse, RedisCacheManager


def test_redis_cache_round_trip_and_ttl_expiration():
    redis = Redis.from_url(
        "redis://localhost:6379/0",
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    try:
        try:
            redis.ping()
        except RedisError as exc:
            pytest.skip(f"localhost:6379 Redis is unavailable: {exc}")

        key_prefix = f"remnant:integration:{uuid4().hex}:"
        cache = RedisCacheManager(client=redis, key_prefix=key_prefix)
        key = "response"
        expected = CachedHTTPResponse(
            status_code=206,
            headers=(
                ("content-type", "application/octet-stream"),
                ("x-tag", "one"),
                ("x-tag", "two"),
            ),
            body=b"\x00redis response\xff",
        )

        miss = cache.lookup(key)
        assert miss.status is CacheStatus.MISS
        assert miss.response is None

        cache.store(key, expected, ttl_seconds=1)

        hit = cache.lookup(key)
        assert hit.status is CacheStatus.HIT
        assert hit.response == expected
        assert 0 < redis.pttl(f"{key_prefix}{key}") <= 1000

        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            expired = cache.lookup(key)
            if expired.status is CacheStatus.MISS:
                break
            time.sleep(0.05)
        else:
            pytest.fail("Redis cache entry did not expire within 3 seconds")

        assert expired.response is None
    finally:
        redis.close()
