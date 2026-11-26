"""Redis-backed storage for cached HTTP response snapshots."""

import base64
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from redis import Redis
from redis.exceptions import RedisError

from remnant.cache.metadata import CacheMetadata
from remnant.cache.models import CacheObservation, CacheObservationStatus


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
    metadata: Optional[CacheMetadata] = None


class RedisCacheError(RuntimeError):
    """Raised when Redis cannot complete a cache operation or data is invalid."""


class RedisCacheBackendError(RedisCacheError):
    """Raised when Redis itself cannot complete an operation."""


class RedisCacheManager:
    """Store and retrieve response snapshots; never evaluates authorization."""

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
        metadata: Optional[CacheMetadata] = None,
    ) -> None:
        if type(ttl_seconds) is not int or ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be a positive integer")
        if metadata is not None and (
            metadata.response_status != response.status_code
            or not metadata.verify_body(response.body)
        ):
            raise ValueError("cache metadata does not match response")

        data = {
            "status_code": response.status_code,
            "headers": [list(header) for header in response.headers],
            "body": base64.b64encode(response.body).decode("ascii"),
        }
        # Keep the original V1 payload byte-for-byte compatible when metadata
        # is not supplied. V2 records add a separately validated metadata field.
        if metadata is not None:
            data["metadata"] = metadata.to_dict()
        payload = json.dumps(data, separators=(",", ":"))
        try:
            self._client.set(self._key(key), payload, ex=ttl_seconds)
        except RedisError as exc:
            raise RedisCacheBackendError(
                "Redis operation failed while storing response"
            ) from exc

    def lookup(self, key: str) -> CacheResult:
        try:
            payload = self._client.get(self._key(key))
        except RedisError as exc:
            raise RedisCacheBackendError(
                "Redis operation failed while retrieving response"
            ) from exc

        if payload is None:
            return CacheResult(CacheStatus.MISS, None)

        try:
            data = json.loads(payload)
            status_code = data["status_code"]
            headers = data["headers"]
            body = data["body"]
            if (
                type(status_code) is not int
                or not 100 <= status_code <= 599
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
            raw_metadata = data.get("metadata")
            metadata = (
                CacheMetadata.from_dict(raw_metadata)
                if raw_metadata is not None
                else None
            )
            if metadata is not None and (
                metadata.response_status != response.status_code
                or not metadata.verify_body(response.body)
            ):
                raise ValueError("cached response does not match metadata")
        except (KeyError, TypeError, ValueError) as exc:
            raise RedisCacheError("Cached response data is invalid") from exc

        return CacheResult(CacheStatus.HIT, response, metadata)

    def observe(self, key: str, *, now: Optional[float] = None) -> CacheObservation:
        """Return an explicit V2 observation without collapsing errors to misses."""
        if now is not None and (
            type(now) not in (int, float) or (type(now) is float and not math.isfinite(now))
        ):
            raise ValueError("now must be a finite numeric Unix timestamp")

        try:
            result = self.lookup(key)
        except RedisCacheBackendError as exc:
            return CacheObservation(
                CacheObservationStatus.BACKEND_ERROR,
                diagnostic=str(exc),
            )
        except RedisCacheError as exc:
            return CacheObservation(
                CacheObservationStatus.INVALID_METADATA,
                diagnostic=str(exc),
            )

        if result.status is CacheStatus.MISS:
            return CacheObservation(CacheObservationStatus.MISS)
        if result.metadata is not None:
            current_time = (
                datetime.now(timezone.utc).timestamp() if now is None else now
            )
            if current_time >= result.metadata.expires_at:
                return CacheObservation(
                    CacheObservationStatus.EXPIRED,
                    metadata=result.metadata,
                )
        return CacheObservation(
            CacheObservationStatus.HIT,
            response=result.response,
            metadata=result.metadata,
        )

    def delete(self, key: str) -> bool:
        """Delete one namespaced cache key; never flushes the Redis database."""
        try:
            return bool(self._client.delete(self._key(key)))
        except RedisError as exc:
            raise RedisCacheBackendError(
                "Redis operation failed while deleting response"
            ) from exc

    def _key(self, key: str) -> str:
        if not key:
            raise ValueError("cache key cannot be empty")
        return f"{self._key_prefix}{key}"
