from remnant.v3.cache_analysis import Cacheability, analyze_response


def test_no_store_overrides_public_for_shared_authorized_response():
    result = analyze_response(
        200, {"Cache-Control": "public, max-age=60, no-store"},
        request_had_authorization=True,
    )
    assert result.shared_cache_may_reuse_authorized_response is False


def test_private_overrides_public_for_shared_authorized_response():
    result = analyze_response(
        200, {"Cache-Control": "public, private, max-age=60"},
        request_had_authorization=True,
    )
    assert result.shared_cache_may_reuse_authorized_response is False


def test_s_maxage_is_used_for_shared_cache_freshness():
    result = analyze_response(200, {"Cache-Control": "max-age=0, s-maxage=120"})
    assert result.cacheability is Cacheability.CACHEABLE


def test_unquoted_comma_in_cache_extension_is_split():
    result = analyze_response(200, {"Cache-Control": "max-age=30, public"})
    assert result.directives == (("max-age", "30"), ("public", None))
