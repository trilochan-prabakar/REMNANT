"""Controlled cache and origin authorization replay experiment."""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote
from uuid import uuid4

from fastapi import FastAPI

from remnant.api import app as app_module
from remnant.api.app import create_protected_origin_app
from remnant.auth.models import Principal, Role
from remnant.auth.policy import AuthorizationPolicy
from remnant.cache.manager import (
    CacheStatus,
    CachedHTTPResponse,
    RedisCacheBackendError,
    RedisCacheManager,
)
from remnant.cache.models import CacheObservation, CacheObservationStatus
from remnant.cache.metadata import CacheMetadata
from remnant.analysis import compare_responses
from remnant.analysis.models import (
    CacheMetadataEvidence,
    ExperimentAnalysisEvidence,
)
from remnant.analysis.oracle import evaluate_observation_finding
from remnant.origin.fastapi import FastAPIOriginAdapter
from remnant.origin.protocols import OriginAdapter, OriginResponse


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
    cache_observation_status: Optional[str] = None
    differential_state: Optional[str] = None
    analysis_evidence: Optional[ExperimentAnalysisEvidence] = None


def evaluate_finding(
    *,
    origin_status: int,
    cache_status: CacheStatus,
    response_body: Optional[bytes],
    expected_canary: str,
) -> FindingOracle:
    """Evaluate the exact V1-compatible three-condition finding oracle.

    Legacy inputs are normalized into the V2 observation model while callers
    retain the original signature and FindingOracle result type.
    """
    if cache_status is CacheStatus.HIT and response_body is not None:
        observation = CacheObservation(
            CacheObservationStatus.HIT,
            response=CachedHTTPResponse(200, (), response_body),
        )
    else:
        observation = CacheObservation(
            CacheObservationStatus.MISS
            if cache_status is CacheStatus.MISS
            else CacheObservationStatus.UNKNOWN
        )

    result = evaluate_observation_finding(
        origin_status=origin_status,
        observation=observation,
        expected_canary=expected_canary,
    )
    return FindingOracle(
        origin_denies=result.origin_denies,
        cache_hit=result.cache_hit,
        canary_matches=result.canary_matches,
        finding_confirmed=result.finding_confirmed,
    )


class CacheReplayExperiment:
    """Compose an independent protected origin with Redis response caching."""

    def __init__(
        self,
        *,
        cache: RedisCacheManager,
        policy: Optional[AuthorizationPolicy] = None,
        origin_app: Optional[FastAPI] = None,
        origin_adapter: Optional[OriginAdapter] = None,
    ) -> None:
        self._cache = cache
        self._active_runner: Optional[asyncio.Runner] = None
        if origin_adapter is not None and origin_app is not None:
            raise ValueError("provide origin_adapter or origin_app, not both")

        if origin_adapter is not None:
            self._policy = policy if policy is not None else AuthorizationPolicy()
            self._origin_adapter = origin_adapter
        elif origin_app is None:
            self._policy = policy if policy is not None else AuthorizationPolicy()
            origin = create_protected_origin_app(self._policy)
            self._origin_adapter = FastAPIOriginAdapter(origin)
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
            self._origin_adapter = FastAPIOriginAdapter(origin_app)

    def run(
        self,
        principal_id: str,
        resource_id: str,
        *,
        ttl_seconds: int = 60,
    ) -> ExperimentResult:
        """Run the synchronous experiment on one event loop.

        All async origin-adapter calls within a run share one loop. The loop
        is closed when the run finishes, so adapters must not retain loop-bound
        resources for reuse across separate calls to run().
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                "CacheReplayExperiment.run() cannot be called from a running event loop"
            )

        if self._active_runner is not None:
            raise RuntimeError("this experiment is already running")
        with asyncio.Runner() as runner:
            self._active_runner = runner
            try:
                return self._run_with_runner(
                    principal_id, resource_id, ttl_seconds=ttl_seconds
                )
            finally:
                self._active_runner = None

    def _run_with_runner(
        self,
        principal_id: str,
        resource_id: str,
        *,
        ttl_seconds: int,
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
        prime_status, prime_response, _prime_observation = self._cached_request(
            principal_id,
            resource_id,
            cache_key,
            ttl_seconds=ttl_seconds,
        )
        prime_canary = self._response_canary(prime_response)
        primed_entry = (
            _prime_observation
            if _prime_observation.status is CacheObservationStatus.BACKEND_ERROR
            else self._cache.observe(cache_key)
        )
        cache_primed = (
            prime_status is CacheStatus.MISS
            and prime_response is not None
            and prime_response.status_code == 200
            and prime_canary == expected_canary
            and primed_entry.status is CacheObservationStatus.HIT
            and primed_entry.metadata is not None
            and primed_entry.metadata.principal_id == principal_id
            and primed_entry.metadata.resource_id == resource_id
            and self._response_canary(primed_entry.response) == expected_canary
        )

        # C: revoke authorization only; leave the cache entry and its TTL intact.
        self._policy.revoke(principal_id, resource_id)
        permission_revoked = not self._policy.is_allowed(principal, resource_id).allowed

        # D: bypass the cache and verify the origin's independent decision.
        bypassed_response = self._origin_request(principal_id, resource_id)

        # E: normal cache path must return the still-live snapshot if it exists.
        normal_status, normal_response, observation = self._cached_request(
            principal_id,
            resource_id,
            cache_key,
            ttl_seconds=ttl_seconds,
        )
        oracle_result = evaluate_observation_finding(
            origin_status=bypassed_response.status_code,
            observation=observation,
            expected_canary=expected_canary,
        )
        oracle = FindingOracle(
            origin_denies=oracle_result.origin_denies,
            cache_hit=oracle_result.cache_hit,
            canary_matches=oracle_result.canary_matches,
            finding_confirmed=oracle_result.finding_confirmed,
        )
        origin_snapshot = OriginResponse(
            status_code=bypassed_response.status_code,
            headers=bypassed_response.headers,
            body=bypassed_response.body,
        )
        differential = compare_responses(
            origin_snapshot,
            observation,
            expected_canary=expected_canary.encode("utf-8"),
        )
        prime_metadata_evidence = self._metadata_evidence(
            primed_entry, principal_id=principal_id, resource_id=resource_id
        )
        replay_metadata_evidence = self._metadata_evidence(
            observation, principal_id=principal_id, resource_id=resource_id
        )
        diagnostic_categories = self._diagnostic_categories(
            primed_entry, observation
        )
        analysis_evidence = ExperimentAnalysisEvidence(
            schema_version=1,
            initial_origin_status=initial_response.status_code,
            cache_prime_observation_status=primed_entry.status.value,
            cache_prime_metadata=prime_metadata_evidence,
            post_revocation_origin_status=bypassed_response.status_code,
            replay_observation_status=observation.status.value,
            replay_metadata=replay_metadata_evidence,
            differential=differential,
            diagnostic_categories=diagnostic_categories,
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
            cache_observation_status=observation.status.value,
            differential_state=differential.state.value,
            analysis_evidence=analysis_evidence,
        )

    @staticmethod
    def _metadata_evidence(
        observation: CacheObservation,
        *,
        principal_id: str,
        resource_id: str,
    ) -> CacheMetadataEvidence:
        metadata = observation.metadata
        if metadata is None:
            return CacheMetadataEvidence(present=False, valid=False)
        response = observation.response
        valid = (
            observation.status is CacheObservationStatus.HIT
            and response is not None
            and metadata.principal_id == principal_id
            and metadata.resource_id == resource_id
            and metadata.response_status == response.status_code
            and metadata.verify_body(response.body)
        )
        return CacheMetadataEvidence(
            present=True,
            valid=valid,
            schema_version=metadata.schema_version,
            principal_id=metadata.principal_id,
            resource_id=metadata.resource_id,
            tenant_id=metadata.tenant_id,
            response_status=metadata.response_status,
            created_at=metadata.created_at,
            expires_at=metadata.expires_at,
            body_sha256=metadata.body_sha256,
        )

    @staticmethod
    def _diagnostic_categories(
        *observations: CacheObservation,
    ) -> tuple[str, ...]:
        categories = set()
        for observation in observations:
            if observation.status is not CacheObservationStatus.HIT:
                categories.add(f"CACHE_{observation.status.value}")
            diagnostic = observation.diagnostic or ""
            if "identity" in diagnostic.lower():
                categories.add("METADATA_IDENTITY_MISMATCH")
            elif diagnostic:
                categories.add("CACHE_DIAGNOSTIC")
        return tuple(sorted(categories))

    def _origin_request(self, principal_id: str, resource_id: str) -> OriginResponse:
        """Call the configured adapter from the synchronous V1 experiment API."""
        if self._active_runner is None:
            raise RuntimeError("origin requests must run inside CacheReplayExperiment.run()")
        return self._active_runner.run(
            self._origin_adapter.get_protected(
                resource_id, principal_id=principal_id
            )
        )

    def _cached_request(
        self,
        principal_id: str,
        resource_id: str,
        cache_key: str,
        *,
        ttl_seconds: int,
    ) -> tuple[CacheStatus, Optional[CachedHTTPResponse], CacheObservation]:
        observation = self._cache.observe(cache_key)
        if observation.status is CacheObservationStatus.HIT:
            metadata = observation.metadata
            if (
                metadata is None
                or metadata.principal_id != principal_id
                or metadata.resource_id != resource_id
            ):
                observation = CacheObservation(
                    CacheObservationStatus.INVALID_METADATA,
                    diagnostic="cache metadata identity does not match the request",
                )
            else:
                return CacheStatus.HIT, observation.response, observation

        if observation.status not in (
            CacheObservationStatus.MISS,
            CacheObservationStatus.EXPIRED,
        ):
            return CacheStatus.MISS, None, observation

        response = self._origin_request(principal_id, resource_id)
        snapshot = CachedHTTPResponse(
            status_code=response.status_code,
            headers=response.headers,
            body=response.body,
        )
        if response.status_code == 200:
            metadata = CacheMetadata.create(
                principal_id=principal_id,
                resource_id=resource_id,
                response_status=snapshot.status_code,
                body=snapshot.body,
                ttl_seconds=ttl_seconds,
            )
            try:
                self._cache.store(
                    cache_key,
                    snapshot,
                    ttl_seconds=ttl_seconds,
                    metadata=metadata,
                )
            except RedisCacheBackendError as exc:
                # A failed write is an explicit backend failure, never a
                # successful prime or an ordinary cache miss. Preserve the
                # authorized origin snapshot for diagnostics, but do not let
                # it enter the replay oracle as a cache HIT.
                return (
                    CacheStatus.MISS,
                    snapshot,
                    CacheObservation(
                        CacheObservationStatus.BACKEND_ERROR,
                        diagnostic="cache backend failed while priming response",
                    ),
                )
        return CacheStatus.MISS, snapshot, CacheObservation(CacheObservationStatus.MISS)

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
