import pytest

from remnant.analysis import ComparisonState, compare_responses
from remnant.cache.manager import CachedHTTPResponse
from remnant.cache.models import CacheObservation, CacheObservationStatus
from remnant.origin.protocols import OriginResponse


def _responses(*, origin_body=b"protected:CANARY-1", cache_body=b"protected:CANARY-1",
               origin_status=200, cache_status=200,
               origin_headers=(("Content-Type", "application/json"), ("Cache-Control", "private")),
               cache_headers=(("cache-control", "private"), ("content-type", "application/json"))):
    origin = OriginResponse(origin_status, origin_headers, origin_body)
    cached = CachedHTTPResponse(cache_status, cache_headers, cache_body)
    return origin, CacheObservation(CacheObservationStatus.HIT, response=cached)


def test_identical_responses_match_case_insensitive_selected_headers():
    origin, cache = _responses()
    result = compare_responses(origin, cache, expected_canary=b"CANARY-1")
    assert result.state is ComparisonState.MATCH
    assert result.status_code.state is ComparisonState.MATCH
    assert result.selected_headers.state is ComparisonState.MATCH
    assert result.body_digest.state is ComparisonState.MATCH
    assert result.canary.state is ComparisonState.MATCH
    assert result.canary.origin_value is True
    assert result.canary.cache_value is True


@pytest.mark.parametrize(
    ("kwargs", "dimension"),
    [
        ({"origin_status": 403}, "status_code"),
        ({"origin_headers": (("content-type", "text/plain"),)}, "selected_headers"),
        ({"origin_body": b"origin body"}, "body_digest"),
        ({"cache_body": b"protected without marker"}, "canary"),
    ],
)
def test_meaningful_response_differences_are_reported(kwargs, dimension):
    origin, cache = _responses(**kwargs)
    result = compare_responses(origin, cache, expected_canary=b"CANARY-1")
    assert result.state is ComparisonState.DIFFERENT
    assert getattr(result, dimension).state is ComparisonState.DIFFERENT


def test_unavailable_origin_is_indeterminate():
    _, cache = _responses()
    result = compare_responses(None, cache)
    assert result.state is ComparisonState.INDETERMINATE
    assert result.status_code.state is ComparisonState.INDETERMINATE


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
def test_non_hit_cache_states_are_indeterminate(status):
    origin, _ = _responses()
    result = compare_responses(origin, CacheObservation(status))
    assert result.state is ComparisonState.INDETERMINATE
    assert status.value in result.diagnostic


def test_canary_is_not_checked_when_not_supplied_but_other_dimensions_can_match():
    origin, cache = _responses()
    result = compare_responses(origin, cache)
    assert result.state is ComparisonState.MATCH
    assert result.canary.state is ComparisonState.INDETERMINATE


def test_canary_missing_from_both_responses_is_not_a_match():
    origin, cache = _responses(origin_body=b"no marker", cache_body=b"no marker")
    result = compare_responses(origin, cache, expected_canary=b"CANARY-1")
    assert result.canary.state is ComparisonState.DIFFERENT
    assert result.canary.origin_value is False
    assert result.canary.cache_value is False
    assert result.state is ComparisonState.DIFFERENT


def test_empty_canary_and_empty_header_names_are_rejected():
    origin, cache = _responses()
    with pytest.raises(ValueError, match="expected_canary"):
        compare_responses(origin, cache, expected_canary=b"")
    with pytest.raises(ValueError, match="header names"):
        compare_responses(origin, cache, selected_headers=("content-type", " "))


def test_result_contains_digests_not_response_bodies():
    secret_body = b"highly-sensitive-protected-content-CANARY-1"
    origin, cache = _responses(origin_body=secret_body, cache_body=secret_body)
    result = compare_responses(origin, cache, expected_canary=b"CANARY-1")
    assert secret_body.decode() not in repr(result)
    assert len(result.body_digest.origin_value) == 64
    assert len(result.body_digest.cache_value) == 64
