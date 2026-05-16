"""LatencyP95Evaluator unit tests.

The class reads `latency_ms` from `context` and `reference_p95_ms` from
`context['evaluator_config']`. Engine plumbing for both keys is owned by
the rubric-wiring sub-task (3.5.5); these tests construct context dicts
directly to pin the contract the evaluator depends on.

Normalisation: `score = 100 * min(reference / raw, 1)`. At-or-below the
reference scores 100; above decays harmonically (2× → 50, 4× → 25).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from mmfp.evaluators import get


@pytest.fixture
def evaluator():
    return get("latency_p95")()


def _ctx(*, latency_ms: int, reference_p95_ms: int) -> dict:
    return {
        "dimension_id": "dim_latency",
        "latency_ms": latency_ms,
        "evaluator_config": {"reference_p95_ms": reference_p95_ms},
    }


def test_at_reference_scores_100(evaluator):
    ctx = _ctx(latency_ms=2000, reference_p95_ms=2000)
    score = evaluator.evaluate("", {}, ctx)
    assert score.normalized_score == Decimal("100")
    assert score.latency_ms == 2000


def test_below_reference_scores_100(evaluator):
    ctx = _ctx(latency_ms=500, reference_p95_ms=2000)
    score = evaluator.evaluate("", {}, ctx)
    assert score.normalized_score == Decimal("100")


def test_twice_reference_scores_50(evaluator):
    ctx = _ctx(latency_ms=4000, reference_p95_ms=2000)
    score = evaluator.evaluate("", {}, ctx)
    assert score.normalized_score == Decimal("50.00")


def test_four_times_reference_scores_25(evaluator):
    ctx = _ctx(latency_ms=8000, reference_p95_ms=2000)
    score = evaluator.evaluate("", {}, ctx)
    assert score.normalized_score == Decimal("25.00")


def test_zero_latency_scores_100(evaluator):
    """Pathological but legal — cached responses, fast-paths. Never punish."""
    ctx = _ctx(latency_ms=0, reference_p95_ms=2000)
    score = evaluator.evaluate("", {}, ctx)
    assert score.normalized_score == Decimal("100")


def test_raw_value_captures_inputs_for_audit(evaluator):
    ctx = _ctx(latency_ms=3000, reference_p95_ms=2000)
    score = evaluator.evaluate("", {}, ctx)
    assert score.raw_value == {"latency_ms": 3000, "reference_p95_ms": 2000}


def test_passed_is_none_for_continuous_score(evaluator):
    """Metric evaluators are continuous, not pass/fail — `passed` stays None."""
    ctx = _ctx(latency_ms=2000, reference_p95_ms=2000)
    score = evaluator.evaluate("", {}, ctx)
    assert score.passed is None


def test_missing_latency_ms_raises(evaluator):
    ctx = {
        "dimension_id": "dim_latency",
        "evaluator_config": {"reference_p95_ms": 2000},
    }
    with pytest.raises(ValueError, match="latency_ms"):
        evaluator.evaluate("", {}, ctx)


def test_missing_reference_p95_ms_raises(evaluator):
    ctx = {
        "dimension_id": "dim_latency",
        "latency_ms": 2000,
        "evaluator_config": {},
    }
    with pytest.raises(ValueError, match="reference_p95_ms"):
        evaluator.evaluate("", {}, ctx)


def test_missing_evaluator_config_raises(evaluator):
    ctx = {"dimension_id": "dim_latency", "latency_ms": 2000}
    with pytest.raises(ValueError, match="reference_p95_ms"):
        evaluator.evaluate("", {}, ctx)


def test_non_positive_reference_raises(evaluator):
    ctx = _ctx(latency_ms=2000, reference_p95_ms=0)
    with pytest.raises(ValueError, match="reference_p95_ms must be >= 1"):
        evaluator.evaluate("", {}, ctx)


def test_negative_latency_raises(evaluator):
    ctx = _ctx(latency_ms=-5, reference_p95_ms=2000)
    with pytest.raises(ValueError, match="latency_ms must be >= 0"):
        evaluator.evaluate("", {}, ctx)


def test_ignores_candidate_output_and_expected(evaluator):
    """Metric evaluators score the response envelope, not the text."""
    ctx = _ctx(latency_ms=1000, reference_p95_ms=2000)
    a = evaluator.evaluate("anything", {"value": "ignored"}, ctx)
    b = evaluator.evaluate("", {}, ctx)
    assert a.normalized_score == b.normalized_score
