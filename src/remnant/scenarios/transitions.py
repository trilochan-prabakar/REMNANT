from dataclasses import dataclass, field

from remnant.scenarios.models import Scenario, ScenarioStep
from remnant.scenarios.validator import ScenarioValidator


@dataclass
class ScenarioState:
    """Deterministic logical state for scenario dry-runs; no network I/O occurs."""

    grants: set[tuple[str, str, str]] = field(default_factory=set)
    denials: set[tuple[str, str, str]] = field(default_factory=set)
    suspended: set[str] = field(default_factory=set)
    removed: set[str] = field(default_factory=set)
    primed_cache: set[tuple[str, str]] = field(default_factory=set)
    history: list[dict[str, object]] = field(default_factory=list)


class ScenarioTransitionError(ValueError):
    pass


class ScenarioTransitionEngine:
    """Apply state-changing scenario steps and record deterministic history."""

    STATE_ACTIONS = {
        "grant_permission", "deny_permission", "revoke_permission",
        "clear_denial", "suspend_identity", "reactivate_identity",
        "remove_identity", "prime_cache",
    }

    def execute(self, scenario: Scenario) -> ScenarioState:
        # Validate the complete document before applying any state transition.
        # This keeps direct callers as safe as callers using ScenarioLoader.
        ScenarioValidator().validate(scenario)
        state = ScenarioState()
        for index, step in enumerate(scenario.steps, start=1):
            self.apply(state, step, index=index)
        return state

    def apply(self, state: ScenarioState, step: ScenarioStep, *, index: int) -> None:
        principal = step.principal
        resource = step.resource
        permission = step.permission
        action = step.action

        if action == "grant_permission":
            state.grants.add((principal, resource, permission))
            state.denials.discard((principal, resource, permission))
        elif action == "deny_permission":
            state.denials.add((principal, resource, permission))
            state.grants.discard((principal, resource, permission))
        elif action == "revoke_permission":
            state.grants.discard((principal, resource, permission))
        elif action == "clear_denial":
            state.denials.discard((principal, resource, permission))
        elif action == "suspend_identity":
            if principal in state.removed:
                raise ScenarioTransitionError(f"step {index}: removed identity cannot be suspended")
            state.suspended.add(principal)
        elif action == "reactivate_identity":
            if principal in state.removed:
                raise ScenarioTransitionError(f"step {index}: removed identity cannot be reactivated")
            state.suspended.discard(principal)
        elif action == "remove_identity":
            state.removed.add(principal)
            state.suspended.discard(principal)
        elif action == "prime_cache":
            state.primed_cache.add((principal, resource))
        elif action in {"request_origin", "request_cache"}:
            pass
        else:
            raise ScenarioTransitionError(f"step {index}: unsupported action '{action}'")

        state.history.append({
            "step": index, "action": action,
            "principal": principal, "resource": resource,
            "permission": permission,
        })
