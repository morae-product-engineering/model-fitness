"""Evaluator registry and the deterministic-trio re-exports.

Importing this package triggers registration of every concrete evaluator in
`mmfp.evaluators.deterministic` (and, later, `.inferential` and
`.composite`). The matrix engine looks up evaluator classes via `get(name)`.
"""

from mmfp.evaluators._registry import get, names, register

# Side-effect imports — each module @register's its evaluator class on import.
from mmfp.evaluators.deterministic import (  # noqa: E402, F401
    exact_match,
    json_schema,
    regex_match,
)
from mmfp.plugins.evaluator import EvaluatorPlugin

__all__ = ["EvaluatorPlugin", "get", "names", "register"]
