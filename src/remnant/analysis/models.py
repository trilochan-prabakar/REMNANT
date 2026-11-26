"""Structured, body-safe results for cache/origin response comparisons."""

from dataclasses import dataclass
from enum import Enum


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
