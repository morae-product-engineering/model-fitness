"""Evaluator registry and the deterministic + metric re-exports.

Importing this package triggers registration of every concrete evaluator in
`mmfp.evaluators.deterministic` and `mmfp.evaluators.metric` (and, later,
`.inferential` and `.composite`). The matrix engine looks up evaluator
classes via `get(name)`.
"""

from mmfp.evaluators._registry import get, names, register

# Side-effect imports — each module @register's its evaluator class on import.
from mmfp.evaluators.deterministic import (  # noqa: E402, F401
    confidence_calibration,
    context_window_adequacy,
    exact_match,
    json_schema,
    parse_rate,
    query_correctness,
    regex_match,
    structured_output_reliability,
)
from mmfp.evaluators.metric import (  # noqa: E402, F401
    cost_per_call,
    latency_p95,
)
from mmfp.plugins.evaluator import EvaluatorPlugin

__all__ = ["EvaluatorPlugin", "get", "names", "register"]
