import json

import pytest

from remnant.scenarios import ScenarioLoader, ScenarioValidationError, ScenarioValidator
from remnant.scenarios.models import Scenario, ScenarioIdentity, ScenarioStep
from remnant.scenarios.transitions import ScenarioTransitionEngine, ScenarioTransitionError


VALID = """
schema_version: 1
scenario:
  id: basic_revocation_test
  name: Authorization Revocation Replay
tenants:
  - id: tenant-a
identities:
  - id: alice
    tenant: tenant-a
    roles: [user]
resources:
  - id: document-1
    tenant: tenant-a
    owner: alice
steps:
  - action: grant_permission
    principal: alice
    resource: document-1
  - action: prime_cache
    principal: alice
    resource: document-1
  - action: revoke_permission
    principal: alice
    resource: document-1
  - action: request_cache
    principal: alice
    resource: document-1
"""


def test_yaml_scenario_loads_and_validates():
    scenario = ScenarioLoader().loads(VALID)
    ScenarioValidator().validate(scenario)
    assert scenario.scenario_id == "basic_revocation_test"
    assert len(scenario.steps) == 4


def test_json_scenario_loads():
    document = {
        "scenario": {"id": "json-test", "name": "JSON test"},
        "tenants": ["tenant-a"],
        "identities": [{"id": "alice", "tenant": "tenant-a"}],
        "resources": [{"id": "doc", "tenant": "tenant-a", "owner": "alice"}],
        "steps": [{"action": "request_origin", "principal": "alice", "resource": "doc"}],
    }
    scenario = ScenarioLoader().loads(json.dumps(document), format="json")
    ScenarioValidator().validate(scenario)
    assert scenario.name == "JSON test"


def test_unknown_resource_reference_is_rejected():
    scenario = ScenarioLoader().loads(VALID.replace("resource: document-1", "resource: missing", 1))
    with pytest.raises(ScenarioValidationError, match="unknown resource"):
        ScenarioValidator().validate(scenario)


def test_unsupported_action_is_rejected():
    scenario = ScenarioLoader().loads(VALID.replace("grant_permission", "execute_shell"))
    with pytest.raises(ScenarioValidationError, match="unsupported action"):
        ScenarioValidator().validate(scenario)


def test_duplicate_tenant_is_rejected():
    scenario = Scenario(
        scenario_id="duplicate", name="Duplicate tenant", schema_version=1,
        tenants=("tenant-a", "tenant-a"),
        identities=(ScenarioIdentity("alice", "tenant-a"),),
        resources=(),
        steps=(ScenarioStep("suspend_identity", principal="alice"),),
    )
    with pytest.raises(ScenarioValidationError, match="duplicate tenant"):
        ScenarioValidator().validate(scenario)


def test_transition_engine_tracks_permission_revocation_and_cache_prime():
    scenario = ScenarioLoader().loads(VALID)
    state = ScenarioTransitionEngine().execute(scenario)
    assert ("alice", "document-1", "read") not in state.grants
    assert ("alice", "document-1") in state.primed_cache
    assert len(state.history) == 4


def test_removed_identity_cannot_be_reactivated_in_scenario():
    scenario = Scenario(
        scenario_id="remove-reactivate", name="Remove then reactivate",
        schema_version=1, tenants=("tenant-a",),
        identities=(ScenarioIdentity("alice", "tenant-a"),),
        resources=(), steps=(
            ScenarioStep("remove_identity", principal="alice"),
            ScenarioStep("reactivate_identity", principal="alice"),
        ),
    )
    with pytest.raises(ScenarioTransitionError, match="removed identity"):
        ScenarioTransitionEngine().execute(scenario)


def test_empty_scenario_document_is_rejected():
    with pytest.raises(ValueError, match="cannot be empty"):
        ScenarioLoader().loads(" ")


def test_missing_required_scenario_field_has_actionable_error():
    malformed = VALID.replace("  name: Authorization Revocation Replay\n", "")
    with pytest.raises(ValueError, match="scenario.*name"):
        ScenarioLoader().loads(malformed)


def test_transition_engine_validates_direct_scenario_before_execution():
    invalid = Scenario(
        scenario_id="invalid", name="Invalid direct input", schema_version=1,
        tenants=("tenant-a",),
        identities=(ScenarioIdentity("alice", "tenant-a"),),
        resources=(),
        steps=(ScenarioStep("grant_permission", principal="alice", resource="missing"),),
    )
    with pytest.raises(ScenarioValidationError, match="unknown resource"):
        ScenarioTransitionEngine().execute(invalid)
