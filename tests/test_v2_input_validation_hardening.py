import pytest

from remnant.auth import (
    IdentityRegistry,
    Principal,
    Role,
    Tenant,
    TenantRegistry,
)
from remnant.scenarios.models import (
    Scenario,
    ScenarioIdentity,
    ScenarioResource,
    ScenarioStep,
)
from remnant.scenarios.validator import ScenarioValidationError, ScenarioValidator


def test_identity_registry_rejects_untyped_roles_and_status():
    registry = IdentityRegistry()
    with pytest.raises(ValueError, match="role"):
        registry.register(Principal("alice", "admin"))
    with pytest.raises(ValueError, match="roles"):
        registry.register(Principal("bob", Role.USER, roles=("admin",)))


def test_identity_registry_rejects_invalid_role_updates_without_mutation():
    registry = IdentityRegistry()
    registry.register(Principal("alice", Role.USER))
    version = registry.version

    with pytest.raises(ValueError, match="roles"):
        registry.set_roles("alice", ("admin",))

    assert registry.get("alice").effective_roles == {Role.USER}
    assert registry.version == version


@pytest.mark.parametrize("active", ["false", 0, 1, None])
def test_tenant_registry_rejects_non_boolean_active_values(active):
    registry = TenantRegistry()
    with pytest.raises(ValueError, match="boolean"):
        registry.register(Tenant("tenant-a", active=active))
    registry.register(Tenant("tenant-a"))
    with pytest.raises(ValueError, match="boolean"):
        registry.set_active("tenant-a", active)


def _valid_scenario(**overrides):
    values = dict(
        scenario_id="basic",
        name="Basic scenario",
        schema_version=1,
        tenants=("tenant-a",),
        identities=(ScenarioIdentity("alice", "tenant-a"),),
        resources=(ScenarioResource("doc-1", "tenant-a", "alice"),),
        steps=(ScenarioStep("request_origin", "alice", "doc-1"),),
    )
    values.update(overrides)
    return Scenario(**values)


def test_scenario_validator_rejects_boolean_schema_version():
    with pytest.raises(ScenarioValidationError, match="schema_version"):
        ScenarioValidator().validate(_valid_scenario(schema_version=True))


def test_scenario_validator_rejects_unhashable_or_unknown_roles_cleanly():
    scenario = _valid_scenario(
        identities=(ScenarioIdentity("alice", "tenant-a", roles=({"admin": True},)),)
    )
    with pytest.raises(ScenarioValidationError, match="invalid roles"):
        ScenarioValidator().validate(scenario)


def test_scenario_validator_rejects_non_string_step_permission_cleanly():
    scenario = _valid_scenario(
        steps=(ScenarioStep("request_origin", "alice", "doc-1", permission=None),)
    )
    with pytest.raises(ScenarioValidationError, match="permission"):
        ScenarioValidator().validate(scenario)


def test_scenario_validator_rejects_wrong_record_types_cleanly():
    scenario = _valid_scenario(identities=({"id": "alice"},))
    with pytest.raises(ScenarioValidationError, match="ScenarioIdentity"):
        ScenarioValidator().validate(scenario)
