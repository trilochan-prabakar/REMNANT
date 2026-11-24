"""Real Redis coverage for the complete authorization replay experiment."""

from uuid import uuid4

import pytest
from redis import Redis
from redis.exceptions import RedisError

from remnant.cache.manager import CacheStatus, RedisCacheManager
from remnant.engine.experiment import CacheReplayExperiment


def test_real_redis_replays_cached_response_after_permission_revocation():
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

        key_prefix = f"remnant:experiment:{uuid4().hex}:"
        cache = RedisCacheManager(client=redis, key_prefix=key_prefix)
        result = CacheReplayExperiment(cache=cache).run(
            "alice",
            "document-1",
            ttl_seconds=5,
        )

        assert result.initial_authorization_status == 200
        assert result.cache_prime_status is CacheStatus.MISS
        assert result.cache_primed is True
        assert result.cached_canary == "remnant-canary-document-1-7b91c2e4"
        assert result.permission_revoked is True
        assert result.origin_status_after_revocation == 403
        assert result.cache_status is CacheStatus.HIT
        assert result.canary_match is True
        assert result.oracle_origin_denies is True
        assert result.oracle_cache_hit is True
        assert result.oracle_canary_matches is True
        assert result.finding_status == "CONFIRMED"

        keys = list(redis.scan_iter(match=f"{key_prefix}*"))
        assert len(keys) == 1
        assert 0 < redis.pttl(keys[0]) <= 5000
    finally:
        redis.close()
