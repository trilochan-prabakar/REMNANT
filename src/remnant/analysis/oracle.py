"""Finding validation for explicit V2 cache observations.

The differential analyzer is supporting evidence only. A finding still requires
an independently denied origin, a cache HIT, and the expected canary in that hit.
"""

import json
from dataclasses import dataclass

from remnant.cache.models import CacheObservation, CacheObservationStatus


@dataclass(frozen=True)
class ObservationFindingOracle:
    origin_denies: bool
    cache_hit: bool
    canary_matches: bool
    finding_confirmed: bool


def evaluate_observation_finding(
    *,
    origin_status: int,
    observation: CacheObservation,
    expected_canary: str,
) -> ObservationFindingOracle:
    """Apply the exact three-condition oracle to a V2 cache observation."""
    if not isinstance(expected_canary, str) or not expected_canary:
        raise ValueError("expected_canary must be a non-empty string")

    origin_denies = origin_status == 403
    cache_hit = observation.status is CacheObservationStatus.HIT
    canary_matches = False

    if cache_hit and observation.response is not None:
        try:
            data = json.loads(observation.response.body)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
            data = None
        canary_matches = (
            isinstance(data, dict) and data.get("canary") == expected_canary
        )

    return ObservationFindingOracle(
        origin_denies=origin_denies,
        cache_hit=cache_hit,
        canary_matches=canary_matches,
        finding_confirmed=origin_denies and cache_hit and canary_matches,
    )
