from remnant.scenarios.models import (
    Scenario,
    ScenarioIdentity,
    ScenarioResource,
    ScenarioStep,
)


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
    RESOURCE_ACTIONS = frozenset({
        "grant_permission", "deny_permission", "revoke_permission",
        "clear_denial", "request_origin", "prime_cache", "request_cache",
    })

    def validate(self, scenario: Scenario) -> None:
        if not isinstance(scenario, Scenario):
            raise ScenarioValidationError("scenario must be a Scenario")
        if type(scenario.schema_version) is not int or scenario.schema_version != self.SUPPORTED_SCHEMA_VERSION:
            raise ScenarioValidationError(
                f"unsupported schema_version: {scenario.schema_version}"
            )
        for field_name, value in (("scenario id", scenario.scenario_id), ("scenario name", scenario.name)):
            if not isinstance(value, str) or not value.strip():
                raise ScenarioValidationError(f"{field_name} is required")
        for field_name, value in (
            ("tenants", scenario.tenants),
            ("identities", scenario.identities),
            ("resources", scenario.resources),
            ("steps", scenario.steps),
        ):
            if not isinstance(value, tuple):
                raise ScenarioValidationError(f"{field_name} must be a tuple")

        if any(not isinstance(item, ScenarioIdentity) for item in scenario.identities):
            raise ScenarioValidationError("each identity must be a ScenarioIdentity")
        if any(not isinstance(item, ScenarioResource) for item in scenario.resources):
            raise ScenarioValidationError("each resource must be a ScenarioResource")
        if any(not isinstance(item, ScenarioStep) for item in scenario.steps):
            raise ScenarioValidationError("each step must be a ScenarioStep")

        self._unique(scenario.tenants, "tenant")
        self._unique((item.identity_id for item in scenario.identities), "identity")
        self._unique((item.resource_id for item in scenario.resources), "resource")
        tenant_ids = set(scenario.tenants)
        identities = {item.identity_id: item for item in scenario.identities}
        resources = {item.resource_id: item for item in scenario.resources}

        if not tenant_ids:
            raise ScenarioValidationError("at least one tenant is required")
        for identity in scenario.identities:
            self._identifier(identity.tenant_id, f"identity '{identity.identity_id}' tenant")
            if identity.tenant_id not in tenant_ids:
                raise ScenarioValidationError(
                    f"identity '{identity.identity_id}' references unknown tenant '{identity.tenant_id}'"
                )
            if (
                not isinstance(identity.roles, tuple)
                or not identity.roles
                or any(not isinstance(role, str) or role not in self.ALLOWED_ROLES for role in identity.roles)
            ):
                raise ScenarioValidationError(f"identity '{identity.identity_id}' has invalid roles")
        for resource in scenario.resources:
            self._identifier(resource.tenant_id, f"resource '{resource.resource_id}' tenant")
            self._identifier(resource.owner_id, f"resource '{resource.resource_id}' owner")
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
            if not isinstance(step.action, str) or step.action not in self.ACTIONS:
                raise ScenarioValidationError(f"step {index}: unsupported action '{step.action}'")
            self._identifier(step.principal, f"step {index} principal")
            if step.principal not in identities:
                raise ScenarioValidationError(
                    f"step {index}: unknown principal '{step.principal}'"
                )
            if step.action in self.RESOURCE_ACTIONS:
                self._identifier(step.resource, f"step {index} resource")
                if step.resource not in resources:
                    raise ScenarioValidationError(
                        f"step {index}: unknown resource '{step.resource}'"
                    )
                self._identifier(step.permission, f"step {index} permission")

    @staticmethod
    def _identifier(value, label: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ScenarioValidationError(f"{label} must be a non-empty string")

    @classmethod
    def _unique(cls, values, label: str) -> None:
        items = tuple(values)
        if any(not isinstance(value, str) or not value.strip() for value in items):
            raise ScenarioValidationError(f"{label} identifiers cannot be empty")
        if len(items) != len(set(items)):
            raise ScenarioValidationError(f"duplicate {label} identifier")
