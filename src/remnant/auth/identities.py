from dataclasses import replace

from remnant.auth.models import AccountStatus, Principal, Role


class IdentityRegistry:
    """In-memory identity registry for deterministic, isolated experiments."""

    def __init__(self) -> None:
        self._identities: dict[str, Principal] = {}
        self._version = 0

    @property
    def version(self) -> int:
        return self._version

    def register(self, principal: Principal) -> Principal:
        if not isinstance(principal, Principal):
            raise TypeError("principal must be a Principal")
        self._validate_id(principal.principal_id, "principal_id")
        self._validate_id(principal.tenant_id, "tenant_id")
        self._validate_roles(principal.roles)
        if not isinstance(principal.role, Role):
            raise ValueError("role must be a supported Role")
        if not isinstance(principal.status, AccountStatus):
            raise ValueError("status must be a supported AccountStatus")
        if principal.principal_id in self._identities:
            raise ValueError(f"identity already exists: {principal.principal_id}")
        if principal.status is not AccountStatus.ACTIVE:
            raise ValueError("new identities must start ACTIVE")
        self._identities[principal.principal_id] = principal
        self._version += 1
        return principal

    def get(self, principal_id: str) -> Principal | None:
        self._validate_id(principal_id, "principal_id")
        return self._identities.get(principal_id)

    def suspend(self, principal_id: str) -> Principal:
        return self._set_status(principal_id, AccountStatus.SUSPENDED)

    def reactivate(self, principal_id: str) -> Principal:
        current = self._require(principal_id)
        if current.status is AccountStatus.REMOVED:
            raise ValueError("removed identities cannot be reactivated")
        return self._set_status(principal_id, AccountStatus.ACTIVE)

    def remove(self, principal_id: str) -> Principal:
        return self._set_status(principal_id, AccountStatus.REMOVED)

    def set_roles(self, principal_id: str, roles: tuple[Role, ...]) -> Principal:
        current = self._require(principal_id)
        self._validate_roles(roles)
        normalized = tuple(dict.fromkeys(roles))
        updated = replace(
            current,
            role=normalized[0] if normalized else Role.USER,
            roles=normalized,
        )
        if updated != current:
            self._identities[principal_id] = updated
            self._version += 1
        return updated

    def list_identities(self) -> tuple[Principal, ...]:
        return tuple(self._identities[key] for key in sorted(self._identities))

    def _set_status(self, principal_id: str, status: AccountStatus) -> Principal:
        current = self._require(principal_id)
        updated = replace(current, status=status)
        if updated != current:
            self._identities[principal_id] = updated
            self._version += 1
        return updated

    def _require(self, principal_id: str) -> Principal:
        principal = self.get(principal_id)
        if principal is None:
            raise KeyError(f"unknown identity: {principal_id}")
        return principal

    @staticmethod
    def _validate_id(value: str, field_name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} cannot be empty")

    @staticmethod
    def _validate_roles(roles: tuple[Role, ...]) -> None:
        if not isinstance(roles, tuple) or any(not isinstance(role, Role) for role in roles):
            raise ValueError("roles must be a tuple of supported Role values")
