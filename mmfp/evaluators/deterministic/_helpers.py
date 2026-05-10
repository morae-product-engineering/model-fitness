"""Tiny helpers shared by the deterministic-trio evaluators.

Lifted out of each evaluator only because the same `EvaluatorScore`
construction repeats verbatim three times — three is the line at which
duplication starts to drift.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from mmfp.models.matrix_run import EvaluatorScore, SourceField


def make_score(
    *,
    context: dict[str, Any],
    evaluator_name: str,
    source_field: SourceField,
    raw_value: Any,
    passed: bool,
    reason: str,
) -> EvaluatorScore:
    """Build a binary pass/fail EvaluatorScore.

    Deterministic evaluators are pass/fail by definition: passed -> 100,
    failed -> 0. Continuous-valued evaluators (e.g. cost, latency) build
    EvaluatorScore directly without going through this helper.
    """
    if "dimension_id" not in context:
        raise ValueError("context must include 'dimension_id'")
    return EvaluatorScore(
        dimension_id=context["dimension_id"],
        evaluator_id=context.get("evaluator_id", evaluator_name),
        raw_value=raw_value,
        normalized_score=Decimal("100") if passed else Decimal("0"),
        passed=passed,
        source_field=source_field,
        reason=reason,
    )
