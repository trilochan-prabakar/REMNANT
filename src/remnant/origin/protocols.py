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
    async def get_protected(
        self, resource_id: str, *, principal_id: str
    ) -> OriginResponse: ...
