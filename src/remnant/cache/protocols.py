"""Storage-only cache adapter contract."""

from typing import Optional, Protocol, runtime_checkable

from remnant.cache.manager import CachedHTTPResponse
from remnant.cache.metadata import CacheMetadata
from remnant.cache.models import CacheObservation


@runtime_checkable
class CacheAdapter(Protocol):
    """Minimal cache contract; implementations must not make auth decisions."""

    def store(
        self,
        key: str,
        response: CachedHTTPResponse,
        *,
        ttl_seconds: int,
        metadata: Optional[CacheMetadata] = None,
    ) -> None: ...

    def lookup(self, key: str): ...

    def observe(self, key: str, *, now: Optional[float] = None) -> CacheObservation: ...

    def delete(self, key: str) -> bool: ...
