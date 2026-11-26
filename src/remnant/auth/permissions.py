class PermissionStore:
    """Stores explicit allow and deny rules as (principal, resource, action)."""

    def __init__(self) -> None:
        self._grants: set[tuple[str, str, str]] = set()
        self._denials: set[tuple[str, str, str]] = set()
        self._version = 0

    @property
    def version(self) -> int:
        return self._version

    def grant(self, principal_id: str, resource_id: str, action: str = "read") -> None:
        key = self._key(principal_id, resource_id, action)
        changed = key not in self._grants or key in self._denials
        self._grants.add(key)
        self._denials.discard(key)
        if changed:
            self._version += 1

    def deny(self, principal_id: str, resource_id: str, action: str = "read") -> None:
        key = self._key(principal_id, resource_id, action)
        changed = key not in self._denials or key in self._grants
        self._denials.add(key)
        self._grants.discard(key)
        if changed:
            self._version += 1

    def revoke(self, principal_id: str, resource_id: str, action: str = "read") -> None:
        key = self._key(principal_id, resource_id, action)
        if key in self._grants:
            self._grants.remove(key)
            self._version += 1

    def clear_denial(self, principal_id: str, resource_id: str, action: str = "read") -> None:
        key = self._key(principal_id, resource_id, action)
        if key in self._denials:
            self._denials.remove(key)
            self._version += 1

    def is_granted(self, principal_id: str, resource_id: str, action: str) -> bool:
        return self._key(principal_id, resource_id, action) in self._grants

    def is_denied(self, principal_id: str, resource_id: str, action: str) -> bool:
        return self._key(principal_id, resource_id, action) in self._denials

    @staticmethod
    def _key(principal_id: str, resource_id: str, action: str) -> tuple[str, str, str]:
        values = (principal_id, resource_id, action)
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("principal_id, resource_id and action must be non-empty")
        return values
