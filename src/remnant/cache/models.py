"""Typed cache observations used by the REMNANT analysis pipeline."""

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from remnant.cache.manager import CachedHTTPResponse
    from remnant.cache.metadata import CacheMetadata


class CacheObservationStatus(str, Enum):
    """Cache outcomes; uncertainty and infrastructure failures are not misses."""

    HIT = "HIT"
    MISS = "MISS"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"
    BACKEND_ERROR = "BACKEND_ERROR"
    INVALID_METADATA = "INVALID_METADATA"


@dataclass(frozen=True)
class CacheObservation:
    """A cache lookup result with an explicit outcome and optional evidence."""

    status: CacheObservationStatus
    response: Optional["CachedHTTPResponse"] = None
    metadata: Optional["CacheMetadata"] = None
    diagnostic: Optional[str] = None

    def __post_init__(self) -> None:
        if self.status is CacheObservationStatus.HIT and self.response is None:
            raise ValueError("a HIT observation requires a response")
        if self.status is not CacheObservationStatus.HIT and self.response is not None:
            raise ValueError("only a HIT observation may contain a response")
        if self.diagnostic is not None and not self.diagnostic.strip():
            raise ValueError("diagnostic must be non-empty when provided")
