"""Versioned, integrity-checked metadata for cached response snapshots."""

import hashlib
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class CacheMetadata:
    """Identity and integrity metadata stored alongside a cached response.

    Timestamps are UTC Unix seconds. The metadata deliberately contains no
    credentials, authorization decisions, or response body contents.
    """

    principal_id: str
    resource_id: str
    response_status: int
    body_sha256: str
    created_at: float
    expires_at: float
    tenant_id: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1 or type(self.schema_version) is not int:
            raise ValueError("unsupported cache metadata schema_version")
        for field_name, value in (
            ("principal_id", self.principal_id),
            ("resource_id", self.resource_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if self.tenant_id is not None and (
            not isinstance(self.tenant_id, str) or not self.tenant_id.strip()
        ):
            raise ValueError("tenant_id must be None or a non-empty string")
        if type(self.response_status) is not int or not 100 <= self.response_status <= 599:
            raise ValueError("response_status must be an HTTP status code")
        if not isinstance(self.body_sha256, str) or not _DIGEST_RE.fullmatch(self.body_sha256):
            raise ValueError("body_sha256 must be a lowercase SHA-256 hex digest")
        if (
            type(self.created_at) not in (int, float)
            or type(self.expires_at) not in (int, float)
            or not math.isfinite(self.created_at)
            or not math.isfinite(self.expires_at)
        ):
            raise ValueError("created_at and expires_at must be finite numeric Unix timestamps")
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be later than created_at")

    @classmethod
    def create(
        cls,
        *,
        principal_id: str,
        resource_id: str,
        response_status: int,
        body: bytes,
        ttl_seconds: int,
        tenant_id: str | None = None,
        now: float | None = None,
    ) -> "CacheMetadata":
        if type(ttl_seconds) is not int or ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be a positive integer")
        if now is None:
            now = datetime.now(timezone.utc).timestamp()
        if type(now) not in (int, float) or not math.isfinite(now):
            raise ValueError("now must be a finite numeric Unix timestamp")
        if not isinstance(body, bytes):
            raise TypeError("body must be bytes")
        return cls(
            principal_id=principal_id,
            resource_id=resource_id,
            tenant_id=tenant_id,
            response_status=response_status,
            body_sha256=hashlib.sha256(body).hexdigest(),
            created_at=float(now),
            expires_at=float(now + ttl_seconds),
        )

    def verify_body(self, body: bytes) -> bool:
        """Return whether body bytes match the stored SHA-256 digest."""
        return isinstance(body, bytes) and hashlib.sha256(body).hexdigest() == self.body_sha256

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "principal_id": self.principal_id,
            "resource_id": self.resource_id,
            "tenant_id": self.tenant_id,
            "response_status": self.response_status,
            "body_sha256": self.body_sha256,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "CacheMetadata":
        if not isinstance(data, dict):
            raise ValueError("cache metadata must be an object")
        required = {
            "schema_version", "principal_id", "resource_id", "tenant_id",
            "response_status", "body_sha256", "created_at", "expires_at",
        }
        if set(data) != required:
            raise ValueError("cache metadata has missing or unexpected fields")
        return cls(**data)
