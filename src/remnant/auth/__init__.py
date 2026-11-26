"""Authorization models and policy engines for REMNANT."""

from remnant.auth.identities import IdentityRegistry
from remnant.auth.adapter import PolicyEngineAdapter
from remnant.auth.models import AccountStatus, AuthorizationDecision, Principal, Resource, Role
from remnant.auth.ownership import ResourceRegistry
from remnant.auth.permissions import PermissionStore
from remnant.auth.policy import AuthorizationPolicy, PolicyEngine
from remnant.auth.tenancy import Tenant, TenantRegistry

__all__ = [
    "AccountStatus", "AuthorizationDecision", "AuthorizationPolicy",
    "IdentityRegistry", "PermissionStore", "PolicyEngine", "PolicyEngineAdapter", "Principal",
    "Resource", "ResourceRegistry", "Role", "Tenant", "TenantRegistry",
]
