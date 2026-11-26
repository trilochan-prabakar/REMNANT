"""HTTP response cache analysis for controlled REMNANT V3 experiments.

This module is side-effect free: it analyses response metadata supplied by an
experiment runner and never sends requests or declares a security finding.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from enum import Enum
from typing import Mapping


class Cacheability(str, Enum):
    NOT_CACHEABLE = "not_cacheable"
    PRIVATE_ONLY = "private_only"
    REQUIRES_REVALIDATION = "requires_revalidation"
    CACHEABLE = "cacheable"
    UNSPECIFIED = "unspecified"


class CacheState(str, Enum):
    HIT = "hit"
    MISS = "miss"
    STALE = "stale"
    BYPASS = "bypass"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CacheAnalysis:
    status_code: int
    cacheability: Cacheability
    cache_state: CacheState
    directives: tuple[tuple[str, str | None], ...]
    vary: tuple[str, ...]
    age_seconds: int | None
    has_set_cookie: bool
    request_had_authorization: bool
    shared_cache_may_reuse_authorized_response: bool | None
    reasons: tuple[str, ...]


def _headers_lower(headers: Mapping[str, str]) -> dict[str, str]:
    return {str(key).strip().lower(): str(value).strip() for key, value in headers.items()}


def _split_directives(value: str) -> tuple[tuple[str, str | None], ...]:
    """Split Cache-Control without splitting commas inside quoted values."""
    parts: list[str] = []
    current: list[str] = []
    quoted = False
    escaped = False
    for char in value:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\" and quoted:
            current.append(char)
            escaped = True
        elif char == '"':
            current.append(char)
            quoted = not quoted
        elif char == "," and not quoted:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    if current:
        parts.append("".join(current))

    parsed: list[tuple[str, str | None]] = []
    for part in parts:
        name, separator, raw_value = part.strip().partition("=")
        if not name:
            continue
        value_part = raw_value.strip() if separator else None
        if value_part and len(value_part) >= 2 and value_part[0] == value_part[-1] == '"':
            value_part = value_part[1:-1]
        parsed.append((name.lower(), value_part))
    return tuple(parsed)


def _date_value(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _nonnegative_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value, 10)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _cache_state(headers: Mapping[str, str]) -> CacheState:
    standard = headers.get("cache-status", "")
    if standard:
        # RFC 9211 Cache-Status uses key/value parameters, e.g. ExampleCache; hit
        # and ExampleCache; fwd=uri-miss. Parse each member conservatively.
        for member in standard.lower().split(","):
            tokens = member.replace(";", " ").split()
            if "hit" in tokens:
                return CacheState.HIT
            if any(token.startswith("fwd=stale") for token in tokens):
                return CacheState.STALE
            if any(token.startswith("fwd=bypass") for token in tokens):
                return CacheState.BYPASS
            if any(token.startswith("fwd=miss") or token.startswith("fwd=uri-miss") for token in tokens):
                return CacheState.MISS

    for name in ("x-cache", "x-cache-status", "cf-cache-status", "x-proxy-cache"):
        value = headers.get(name, "").lower()
        if not value:
            continue
        tokens = {token.strip().split(" ", 1)[0] for token in value.replace(";", ",").split(",")}
        if any(token in {"hit", "tcp_hit", "cached"} for token in tokens):
            return CacheState.HIT
        if any(token in {"stale", "updating"} for token in tokens):
            return CacheState.STALE
        if any(token in {"bypass", "dynamically_generated", "none"} for token in tokens):
            return CacheState.BYPASS
        if any(token in {"miss", "tcp_miss", "expired"} for token in tokens):
            return CacheState.MISS
    return CacheState.UNKNOWN


def analyze_response(
    status_code: int,
    headers: Mapping[str, str],
    *,
    request_had_authorization: bool = False,
    now: datetime | None = None,
) -> CacheAnalysis:
    """Analyse cache directives and observed cache state.

    RFC 9111 shared-cache restrictions for Authorization requests are reported as
    diagnostics. A directive is not proof that a particular cache obeyed it.
    """
    normalized = _headers_lower(headers)
    directives = _split_directives(normalized.get("cache-control", ""))
    directive_map = {name: value for name, value in directives}
    names = set(directive_map)
    reasons: list[str] = []
    vary = tuple(
        item.strip().lower()
        for item in normalized.get("vary", "").split(",")
        if item.strip()
    )
    age = _nonnegative_int(normalized.get("age"))
    has_set_cookie = "set-cookie" in normalized

    if "no-store" in names:
        cacheability = Cacheability.NOT_CACHEABLE
        reasons.append("Cache-Control: no-store prohibits storing the response.")
    elif "*" in vary:
        cacheability = Cacheability.NOT_CACHEABLE
        reasons.append("Vary: * makes the response unsuitable for reuse.")
    elif "private" in names:
        cacheability = Cacheability.PRIVATE_ONLY
        reasons.append("Cache-Control: private prohibits shared-cache storage.")
    elif "no-cache" in names:
        cacheability = Cacheability.REQUIRES_REVALIDATION
        reasons.append("Cache-Control: no-cache permits storage but requires validation before reuse.")
    else:
        shared_lifetime = _nonnegative_int(directive_map.get("s-maxage"))
        ordinary_lifetime = _nonnegative_int(directive_map.get("max-age"))
        lifetime = shared_lifetime if shared_lifetime is not None else ordinary_lifetime
        current = now or datetime.now(timezone.utc)
        expires = _date_value(normalized.get("expires"))
        date = _date_value(normalized.get("date"))
        if lifetime is not None:
            cacheability = Cacheability.CACHEABLE
            reasons.append("An explicit max-age or s-maxage freshness lifetime is present.")
        elif expires is not None and expires > (date or current):
            cacheability = Cacheability.CACHEABLE
            reasons.append("Expires declares a future freshness time.")
        else:
            cacheability = Cacheability.UNSPECIFIED
            reasons.append("No explicit freshness lifetime establishes cacheability.")

    shared_reuse: bool | None = None
    if request_had_authorization:
        # RFC 9111 §3.5 permits shared-cache reuse of an Authorization response
        # only under specified response directives. no-store/private still win.
        allowed_directives = {"public", "s-maxage", "must-revalidate"}
        shared_reuse = (
            cacheability not in {Cacheability.NOT_CACHEABLE, Cacheability.PRIVATE_ONLY}
            and bool(names.intersection(allowed_directives))
        )
        if shared_reuse:
            reasons.append(
                "An applicable explicit directive may permit shared-cache reuse for "
                "an Authorization-bearing request; verify freshness and other RFC conditions."
            )
        else:
            reasons.append(
                "No applicable directive permits shared-cache reuse of this "
                "Authorization-bearing response under the observed directives."
            )

    if has_set_cookie:
        reasons.append("Set-Cookie is present; inspect whether sensitive session material is cached.")

    return CacheAnalysis(
        status_code=int(status_code),
        cacheability=cacheability,
        cache_state=_cache_state(normalized),
        directives=directives,
        vary=vary,
        age_seconds=age,
        has_set_cookie=has_set_cookie,
        request_had_authorization=bool(request_had_authorization),
        shared_cache_may_reuse_authorized_response=shared_reuse,
        reasons=tuple(reasons),
    )
