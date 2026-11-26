from datetime import datetime, timezone

import pytest

from remnant.v3.cache_analysis import Cacheability, CacheState, analyze_response


def test_no_store_is_not_cacheable():
    result = analyze_response(200, {"Cache-Control": "private, no-store"})
    assert result.cacheability is Cacheability.NOT_CACHEABLE


def test_private_response_is_not_shared_cacheable():
    result = analyze_response(200, {"Cache-Control": "private, max-age=300"})
    assert result.cacheability is Cacheability.PRIVATE_ONLY


def test_no_cache_means_revalidate_not_do_not_store():
    result = analyze_response(200, {"Cache-Control": "no-cache"})
    assert result.cacheability is Cacheability.REQUIRES_REVALIDATION


def test_max_age_establishes_freshness():
    result = analyze_response(200, {"Cache-Control": "public, max-age=60"})
    assert result.cacheability is Cacheability.CACHEABLE


def test_expires_is_compared_with_date():
    result = analyze_response(
        200,
        {
            "Date": "Wed, 25 Nov 2026 12:00:00 GMT",
            "Expires": "Wed, 25 Nov 2026 12:05:00 GMT",
        },
        now=datetime(2026, 11, 25, 12, 1, tzinfo=timezone.utc),
    )
    assert result.cacheability is Cacheability.CACHEABLE


def test_vary_star_prevents_reuse():
    result = analyze_response(200, {"Cache-Control": "max-age=60", "Vary": "*"})
    assert result.cacheability is Cacheability.NOT_CACHEABLE


def test_authorization_request_requires_explicit_shared_cache_directive():
    blocked = analyze_response(
        200, {"Cache-Control": "max-age=60"}, request_had_authorization=True
    )
    allowed = analyze_response(
        200, {"Cache-Control": "public, max-age=60"}, request_had_authorization=True
    )
    assert blocked.shared_cache_may_reuse_authorized_response is False
    assert allowed.shared_cache_may_reuse_authorized_response is True


def test_set_cookie_is_reported_without_assuming_not_cacheable():
    result = analyze_response(
        200, {"Cache-Control": "public, max-age=60", "Set-Cookie": "session=secret"}
    )
    assert result.cacheability is Cacheability.CACHEABLE
    assert result.has_set_cookie is True
    assert any("Set-Cookie" in reason for reason in result.reasons)


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"X-Cache": "HIT"}, CacheState.HIT),
        ({"Cache-Status": "ExampleCache; hit"}, CacheState.HIT),
        ({"X-Cache": "MISS"}, CacheState.MISS),
        ({"Cache-Status": "ExampleCache; fwd=uri-miss"}, CacheState.MISS),
        ({"CF-Cache-Status": "STALE"}, CacheState.STALE),
        ({"X-Cache-Status": "BYPASS"}, CacheState.BYPASS),
        ({}, CacheState.UNKNOWN),
    ],
)
def test_observed_cache_state(headers, expected):
    assert analyze_response(200, headers).cache_state is expected


def test_cache_control_parser_keeps_commas_inside_quoted_value():
    result = analyze_response(
        200, {"Cache-Control": 'max-age=30, extension="a,b", public'}
    )
    assert result.directives == (
        ("max-age", "30"),
        ("extension", "a,b"),
        ("public", None),
    )


def test_invalid_age_is_ignored():
    result = analyze_response(200, {"Age": "-5"})
    assert result.age_seconds is None
