from remnant.auth.models import (
    AuthorizationDecision,
    Principal,
    Role,
)


class AuthorizationPolicy:
    """Independent authorization policy for protected resources."""

    def __init__(self) -> None:
        self._grants: set[tuple[str, str]] = set()

    def grant(self, principal_id: str, resource_id: str) -> None:
        self._validate(principal_id, resource_id)
        self._grants.add((principal_id, resource_id))

    def revoke(self, principal_id: str, resource_id: str) -> None:
        self._validate(principal_id, resource_id)
        self._grants.discard((principal_id, resource_id))

    def is_allowed(
        self,
        principal: Principal,
        resource_id: str,
    ) -> AuthorizationDecision:
        self._validate(principal.principal_id, resource_id)

        if principal.role == Role.ADMIN:
            return AuthorizationDecision(
                allowed=True,
                principal_id=principal.principal_id,
                resource_id=resource_id,
                reason="administrator_access",
            )

        allowed = (
            principal.principal_id,
            resource_id,
        ) in self._grants

        return AuthorizationDecision(
            allowed=allowed,
            principal_id=principal.principal_id,
            resource_id=resource_id,
            reason=(
                "explicit_grant"
                if allowed
                else "no_active_grant"
            ),
        )

    @staticmethod
    def _validate(principal_id: str, resource_id: str) -> None:
        if not principal_id.strip():
            raise ValueError("principal_id cannot be empty")

        if not resource_id.strip():
            raise ValueError("resource_id cannot be empty")
