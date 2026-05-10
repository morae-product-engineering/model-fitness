"""Plugin abstract base classes — the P3 stable boundaries.

Concrete implementations live in sibling packages: evaluators in
`mmfp.evaluators`, bindings in `mmfp.bindings`, etc. The ABCs here are the
public contract; signature changes need explicit human approval per
CLAUDE.md.
"""

from mmfp.plugins.evaluator import EvaluatorPlugin

__all__ = ["EvaluatorPlugin"]
