import json

import pytest

from remnant.analysis.oracle import evaluate_observation_finding
from remnant.cache.manager import CachedHTTPResponse
from remnant.cache.models import CacheObservation, CacheObservationStatus


EXPECTED = "remnant-canary-document-1-7b91c2e4"


def _hit(body: bytes) -> CacheObservation:
    return CacheObservation(
        CacheObservationStatus.HIT,
        response=CachedHTTPResponse(200, (("content-type", "application/json"),), body),
    )


def test_v2_oracle_confirms_only_the_complete_three_condition_match():
    result = evaluate_observation_finding(
        origin_status=403,
        observation=_hit(json.dumps({"canary": EXPECTED}).encode()),
        expected_canary=EXPECTED,
    )
    assert result.origin_denies is True
    assert result.cache_hit is True
    assert result.canary_matches is True
    assert result.finding_confirmed is True


def test_v2_oracle_does_not_confirm_when_origin_allows():
    result = evaluate_observation_finding(
        origin_status=200,
        observation=_hit(json.dumps({"canary": EXPECTED}).encode()),
        expected_canary=EXPECTED,
    )
    assert result.cache_hit and result.canary_matches
    assert not result.origin_denies
    assert not result.finding_confirmed


@pytest.mark.parametrize(
    "status",
    [
        CacheObservationStatus.MISS,
        CacheObservationStatus.EXPIRED,
        CacheObservationStatus.UNKNOWN,
        CacheObservationStatus.BACKEND_ERROR,
        CacheObservationStatus.INVALID_METADATA,
    ],
)
def test_v2_oracle_never_confirms_non_hit_cache_states(status):
    result = evaluate_observation_finding(
        origin_status=403,
        observation=CacheObservation(status),
        expected_canary=EXPECTED,
    )
    assert result.origin_denies is True
    assert result.cache_hit is False
    assert result.canary_matches is False
    assert result.finding_confirmed is False


@pytest.mark.parametrize(
    "body",
    [
        b'{"resource_id":"document-1"}',
        b'{"canary":"different"}',
        b'["not-an-object"]',
        b'{malformed json',
    ],
    ids=["missing", "mismatch", "wrong-shape", "malformed"],
)
def test_v2_oracle_rejects_missing_mismatched_or_malformed_canary(body):
    result = evaluate_observation_finding(
        origin_status=403,
        observation=_hit(body),
        expected_canary=EXPECTED,
    )
    assert result.cache_hit is True
    assert result.canary_matches is False
    assert result.finding_confirmed is False


def test_v2_oracle_rejects_unexpected_origin_status():
    result = evaluate_observation_finding(
        origin_status=502,
        observation=_hit(json.dumps({"canary": EXPECTED}).encode()),
        expected_canary=EXPECTED,
    )
    assert result.cache_hit and result.canary_matches
    assert not result.origin_denies
    assert not result.finding_confirmed


def test_v2_oracle_requires_expected_canary():
    with pytest.raises(ValueError, match="expected_canary"):
        evaluate_observation_finding(
            origin_status=403,
            observation=_hit(b'{"canary":"x"}'),
            expected_canary="",
        )
