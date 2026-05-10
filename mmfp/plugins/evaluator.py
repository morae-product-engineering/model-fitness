"""EvaluatorPlugin — the contract every evaluator implements.

P3 plugin interface. The signature is the public boundary; modifications need
explicit human approval per CLAUDE.md.

Evaluators turn a candidate's response into an `EvaluatorScore` against one
rubric dimension. Deterministic evaluators (regex, exact match, JSON Schema)
live in `mmfp.evaluators.deterministic`; LLM-judge variants land in MLI-211
under `mmfp.evaluators.inferential`. The matrix engine (MLI-172) iterates the
rubric and dispatches to evaluators by name via the registry in
`mmfp.evaluators`.

Reasoning models emit both `content` and `reasoning_content`. Each evaluator
declares which field it scores via the `scores_field` class attribute
(default: `CONTENT`). The matrix engine extracts the appropriate field
before calling `evaluate`; the evaluator stamps `scores_field` onto the
returned `EvaluatorScore` so the contract is enforced end-to-end.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from mmfp.models.matrix_run import EvaluatorScore, SourceField


class EvaluatorPlugin(ABC):
    """Abstract base class for all rubric evaluators."""

    name: ClassVar[str]
    """Registry key — concrete subclasses must override."""

    scores_field: ClassVar[SourceField] = SourceField.CONTENT
    """Which response field this evaluator scores. Tier 1 / Tier 2 evaluators
    must score `content` only (see MLI-165 §2). Tier 3 evaluators that score
    the reasoning trace override this on the subclass."""

    @abstractmethod
    def evaluate(
        self,
        candidate_output: str,
        expected: dict[str, Any],
        context: dict[str, Any],
    ) -> EvaluatorScore:
        """Score one (candidate_output, example) pair.

        candidate_output: the field's text, already extracted by the binding
            from `message.content` or `message.reasoning_content` per
            `cls.scores_field`.
        expected: `DatasetExample.expected` — evaluator-specific shape, e.g.
            `{"value": "..."}` for exact match, `{"schema": {...}}` for JSON
            Schema, `{"pattern": "..."}` for regex.
        context: per-call metadata. `dimension_id` is required (used to
            stamp the score); `evaluator_id` is optional and defaults to
            `cls.name`. Implementations may read additional dimension-level
            config keys from here.

        Implementations must be deterministic — same inputs return the same
        score. Side effects (network, time) are forbidden.
        """
        ...
