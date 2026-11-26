"""Pure comparison of independently observed origin and cached responses."""

import hashlib
from collections import defaultdict
from collections.abc import Iterable

from remnant.analysis.models import (
    ComparisonState,
    DifferentialComparison,
    DimensionComparison,
)
from remnant.cache.models import CacheObservation, CacheObservationStatus
from remnant.origin.protocols import OriginResponse


DEFAULT_SECURITY_HEADERS = (
    "cache-control",
    "content-security-policy",
    "content-type",
    "etag",
    "strict-transport-security",
    "vary",
    "x-content-type-options",
)


def _selected_headers(
    headers: Iterable[tuple[str, str]], selected: tuple[str, ...]
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    values: dict[str, list[str]] = defaultdict(list)
    selected_set = set(selected)
    for name, value in headers:
        normalized_name = name.strip().lower()
        if normalized_name in selected_set:
            values[normalized_name].append(value.strip())
    return tuple(
        (name, tuple(sorted(values.get(name, ()))))
        for name in selected
    )


def _dimension(equal: bool, origin_value=None, cache_value=None) -> DimensionComparison:
    return DimensionComparison(
        ComparisonState.MATCH if equal else ComparisonState.DIFFERENT,
        origin_value,
        cache_value,
    )


def compare_responses(
    origin: OriginResponse | None,
    cache: CacheObservation,
    *,
    expected_canary: bytes | None = None,
    selected_headers: Iterable[str] = DEFAULT_SECURITY_HEADERS,
) -> DifferentialComparison:
    """Compare response snapshots without retaining or returning their bodies.

    Missing origin evidence and any non-HIT cache state are indeterminate, not
    ordinary response differences. This function does not make finding decisions.
    """
    names = tuple(sorted({name.strip().lower() for name in selected_headers}))
    if any(not name for name in names):
        raise ValueError("selected header names must be non-empty")
    if expected_canary is not None and (
        not isinstance(expected_canary, bytes) or not expected_canary
    ):
        raise ValueError("expected_canary must be non-empty bytes when provided")

    empty = DimensionComparison(ComparisonState.INDETERMINATE)
    if origin is None:
        return DifferentialComparison(
            ComparisonState.INDETERMINATE, empty, empty, empty, empty, names,
            "origin response is unavailable",
        )
    if cache.status is not CacheObservationStatus.HIT or cache.response is None:
        return DifferentialComparison(
            ComparisonState.INDETERMINATE, empty, empty, empty, empty, names,
            f"cache observation is {cache.status.value}",
        )

    cached = cache.response
    status = _dimension(
        origin.status_code == cached.status_code,
        origin.status_code,
        cached.status_code,
    )
    origin_headers = _selected_headers(origin.headers, names)
    cached_headers = _selected_headers(cached.headers, names)
    headers = _dimension(origin_headers == cached_headers)
    origin_digest = hashlib.sha256(origin.body).hexdigest()
    cache_digest = hashlib.sha256(cached.body).hexdigest()
    body = _dimension(origin_digest == cache_digest, origin_digest, cache_digest)

    if expected_canary is None:
        canary = DimensionComparison(ComparisonState.INDETERMINATE)
    else:
        origin_has = expected_canary in origin.body
        cache_has = expected_canary in cached.body
        canary = _dimension(origin_has == cache_has, origin_has, cache_has)

    dimensions = (status, headers, body)
    evaluated = dimensions + ((canary,) if expected_canary is not None else ())
    if any(item.state is ComparisonState.DIFFERENT for item in evaluated):
        overall = ComparisonState.DIFFERENT
    elif any(item.state is ComparisonState.INDETERMINATE for item in evaluated):
        overall = ComparisonState.INDETERMINATE
    else:
        overall = ComparisonState.MATCH

    return DifferentialComparison(
        overall, status, headers, body, canary, names
    )
