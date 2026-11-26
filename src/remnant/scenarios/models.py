from dataclasses import dataclass


@dataclass(frozen=True)
class ScenarioIdentity:
    identity_id: str
    tenant_id: str
    roles: tuple[str, ...] = ("user",)


@dataclass(frozen=True)
class ScenarioResource:
    resource_id: str
    tenant_id: str
    owner_id: str


@dataclass(frozen=True)
class ScenarioStep:
    action: str
    principal: str | None = None
    resource: str | None = None
    permission: str = "read"


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    name: str
    schema_version: int
    tenants: tuple[str, ...]
    identities: tuple[ScenarioIdentity, ...]
    resources: tuple[ScenarioResource, ...]
    steps: tuple[ScenarioStep, ...]
