"""CostPerCallEvaluator unit tests.

Reads `cost_usd` from `context` and `reference_usd` + optional `per_calls`
from `context['evaluator_config']`. The per_calls scale lets the same
evaluator serve Tier 1 ("cost per 1,000 calls") and Tier 3 ("cost per
interaction") without a per-tier subclass — see the architectural-input on
MLI-267.

Normalisation: `score = 100 * min(reference_usd / (cost_usd * per_calls), 1)`.
Grouped cost at-or-below reference scores 100; above decays harmonically.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from mmfp.evaluators import get


@pytest.fixture
def evaluator():
    return get("cost_per_call")()


def _ctx(
    *,
    cost_usd: str,
    reference_usd: str,
    per_calls: int = 1,
) -> dict:
    return {
        "dimension_id": "dim_cost",
        "cost_usd": Decimal(cost_usd),
        "evaluator_config": {
            "reference_usd": Decimal(reference_usd),
            "per_calls": per_calls,
        },
    }


def test_at_reference_scores_100(evaluator):
    ctx = _ctx(cost_usd="0.001", reference_usd="0.001")
    score = evaluator.evaluate("", {}, ctx)
    assert score.normalized_score == Decimal("100")
    assert score.cost_usd == Decimal("0.001")


def test_below_reference_scores_100(evaluator):
    ctx = _ctx(cost_usd="0.0005", reference_usd="0.001")
    score = evaluator.evaluate("", {}, ctx)
    assert score.normalized_score == Decimal("100")


def test_twice_reference_scores_50(evaluator):
    ctx = _ctx(cost_usd="0.002", reference_usd="0.001")
    score = evaluator.evaluate("", {}, ctx)
    assert score.normalized_score == Decimal("50.00")


def test_per_calls_groups_the_cost(evaluator):
    """Tier 1 case: $5e-6 per call × 1000 = $0.005 group; reference $0.005 → 100."""
    ctx = _ctx(cost_usd="0.000005", reference_usd="0.005", per_calls=1000)
    score = evaluator.evaluate("", {}, ctx)
    assert score.normalized_score == Decimal("100")


def test_per_calls_above_reference_decays(evaluator):
    """Per-call cost twice as expensive as the per-1000 reference allows → 50."""
    ctx = _ctx(cost_usd="0.00001", reference_usd="0.005", per_calls=1000)
    score = evaluator.evaluate("", {}, ctx)
    assert score.normalized_score == Decimal("50.00")


def test_per_calls_defaults_to_1_when_omitted(evaluator):
    ctx = {
        "dimension_id": "dim_cost",
        "cost_usd": Decimal("0.001"),
        "evaluator_config": {"reference_usd": Decimal("0.001")},
    }
    score = evaluator.evaluate("", {}, ctx)
    assert score.normalized_score == Decimal("100")


def test_zero_cost_scores_100(evaluator):
    ctx = _ctx(cost_usd="0", reference_usd="0.001")
    score = evaluator.evaluate("", {}, ctx)
    assert score.normalized_score == Decimal("100")


def test_raw_value_captures_inputs_for_audit(evaluator):
    ctx = _ctx(cost_usd="0.002", reference_usd="0.001", per_calls=1)
    score = evaluator.evaluate("", {}, ctx)
    assert score.raw_value == {
        "cost_usd": Decimal("0.002"),
        "reference_usd": Decimal("0.001"),
        "per_calls": 1,
        "group_cost_usd": Decimal("0.002"),
    }


def test_passed_is_none_for_continuous_score(evaluator):
    ctx = _ctx(cost_usd="0.001", reference_usd="0.001")
    score = evaluator.evaluate("", {}, ctx)
    assert score.passed is None


def test_missing_cost_usd_raises(evaluator):
    ctx = {
        "dimension_id": "dim_cost",
        "evaluator_config": {"reference_usd": Decimal("0.001")},
    }
    with pytest.raises(ValueError, match="cost_usd"):
        evaluator.evaluate("", {}, ctx)


def test_missing_reference_usd_raises(evaluator):
    ctx = {
        "dimension_id": "dim_cost",
        "cost_usd": Decimal("0.001"),
        "evaluator_config": {},
    }
    with pytest.raises(ValueError, match="reference_usd"):
        evaluator.evaluate("", {}, ctx)


def test_non_positive_reference_raises(evaluator):
    ctx = _ctx(cost_usd="0.001", reference_usd="0")
    with pytest.raises(ValueError, match="reference_usd must be > 0"):
        evaluator.evaluate("", {}, ctx)


def test_non_positive_per_calls_raises(evaluator):
    ctx = _ctx(cost_usd="0.001", reference_usd="0.001", per_calls=0)
    with pytest.raises(ValueError, match="per_calls must be >= 1"):
        evaluator.evaluate("", {}, ctx)


def test_negative_cost_raises(evaluator):
    ctx = _ctx(cost_usd="-0.001", reference_usd="0.001")
    with pytest.raises(ValueError, match="cost_usd must be >= 0"):
        evaluator.evaluate("", {}, ctx)


def test_accepts_float_cost_and_coerces_to_decimal(evaluator):
    """The engine may hand cost as a float from arithmetic; accept it cleanly."""
    ctx = {
        "dimension_id": "dim_cost",
        "cost_usd": 0.001,
        "evaluator_config": {"reference_usd": 0.001},
    }
    score = evaluator.evaluate("", {}, ctx)
    assert score.normalized_score == Decimal("100")
    assert score.cost_usd == Decimal("0.001")


def test_ignores_candidate_output_and_expected(evaluator):
    ctx = _ctx(cost_usd="0.0005", reference_usd="0.001")
    a = evaluator.evaluate("anything", {"value": "ignored"}, ctx)
    b = evaluator.evaluate("", {}, ctx)
    assert a.normalized_score == b.normalized_score
