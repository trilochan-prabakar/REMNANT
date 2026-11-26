from dataclasses import dataclass


@dataclass(frozen=True)
class Tenant:
    tenant_id: str
    active: bool = True


class TenantRegistry:
    """Explicit tenant registry; unknown or inactive tenants are never trusted."""

    def __init__(self) -> None:
        self._tenants: dict[str, Tenant] = {}
        self._version = 0

    @property
    def version(self) -> int:
        return self._version

    def register(self, tenant: Tenant) -> Tenant:
        if not isinstance(tenant, Tenant):
            raise TypeError("tenant must be a Tenant")
        if not isinstance(tenant.tenant_id, str) or not tenant.tenant_id.strip():
            raise ValueError("tenant_id cannot be empty")
        if type(tenant.active) is not bool:
            raise ValueError("tenant.active must be a boolean")
        if tenant.tenant_id in self._tenants:
            raise ValueError(f"tenant already exists: {tenant.tenant_id}")
        self._tenants[tenant.tenant_id] = tenant
        self._version += 1
        return tenant

    def get(self, tenant_id: str) -> Tenant | None:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id cannot be empty")
        return self._tenants.get(tenant_id)

    def set_active(self, tenant_id: str, active: bool) -> Tenant:
        if type(active) is not bool:
            raise ValueError("active must be a boolean")
        tenant = self.get(tenant_id)
        if tenant is None:
            raise KeyError(f"unknown tenant: {tenant_id}")
        updated = Tenant(tenant_id=tenant_id, active=active)
        if updated != tenant:
            self._tenants[tenant_id] = updated
            self._version += 1
        return updated
