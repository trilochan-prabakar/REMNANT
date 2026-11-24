"""Controlled cache and origin authorization replay experiment."""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote
from uuid import uuid4

import httpx
from fastapi import FastAPI

from remnant.api import app as app_module
from remnant.api.app import create_protected_origin_app
from remnant.auth.models import Principal, Role
from remnant.auth.policy import AuthorizationPolicy
from remnant.cache.manager import (
    CacheStatus,
    CachedHTTPResponse,
    RedisCacheManager,
)


@dataclass(frozen=True)
class FindingOracle:
    origin_denies: bool
    cache_hit: bool
    canary_matches: bool
    finding_confirmed: bool


@dataclass(frozen=True)
class ExperimentResult:
    experiment_id: str
    principal_id: str
    resource_id: str
    initial_authorization_status: int
    cache_prime_status: CacheStatus
    cache_primed: bool
    cached_canary: Optional[str]
    permission_revoked: bool
    origin_status_after_revocation: int
    cache_status: CacheStatus
    canary_match: bool
    oracle_origin_denies: bool
    oracle_cache_hit: bool
    oracle_canary_matches: bool
    finding_status: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


def evaluate_finding(
    *,
    origin_status: int,
    cache_status: CacheStatus,
    response_body: Optional[bytes],
    expected_canary: str,
) -> FindingOracle:
    """Evaluate the exact three-condition REMNANT finding oracle."""
    origin_denies = origin_status == 403
    cache_hit = cache_status is CacheStatus.HIT
    canary_matches = False
    if cache_hit and response_body is not None:
        try:
            cached_data = json.loads(response_body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            cached_data = None
        canary_matches = (
            isinstance(cached_data, dict)
            and cached_data.get("canary") == expected_canary
        )
    return FindingOracle(
        origin_denies=origin_denies,
        cache_hit=cache_hit,
        canary_matches=canary_matches,
        finding_confirmed=origin_denies and cache_hit and canary_matches,
    )


class CacheReplayExperiment:
    """Compose an independent protected origin with Redis response caching."""

    def __init__(
        self,
        *,
        cache: RedisCacheManager,
        policy: Optional[AuthorizationPolicy] = None,
        origin_app: Optional[FastAPI] = None,
    ) -> None:
        self._cache = cache
        if origin_app is None:
            self._policy = policy if policy is not None else AuthorizationPolicy()
            self._origin_app = create_protected_origin_app(self._policy)
        else:
            origin_policy = getattr(
                origin_app.state,
                "authorization_policy",
                app_module.authorization_policy,
            )
            if policy is not None and policy is not origin_policy:
                raise ValueError(
                    "experiment and origin must use the same AuthorizationPolicy"
                )
            self._policy = origin_policy
            self._origin_app = origin_app

    def run(
        self,
        principal_id: str,
        resource_id: str,
        *,
        ttl_seconds: int = 60,
    ) -> ExperimentResult:
        if not principal_id.strip() or not resource_id.strip():
            raise ValueError("principal_id and resource_id must not be empty")
        if resource_id not in app_module.PROTECTED_RESOURCES:
            raise ValueError(f"unknown protected resource: {resource_id}")

        started_at = datetime.now(timezone.utc).isoformat()
        experiment_id = uuid4().hex
        principal = Principal(principal_id=principal_id, role=Role.USER)
        expected_canary = app_module.PROTECTED_RESOURCES[resource_id]["canary"]
        cache_key = self._cache_key(experiment_id, principal_id, resource_id)

        # A: grant and verify directly against the origin.
        self._policy.grant(principal_id, resource_id)
        initial_response = self._origin_request(principal_id, resource_id)

        # B: use the regular cache path, priming Redis from the authorized origin.
        prime_status, prime_response = self._cached_request(
            principal_id,
            resource_id,
            cache_key,
            ttl_seconds=ttl_seconds,
        )
        prime_canary = self._response_canary(prime_response)
        primed_entry = self._cache.lookup(cache_key)
        cache_primed = (
            prime_status is CacheStatus.MISS
            and prime_response is not None
            and prime_response.status_code == 200
            and prime_canary == expected_canary
            and primed_entry.status is CacheStatus.HIT
            and self._response_canary(primed_entry.response) == expected_canary
        )

        # C: revoke authorization only; leave the cache entry and its TTL intact.
        self._policy.revoke(principal_id, resource_id)
        permission_revoked = not self._policy.is_allowed(principal, resource_id).allowed

        # D: bypass the cache and verify the origin's independent decision.
        bypassed_response = self._origin_request(principal_id, resource_id)

        # E: normal cache path must return the still-live snapshot if it exists.
        normal_status, normal_response = self._cached_request(
            principal_id,
            resource_id,
            cache_key,
            ttl_seconds=ttl_seconds,
        )
        oracle = evaluate_finding(
            origin_status=bypassed_response.status_code,
            cache_status=normal_status,
            response_body=(normal_response.body if normal_response is not None else None),
            expected_canary=expected_canary,
        )
        completed_at = datetime.now(timezone.utc).isoformat()

        return ExperimentResult(
            experiment_id=experiment_id,
            principal_id=principal_id,
            resource_id=resource_id,
            initial_authorization_status=initial_response.status_code,
            cache_prime_status=prime_status,
            cache_primed=cache_primed,
            cached_canary=prime_canary,
            permission_revoked=permission_revoked,
            origin_status_after_revocation=bypassed_response.status_code,
            cache_status=normal_status,
            canary_match=oracle.canary_matches,
            oracle_origin_denies=oracle.origin_denies,
            oracle_cache_hit=oracle.cache_hit,
            oracle_canary_matches=oracle.canary_matches,
            finding_status="CONFIRMED" if oracle.finding_confirmed else "NOT_FOUND",
            started_at=started_at,
            completed_at=completed_at,
        )

    def _origin_request(self, principal_id: str, resource_id: str) -> httpx.Response:
        async def send_request() -> httpx.Response:
            transport = httpx.ASGITransport(app=self._origin_app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://remnant-origin",
            ) as client:
                return await client.get(
                    f"/protected/{quote(resource_id, safe='')}",
                    params={"principal_id": principal_id},
                )

        return asyncio.run(send_request())

    def _cached_request(
        self,
        principal_id: str,
        resource_id: str,
        cache_key: str,
        *,
        ttl_seconds: int,
    ) -> tuple[CacheStatus, Optional[CachedHTTPResponse]]:
        cached = self._cache.lookup(cache_key)
        if cached.status is CacheStatus.HIT:
            return cached.status, cached.response

        response = self._origin_request(principal_id, resource_id)
        snapshot = CachedHTTPResponse(
            status_code=response.status_code,
            headers=tuple(response.headers.multi_items()),
            body=response.content,
        )
        if response.status_code == 200:
            self._cache.store(cache_key, snapshot, ttl_seconds=ttl_seconds)
        return CacheStatus.MISS, snapshot

    @staticmethod
    def _cache_key(
        experiment_id: str,
        principal_id: str,
        resource_id: str,
    ) -> str:
        return (
            f"experiment:{quote(experiment_id, safe='')}:"
            f"protected:{quote(principal_id, safe='')}:"
            f"{quote(resource_id, safe='')}"
        )

    @staticmethod
    def _response_canary(response: Optional[CachedHTTPResponse]) -> Optional[str]:
        if response is None:
            return None
        try:
            data = json.loads(response.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        canary = data.get("canary") if isinstance(data, dict) else None
        return canary if isinstance(canary, str) else None
