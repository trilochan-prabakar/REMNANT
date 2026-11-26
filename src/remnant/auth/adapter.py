"""Bridge the V2 tenant-aware PolicyEngine to the replay experiment contract."""

from remnant.auth.models import Principal
from remnant.auth.policy import PolicyEngine


class PolicyEngineAdapter:
    """Narrow grant/revoke/decision adapter; tenant identity is registry-derived."""

    def __init__(self, engine: PolicyEngine) -> None:
        self.engine = engine

    def tenant_for(self, principal_id: str) -> str | None:
        identity = self.engine.identities.get(principal_id)
        return identity.tenant_id if identity is not None else None

    def grant(self, principal_id: str, resource_id: str) -> None:
        self.engine.permissions.grant(principal_id, resource_id, "read")

    def revoke(self, principal_id: str, resource_id: str) -> None:
        self.engine.permissions.revoke(principal_id, resource_id, "read")

    def is_allowed(self, principal: Principal, resource_id: str):
        # Ignore caller-supplied role/tenant fields; resolve all identity data
        # inside PolicyEngine from the trusted IdentityRegistry.
        return self.engine.evaluate(principal.principal_id, resource_id, "read")
