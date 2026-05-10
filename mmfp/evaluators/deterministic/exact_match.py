"""Exact-string-equality evaluator.

`expected["value"]` (str) is compared with `candidate_output`. Default mode
is `"trim"` — trailing newlines from chat completions shouldn't fail an
otherwise correct answer. `"exact"` and `"casefold"` are also supported.
"""

from __future__ import annotations

from typing import Any

from mmfp.evaluators._registry import register
from mmfp.evaluators.deterministic._helpers import make_score
from mmfp.models.matrix_run import EvaluatorScore
from mmfp.plugins.evaluator import EvaluatorPlugin


@register
class ExactMatchEvaluator(EvaluatorPlugin):
    name = "exact_match"

    def evaluate(
        self,
        candidate_output: str,
        expected: dict[str, Any],
        context: dict[str, Any],
    ) -> EvaluatorScore:
        if "value" not in expected:
            raise ValueError("ExactMatch requires expected['value']")
        target = expected["value"]
        if not isinstance(target, str):
            raise TypeError("ExactMatch expects expected['value'] to be a string")

        mode = expected.get("normalize", "trim")
        candidate, target_norm = _normalise(candidate_output, target, mode)
        passed = candidate == target_norm
        return make_score(
            context=context,
            evaluator_name=self.name,
            source_field=self.scores_field,
            raw_value={"candidate": candidate, "expected": target_norm, "mode": mode},
            passed=passed,
            reason="exact match" if passed else "strings differ",
        )


def _normalise(candidate: str, target: str, mode: str) -> tuple[str, str]:
    if mode == "exact":
        return candidate, target
    if mode == "trim":
        return candidate.strip(), target.strip()
    if mode == "casefold":
        return candidate.strip().casefold(), target.strip().casefold()
    raise ValueError(
        f"unknown normalize mode '{mode}'; expected one of: exact, trim, casefold"
    )
