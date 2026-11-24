from dataclasses import dataclass
from enum import Enum


class Role(str, Enum):
    USER = "user"
    ADMIN = "admin"


@dataclass(frozen=True)
class Principal:
    principal_id: str
    role: Role


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    principal_id: str
    resource_id: str
    reason: str
