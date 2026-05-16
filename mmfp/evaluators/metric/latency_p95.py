"""LatencyP95Evaluator — per-call latency scored against a p95 target.

The "p95" in the name refers to the *intent* of the reference value (stewards
set `reference_p95_ms` to the SLO p95 they want candidates to meet); the
evaluator itself runs per call and emits one normalised score per
(candidate, example). The dimension-level aggregate (mean across examples,
in `Scorecard.scores_for_tier`) is a proxy for distribution shape — not a
true p95. See the architectural-input on MLI-267 for the rationale.

Context contract:
    context['latency_ms']                    int  >= 0  (from BindingResponse)
    context['evaluator_config']['reference_p95_ms']  int > 0  (from rubric YAML)

`candidate_output` and `expected` are ignored — latency is a property of the
invocation envelope, not the response text.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from mmfp.evaluators._registry import register
from mmfp.evaluators.metric._helpers import (
    normalise_lower_better,
    require_config,
    require_non_negative_int,
    require_positive_int,
)
from mmfp.models.matrix_run import EvaluatorScore
from mmfp.plugins.evaluator import EvaluatorPlugin


@register
class LatencyP95Evaluator(EvaluatorPlugin):
    name = "latency_p95"

    def evaluate(
        self,
        candidate_output: str,
        expected: dict[str, Any],
        context: dict[str, Any],
    ) -> EvaluatorScore:
        if "dimension_id" not in context:
            raise ValueError("context must include 'dimension_id'")
        if "latency_ms" not in context:
            raise ValueError(
                "metric evaluator 'latency_p95' requires context['latency_ms'] "
                "(populated by the engine from BindingResponse.latency_ms)"
            )
        latency_ms = require_non_negative_int(context["latency_ms"], name="latency_ms")

        cfg = require_config(context)
        if "reference_p95_ms" not in cfg:
            raise ValueError(
                "evaluator 'latency_p95' requires evaluator_config['reference_p95_ms'] "
                "(the SLO target in ms, set in the rubric YAML)"
            )
        reference_p95_ms = require_positive_int(
            cfg["reference_p95_ms"], name="reference_p95_ms"
        )

        normalised = normalise_lower_better(
            raw=Decimal(latency_ms), reference=Decimal(reference_p95_ms)
        )

        return EvaluatorScore(
            dimension_id=context["dimension_id"],
            evaluator_id=context.get("evaluator_id", self.name),
            raw_value={
                "latency_ms": latency_ms,
                "reference_p95_ms": reference_p95_ms,
            },
            normalized_score=normalised,
            passed=None,
            source_field=self.scores_field,
            latency_ms=latency_ms,
            reason=_reason(latency_ms, reference_p95_ms),
        )


def _reason(latency_ms: int, reference_p95_ms: int) -> str:
    if latency_ms <= reference_p95_ms:
        return f"latency {latency_ms}ms ≤ p95 target {reference_p95_ms}ms"
    return f"latency {latency_ms}ms exceeds p95 target {reference_p95_ms}ms"
