"""Strict identity-isolation oracle for controlled cache experiments."""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum


class IsolationStatus(str, Enum):
    CONFIRMED = "confirmed"
    NOT_CONFIRMED = "not_confirmed"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True)
class IdentityIsolationResult:
    status: IsolationStatus
    requester_id: str
    owner_id: str
    origin_status: int
    proxy_status: int | None
    cache_hit: bool
    foreign_canary_match: bool
    reason: str


def evaluate_identity_isolation(
    *,
    requester_id: str,
    owner_id: str,
    origin_status: int,
    proxy_status: int | None,
    proxy_cache_state: str,
    proxy_body: bytes | None,
    expected_owner_canary: str,
) -> IdentityIsolationResult:
    """Confirm only if the requester is denied at origin but receives the owner's cached body."""
    for name, value in (
        ("requester_id", requester_id), ("owner_id", owner_id),
        ("expected_owner_canary", expected_owner_canary),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
    if requester_id == owner_id:
        raise ValueError("identity-isolation requires distinct requester and owner identities")
    if type(origin_status) is not int or not 100 <= origin_status <= 599:
        raise ValueError("origin_status must be an HTTP status")
    if proxy_status is not None and (type(proxy_status) is not int or not 100 <= proxy_status <= 599):
        raise ValueError("proxy_status must be an HTTP status or None")
    if proxy_cache_state not in {"hit", "miss", "stale", "bypass", "unknown"}:
        raise ValueError("unsupported proxy_cache_state")
    if proxy_body is not None and not isinstance(proxy_body, bytes):
        raise TypeError("proxy_body must be bytes or None")

    if proxy_status is None or proxy_body is None or proxy_cache_state == "unknown":
        return IdentityIsolationResult(
            IsolationStatus.INDETERMINATE, requester_id, owner_id, origin_status,
            proxy_status, proxy_cache_state == "hit", False,
            "The proxy observation is incomplete or its cache state is unknown.",
        )
    canary_match = False
    try:
        payload = json.loads(proxy_body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = None
    if isinstance(payload, dict):
        canary_match = payload.get("canary") == expected_owner_canary
    confirmed = (
        origin_status == 403 and proxy_status == 200
        and proxy_cache_state == "hit" and canary_match
    )
    return IdentityIsolationResult(
        IsolationStatus.CONFIRMED if confirmed else IsolationStatus.NOT_CONFIRMED,
        requester_id, owner_id, origin_status, proxy_status,
        proxy_cache_state == "hit", canary_match,
        "The denied requester received the owner's expected representation from a cache HIT."
        if confirmed else "The strict identity-isolation conditions were not all observed.",
    )
