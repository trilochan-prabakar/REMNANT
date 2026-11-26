from remnant.scenarios.models import Scenario


class ScenarioValidationError(ValueError):
    """Raised when a scenario is structurally valid but semantically unsafe."""


class ScenarioValidator:
    SUPPORTED_SCHEMA_VERSION = 1
    ACTIONS = frozenset({
        "grant_permission", "deny_permission", "revoke_permission",
        "clear_denial", "suspend_identity", "reactivate_identity",
        "remove_identity", "request_origin", "prime_cache", "request_cache",
    })
    ALLOWED_ROLES = frozenset({"user", "admin", "tenant_admin"})

    def validate(self, scenario: Scenario) -> None:
        if scenario.schema_version != self.SUPPORTED_SCHEMA_VERSION:
            raise ScenarioValidationError(
                f"unsupported schema_version: {scenario.schema_version}"
            )
        self._unique(scenario.tenants, "tenant")
        self._unique((item.identity_id for item in scenario.identities), "identity")
        self._unique((item.resource_id for item in scenario.resources), "resource")
        if not scenario.scenario_id.strip() or not scenario.name.strip():
            raise ScenarioValidationError("scenario id and name are required")
        tenant_ids = set(scenario.tenants)
        identities = {item.identity_id: item for item in scenario.identities}
        resources = {item.resource_id: item for item in scenario.resources}

        if not tenant_ids:
            raise ScenarioValidationError("at least one tenant is required")
        for identity in scenario.identities:
            if identity.tenant_id not in tenant_ids:
                raise ScenarioValidationError(
                    f"identity '{identity.identity_id}' references unknown tenant '{identity.tenant_id}'"
                )
            if not identity.roles or any(role not in self.ALLOWED_ROLES for role in identity.roles):
                raise ScenarioValidationError(f"identity '{identity.identity_id}' has invalid roles")
        for resource in scenario.resources:
            if resource.tenant_id not in tenant_ids:
                raise ScenarioValidationError(
                    f"resource '{resource.resource_id}' references unknown tenant '{resource.tenant_id}'"
                )
            owner = identities.get(resource.owner_id)
            if owner is None:
                raise ScenarioValidationError(
                    f"resource '{resource.resource_id}' references unknown owner '{resource.owner_id}'"
                )
            if owner.tenant_id != resource.tenant_id:
                raise ScenarioValidationError(
                    f"resource '{resource.resource_id}' owner belongs to another tenant"
                )
        if not scenario.steps:
            raise ScenarioValidationError("scenario must contain at least one step")

        for index, step in enumerate(scenario.steps, start=1):
            if step.action not in self.ACTIONS:
                raise ScenarioValidationError(f"step {index}: unsupported action '{step.action}'")
            if step.action in {"grant_permission", "deny_permission", "revoke_permission",
                               "clear_denial", "request_origin", "prime_cache", "request_cache"}:
                if step.principal not in identities:
                    raise ScenarioValidationError(
                        f"step {index}: unknown principal '{step.principal}'"
                    )
                if step.resource not in resources:
                    raise ScenarioValidationError(
                        f"step {index}: unknown resource '{step.resource}'"
                    )
                if not step.permission.strip():
                    raise ScenarioValidationError(f"step {index}: permission cannot be empty")
            elif step.principal not in identities:
                raise ScenarioValidationError(
                    f"step {index}: unknown principal '{step.principal}'"
                )

    @staticmethod
    def _unique(values, label: str) -> None:
        items = tuple(values)
        if any(not isinstance(value, str) or not value.strip() for value in items):
            raise ScenarioValidationError(f"{label} identifiers cannot be empty")
        if len(items) != len(set(items)):
            raise ScenarioValidationError(f"duplicate {label} identifier")
