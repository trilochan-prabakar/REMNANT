"""Response analysis primitives for REMNANT V2."""

from remnant.analysis.differential import (
    DEFAULT_SECURITY_HEADERS,
    compare_responses,
)
from remnant.analysis.oracle import (
    ObservationFindingOracle,
    evaluate_observation_finding,
)
from remnant.analysis.models import (
    ComparisonState,
    DifferentialComparison,
    DimensionComparison,
)

__all__ = [
    "ComparisonState",
    "DEFAULT_SECURITY_HEADERS",
    "DifferentialComparison",
    "DimensionComparison",
    "ObservationFindingOracle",
    "evaluate_observation_finding",
    "compare_responses",
]
