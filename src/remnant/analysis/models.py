"""Structured, body-safe results for cache/origin response comparisons."""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ComparisonState(str, Enum):
    MATCH = "MATCH"
    DIFFERENT = "DIFFERENT"
    INDETERMINATE = "INDETERMINATE"


@dataclass(frozen=True)
class DimensionComparison:
    """Result for one comparison dimension; never stores raw response values."""

    state: ComparisonState
    origin_value: str | bool | None = None
    cache_value: str | bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "origin_value": self.origin_value,
            "cache_value": self.cache_value,
        }


@dataclass(frozen=True)
class DifferentialComparison:
    """Deterministic comparison summary without protected response bodies."""

    state: ComparisonState
    status_code: DimensionComparison
    selected_headers: DimensionComparison
    body_digest: DimensionComparison
    canary: DimensionComparison
    compared_headers: tuple[str, ...]
    diagnostic: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "status_code": self.status_code.to_dict(),
            "selected_headers": self.selected_headers.to_dict(),
            "body_digest": self.body_digest.to_dict(),
            "canary": self.canary.to_dict(),
            "compared_headers": list(self.compared_headers),
            "diagnostic": self.diagnostic,
        }


@dataclass(frozen=True)
class CacheMetadataEvidence:
    """Allow-listed metadata summary; excludes cache keys and response bodies."""

    present: bool
    valid: bool
    schema_version: int | None = None
    principal_id: str | None = None
    resource_id: str | None = None
    tenant_id: str | None = None
    response_status: int | None = None
    created_at: float | None = None
    expires_at: float | None = None
    body_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "present": self.present,
            "valid": self.valid,
            "schema_version": self.schema_version,
            "principal_id": self.principal_id,
            "resource_id": self.resource_id,
            "tenant_id": self.tenant_id,
            "response_status": self.response_status,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "body_sha256": self.body_sha256,
        }


@dataclass(frozen=True)
class ExperimentAnalysisEvidence:
    """Serializable, body-free analysis evidence attached additively to results."""

    schema_version: int
    initial_origin_status: int
    cache_prime_observation_status: str
    cache_prime_metadata: CacheMetadataEvidence
    post_revocation_origin_status: int
    replay_observation_status: str
    replay_metadata: CacheMetadataEvidence
    differential: DifferentialComparison
    diagnostic_categories: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "initial_origin_status": self.initial_origin_status,
            "cache_prime_observation_status": self.cache_prime_observation_status,
            "cache_prime_metadata": self.cache_prime_metadata.to_dict(),
            "post_revocation_origin_status": self.post_revocation_origin_status,
            "replay_observation_status": self.replay_observation_status,
            "replay_metadata": self.replay_metadata.to_dict(),
            "differential": self.differential.to_dict(),
            "diagnostic_categories": list(self.diagnostic_categories),
        }
