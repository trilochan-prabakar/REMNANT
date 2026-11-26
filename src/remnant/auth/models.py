from dataclasses import dataclass, field
from enum import Enum


class Role(str, Enum):
    USER = "user"
    ADMIN = "admin"
    TENANT_ADMIN = "tenant_admin"


class AccountStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REMOVED = "removed"


@dataclass(frozen=True)
class Principal:
    principal_id: str
    role: Role
    tenant_id: str = "default"
    roles: tuple[Role, ...] = field(default_factory=tuple)
    status: AccountStatus = AccountStatus.ACTIVE

    @property
    def effective_roles(self) -> frozenset[Role]:
        return frozenset((*self.roles, self.role))


@dataclass(frozen=True)
class Resource:
    resource_id: str
    tenant_id: str
    owner_id: str


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    principal_id: str
    resource_id: str
    reason: str
    tenant_id: str | None = None
    action: str = "read"
    policy_version: int = 0
