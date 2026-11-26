"""Contracts for independent protected-origin requests."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class OriginResponse:
    status_code: int
    headers: tuple[tuple[str, str], ...]
    body: bytes


@runtime_checkable
class OriginAdapter(Protocol):
    """Async origin boundary.

    CacheReplayExperiment invokes every request for one run on the same event
    loop, then closes that loop. Implementations may reuse async resources
    within a run, but must not retain loop-bound resources across separate
    calls to the experiment's synchronous run() method.
    """

    async def get_protected(
        self, resource_id: str, *, principal_id: str
    ) -> OriginResponse: ...
