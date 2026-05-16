"""CostPerCallEvaluator — per-call cost scored against a config reference.

Single class serves both Tier 1 ("cost per 1,000 interactions") and Tier 3
("cost per interaction") via the `per_calls` config scalar: the grouped cost
is `cost_usd * per_calls`, normalised against `reference_usd`. Tier 3 omits
`per_calls` (defaults to 1) and reads as cost-per-call; Tier 1 sets
`per_calls: 1000` and reads as cost-per-1000-calls. The naming + scale
decision is surfaced as an architectural-input on MLI-267.

Context contract:
    context['cost_usd']                          Decimal/float/int >= 0
    context['evaluator_config']['reference_usd'] Decimal/float/int > 0
    context['evaluator_config']['per_calls']     int >= 1  (default: 1)

Cost units are USD throughout the rubric; the engine is responsible for
converting provider-reported currencies upstream of the evaluator.

`candidate_output` and `expected` are ignored — cost is a property of the
invocation envelope.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from mmfp.evaluators._registry import register
from mmfp.evaluators.metric._helpers import (
    normalise_lower_better,
    require_config,
    require_non_negative_decimal,
    require_positive_decimal,
    require_positive_int,
)
from mmfp.models.matrix_run import EvaluatorScore
from mmfp.plugins.evaluator import EvaluatorPlugin


@register
class CostPerCallEvaluator(EvaluatorPlugin):
    name = "cost_per_call"

    def evaluate(
        self,
        candidate_output: str,
        expected: dict[str, Any],
        context: dict[str, Any],
    ) -> EvaluatorScore:
        if "dimension_id" not in context:
            raise ValueError("context must include 'dimension_id'")
        if "cost_usd" not in context:
            raise ValueError(
                "metric evaluator 'cost_per_call' requires context['cost_usd'] "
                "(populated by the engine from the response envelope)"
            )
        cost_usd = require_non_negative_decimal(context["cost_usd"], name="cost_usd")

        cfg = require_config(context)
        if "reference_usd" not in cfg:
            raise ValueError(
                "evaluator 'cost_per_call' requires "
                "evaluator_config['reference_usd'] (the cost target in USD, "
                "set in the rubric YAML)"
            )
        reference_usd = require_positive_decimal(
            cfg["reference_usd"], name="reference_usd"
        )
        per_calls = require_positive_int(
            cfg.get("per_calls", 1), name="per_calls", minimum=1
        )

        group_cost = cost_usd * Decimal(per_calls)
        normalised = normalise_lower_better(raw=group_cost, reference=reference_usd)

        return EvaluatorScore(
            dimension_id=context["dimension_id"],
            evaluator_id=context.get("evaluator_id", self.name),
            raw_value={
                "cost_usd": cost_usd,
                "reference_usd": reference_usd,
                "per_calls": per_calls,
                "group_cost_usd": group_cost,
            },
            normalized_score=normalised,
            passed=None,
            source_field=self.scores_field,
            cost_usd=cost_usd,
            reason=_reason(group_cost, reference_usd, per_calls),
        )


def _reason(group_cost: Decimal, reference_usd: Decimal, per_calls: int) -> str:
    unit = f"per {per_calls} call{'s' if per_calls != 1 else ''}"
    if group_cost <= reference_usd:
        return f"cost ${group_cost} {unit} ≤ target ${reference_usd}"
    return f"cost ${group_cost} {unit} exceeds target ${reference_usd}"
