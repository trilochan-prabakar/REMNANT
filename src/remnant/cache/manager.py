"""Redis-backed storage for cached HTTP response snapshots."""

import base64
import json
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from redis import Redis
from redis.exceptions import RedisError


class CacheStatus(str, Enum):
    HIT = "HIT"
    MISS = "MISS"


@dataclass(frozen=True)
class CachedHTTPResponse:
    """HTTP response fields needed to replay and inspect a cached response."""

    status_code: int
    headers: tuple[tuple[str, str], ...]
    body: bytes


@dataclass(frozen=True)
class CacheResult:
    status: CacheStatus
    response: Optional[CachedHTTPResponse]


class RedisCacheError(RuntimeError):
    """Raised when Redis cannot complete a cache operation or data is invalid."""


class RedisCacheManager:
    """Store and retrieve HTTP response snapshots without authorization logic."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        *,
        client: Optional[Redis] = None,
        key_prefix: str = "remnant:",
    ) -> None:
        self._client = client if client is not None else Redis.from_url(redis_url)
        self._key_prefix = key_prefix

    def store(
        self,
        key: str,
        response: CachedHTTPResponse,
        *,
        ttl_seconds: int,
    ) -> None:
        if type(ttl_seconds) is not int or ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be a positive integer")

        payload = json.dumps(
            {
                "status_code": response.status_code,
                "headers": [list(header) for header in response.headers],
                "body": base64.b64encode(response.body).decode("ascii"),
            },
            separators=(",", ":"),
        )
        try:
            self._client.set(self._key(key), payload, ex=ttl_seconds)
        except RedisError as exc:
            raise RedisCacheError("Redis operation failed while storing response") from exc

    def lookup(self, key: str) -> CacheResult:
        try:
            payload = self._client.get(self._key(key))
        except RedisError as exc:
            raise RedisCacheError("Redis operation failed while retrieving response") from exc

        if payload is None:
            return CacheResult(CacheStatus.MISS, None)

        try:
            data = json.loads(payload)
            status_code = data["status_code"]
            headers = data["headers"]
            body = data["body"]
            if (
                not isinstance(status_code, int)
                or not isinstance(headers, list)
                or any(
                    not isinstance(header, list)
                    or len(header) != 2
                    or not all(isinstance(value, str) for value in header)
                    for header in headers
                )
                or not isinstance(body, str)
            ):
                raise ValueError("cached response has an invalid shape")
            response = CachedHTTPResponse(
                status_code=status_code,
                headers=tuple((header[0], header[1]) for header in headers),
                body=base64.b64decode(body, validate=True),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RedisCacheError("Cached response data is invalid") from exc

        return CacheResult(CacheStatus.HIT, response)

    def _key(self, key: str) -> str:
        if not key:
            raise ValueError("cache key cannot be empty")
        return f"{self._key_prefix}{key}"
