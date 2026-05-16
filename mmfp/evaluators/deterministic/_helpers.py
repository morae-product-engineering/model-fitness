"""Tiny helpers shared by the deterministic evaluators.

`make_score` was lifted when three evaluators (exact_match, json_schema,
regex_match) repeated the same binary-score construction. `continuous_score`
and `format_jsonschema_error` are the same lift for the parse_rate /
structured_output_reliability / confidence_calibration trio added in
MLI-271: three callers, identical EvaluatorScore boilerplate, single
formatter for jsonschema errors.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from jsonschema.exceptions import ValidationError

from mmfp.models.matrix_run import EvaluatorScore, SourceField

_SCORE_QUANTUM = Decimal("0.01")


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

    Used by deterministic evaluators that are pass/fail by definition:
    passed -> 100, failed -> 0. Continuous-valued deterministic evaluators
    (parse_rate, confidence_calibration, structured_output_reliability) use
    `continuous_score` instead; metric-family evaluators build the model
    directly because they also stamp `latency_ms` / `cost_usd`.
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


def continuous_score(
    *,
    context: dict[str, Any],
    evaluator_name: str,
    source_field: SourceField,
    raw_value: Any,
    normalized_score: Decimal,
    reason: str,
) -> EvaluatorScore:
    """Build a non-binary EvaluatorScore (passed=None) on the 0–100 scale.

    The caller computes `normalized_score`; this helper enforces the
    0 ≤ s ≤ 100 bound by quantising to two decimal places and asserting
    bounds — the same guarantee `EvaluatorScore` validates, surfaced at
    the helper boundary so a buggy caller fails with a readable message.
    """
    if "dimension_id" not in context:
        raise ValueError("context must include 'dimension_id'")
    if normalized_score < Decimal("0") or normalized_score > Decimal("100"):
        raise ValueError(
            f"normalized_score must be in [0, 100]; got {normalized_score}"
        )
    return EvaluatorScore(
        dimension_id=context["dimension_id"],
        evaluator_id=context.get("evaluator_id", evaluator_name),
        raw_value=raw_value,
        normalized_score=normalized_score.quantize(_SCORE_QUANTUM),
        passed=None,
        source_field=source_field,
        reason=reason,
    )


def format_jsonschema_error(err: ValidationError) -> dict[str, Any]:
    """Compact, JSON-safe summary of a jsonschema ValidationError.

    `parse_rate` and `structured_output_reliability` both stamp these into
    `raw_value` so a reviewer can see which turns failed and why without
    re-running the evaluator. `json_schema.py` keeps its own local copy
    for historical reasons (MLI-170 predates the lift); the shape is
    identical so they're interchangeable.
    """
    return {
        "path": "/".join(str(p) for p in err.absolute_path),
        "message": err.message,
        "validator": err.validator,
    }
