from datetime import datetime, timezone

from remnant.v3.cache_analysis import Cacheability, analyze_response


def test_s_maxage_takes_precedence_over_max_age():
    result = analyze_response(
        200, {"Cache-Control": "max-age=5, s-maxage=90"},
        now=datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc),
    )
    assert result.cacheability is Cacheability.CACHEABLE
    assert result.freshness_lifetime_seconds == 90


def test_age_and_date_contribute_to_current_age():
    result = analyze_response(
        200,
        {
            "Cache-Control": "max-age=60",
            "Date": "Thu, 26 Nov 2026 12:00:00 GMT",
            "Age": "20",
        },
        now=datetime(2026, 11, 26, 12, 0, 30, tzinfo=timezone.utc),
    )
    assert result.current_age_seconds == 30
    assert result.freshness_remaining_seconds == 30
    assert result.is_fresh is True


def test_expired_response_is_not_fresh():
    result = analyze_response(
        200,
        {
            "Cache-Control": "max-age=60",
            "Date": "Thu, 26 Nov 2026 12:00:00 GMT",
        },
        now=datetime(2026, 11, 26, 12, 2, tzinfo=timezone.utc),
    )
    assert result.is_fresh is False
    assert result.freshness_remaining_seconds == 0


def test_missing_age_and_date_leave_freshness_unknown():
    result = analyze_response(200, {"Cache-Control": "max-age=60"})
    assert result.current_age_seconds is None
    assert result.is_fresh is None


def test_no_cache_requires_revalidation_even_if_freshness_lifetime_exists():
    result = analyze_response(
        200, {"Cache-Control": "no-cache, max-age=60"},
        now=datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc),
    )
    assert result.cacheability is Cacheability.REQUIRES_REVALIDATION
    assert result.is_fresh is False
