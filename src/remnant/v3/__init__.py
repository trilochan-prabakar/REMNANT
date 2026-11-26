"""Additive V3 capabilities; V1 and V2 modules remain unchanged."""
from remnant.v3.cache_analysis import CacheAnalysis, Cacheability, CacheState, analyze_response
from remnant.v3.evidence import RunComparison, StepDifference, V3EvidenceStore
from remnant.v3.identity_isolation import (
    IdentityIsolationResult, IsolationStatus, evaluate_identity_isolation,
)
from remnant.v3.runner import (
    RequestTrace, RunStatus, ScenarioRun, ScenarioRunner, run_to_dict, run_to_json,
)
from remnant.v3.scenarios import (
    ControlStep, RequestStep, ScenarioDefinition, ScenarioFormatError,
    ScenarioLoader, ScenarioStep,
)

__all__ = [
    "CacheAnalysis", "Cacheability", "CacheState", "IdentityIsolationResult",
    "RunComparison", "StepDifference", "V3EvidenceStore",
    "ControlStep", "IsolationStatus", "RequestStep", "RequestTrace", "RunStatus",
    "ScenarioDefinition", "ScenarioFormatError", "ScenarioLoader", "ScenarioStep",
    "ScenarioRun", "ScenarioRunner", "analyze_response", "run_to_dict", "run_to_json",
    "evaluate_identity_isolation",
]
