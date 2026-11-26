from remnant.auth.identities import IdentityRegistry
from remnant.auth.models import (
    AccountStatus,
    AuthorizationDecision,
    Principal,
    Resource,
    Role,
)
from remnant.auth.ownership import ResourceRegistry
from remnant.auth.permissions import PermissionStore
from remnant.auth.tenancy import TenantRegistry


class AuthorizationPolicy:
    """V1 authorization policy retained unchanged for compatibility."""

    def __init__(self) -> None:
        self._grants: set[tuple[str, str]] = set()

    def grant(self, principal_id: str, resource_id: str) -> None:
        self._validate(principal_id, resource_id)
        self._grants.add((principal_id, resource_id))

    def revoke(self, principal_id: str, resource_id: str) -> None:
        self._validate(principal_id, resource_id)
        self._grants.discard((principal_id, resource_id))

    def is_allowed(self, principal: Principal, resource_id: str) -> AuthorizationDecision:
        self._validate(principal.principal_id, resource_id)
        if principal.role == Role.ADMIN:
            return AuthorizationDecision(
                allowed=True, principal_id=principal.principal_id,
                resource_id=resource_id, reason="administrator_access",
            )
        allowed = (principal.principal_id, resource_id) in self._grants
        return AuthorizationDecision(
            allowed=allowed, principal_id=principal.principal_id,
            resource_id=resource_id,
            reason="explicit_grant" if allowed else "no_active_grant",
        )

    @staticmethod
    def _validate(principal_id: str, resource_id: str) -> None:
        if not isinstance(principal_id, str) or not principal_id.strip():
            raise ValueError("principal_id cannot be empty")
        if not isinstance(resource_id, str) or not resource_id.strip():
            raise ValueError("resource_id cannot be empty")


class PolicyEngine:
    """V2 default-deny policy engine with tenant isolation and explicit precedence.

    Decision order: known active identity, known active tenant, resource existence,
    tenant boundary, explicit deny, ownership, explicit grant, tenant-admin role.
    V2 administrator roles are tenant-scoped and never bypass tenant isolation.
    """

    OWNER_ACTIONS = frozenset({"read", "update", "delete"})
    TENANT_ADMIN_ACTIONS = frozenset({"read", "create", "update", "delete", "manage"})

    def __init__(
        self,
        identities: IdentityRegistry,
        resources: ResourceRegistry,
        permissions: PermissionStore,
        tenants: TenantRegistry,
    ) -> None:
        self.identities = identities
        self.resources = resources
        self.permissions = permissions
        self.tenants = tenants

    @property
    def version(self) -> int:
        return (self.identities.version + self.resources.version +
                self.permissions.version + self.tenants.version)

    def evaluate(
        self,
        principal: Principal | str,
        resource_id: str,
        action: str = "read",
    ) -> AuthorizationDecision:
        principal_id = principal if isinstance(principal, str) else principal.principal_id
        if not isinstance(principal_id, str) or not principal_id.strip():
            raise ValueError("principal_id cannot be empty")
        if not isinstance(resource_id, str) or not resource_id.strip():
            raise ValueError("resource_id cannot be empty")
        if not isinstance(action, str) or not action.strip():
            raise ValueError("action cannot be empty")

        identity = self.identities.get(principal_id)
        if identity is None:
            return self._decision(False, principal_id, resource_id, "unknown_principal", None, action)
        if identity.status is AccountStatus.SUSPENDED:
            return self._decision(False, principal_id, resource_id, "identity_suspended", identity.tenant_id, action)
        if identity.status is AccountStatus.REMOVED:
            return self._decision(False, principal_id, resource_id, "identity_removed", identity.tenant_id, action)

        tenant = self.tenants.get(identity.tenant_id)
        if tenant is None:
            return self._decision(False, principal_id, resource_id, "unknown_tenant", identity.tenant_id, action)
        if not tenant.active:
            return self._decision(False, principal_id, resource_id, "tenant_inactive", identity.tenant_id, action)

        resource = self.resources.get(resource_id)
        if resource is None:
            return self._decision(False, principal_id, resource_id, "unknown_resource", identity.tenant_id, action)
        if identity.tenant_id != resource.tenant_id:
            return self._decision(False, principal_id, resource_id, "tenant_boundary", identity.tenant_id, action)

        if self.permissions.is_denied(principal_id, resource_id, action):
            return self._decision(False, principal_id, resource_id, "explicit_denial", identity.tenant_id, action)
        if resource.owner_id == principal_id and action in self.OWNER_ACTIONS:
            return self._decision(True, principal_id, resource_id, "resource_owner", identity.tenant_id, action)
        if self.permissions.is_granted(principal_id, resource_id, action):
            return self._decision(True, principal_id, resource_id, "explicit_grant", identity.tenant_id, action)
        if Role.TENANT_ADMIN in identity.effective_roles or Role.ADMIN in identity.effective_roles:
            if action in self.TENANT_ADMIN_ACTIONS:
                return self._decision(True, principal_id, resource_id, "tenant_administrator", identity.tenant_id, action)
        return self._decision(False, principal_id, resource_id, "no_active_permission", identity.tenant_id, action)

    def _decision(
        self, allowed: bool, principal_id: str, resource_id: str,
        reason: str, tenant_id: str | None, action: str,
    ) -> AuthorizationDecision:
        return AuthorizationDecision(
            allowed=allowed, principal_id=principal_id, resource_id=resource_id,
            reason=reason, tenant_id=tenant_id, action=action,
            policy_version=self.version,
        )
