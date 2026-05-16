"""ContextWindowAdequacyEvaluator unit tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from mmfp.evaluators import get


@pytest.fixture
def evaluator():
    return get("context_window_adequacy")()


def _ctx(*, window: int, required: int) -> dict:
    return {
        "dimension_id": "dim_window",
        "candidate_context_window": window,
        "evaluator_config": {"required_tokens": required},
    }


def test_window_exceeds_required_passes(evaluator):
    score = evaluator.evaluate("", {}, _ctx(window=128000, required=32000))
    assert score.passed is True
    assert score.normalized_score == Decimal("100")
    assert score.raw_value["headroom_tokens"] == 96000


def test_window_equal_to_required_passes(evaluator):
    """Exact-fit is adequate; the dimension doesn't reward headroom."""
    score = evaluator.evaluate("", {}, _ctx(window=32000, required=32000))
    assert score.passed is True
    assert score.normalized_score == Decimal("100")
    assert score.raw_value["headroom_tokens"] == 0


def test_window_below_required_fails(evaluator):
    score = evaluator.evaluate("", {}, _ctx(window=16000, required=32000))
    assert score.passed is False
    assert score.normalized_score == Decimal("0")
    assert "short by 16000" in score.reason


def test_raw_value_captures_inputs(evaluator):
    score = evaluator.evaluate("", {}, _ctx(window=64000, required=8000))
    assert score.raw_value == {
        "candidate_context_window": 64000,
        "required_tokens": 8000,
        "headroom_tokens": 56000,
    }


def test_missing_candidate_window_raises(evaluator):
    ctx = {
        "dimension_id": "dim_window",
        "evaluator_config": {"required_tokens": 32000},
    }
    with pytest.raises(ValueError, match="candidate_context_window"):
        evaluator.evaluate("", {}, ctx)


def test_missing_required_tokens_raises(evaluator):
    ctx = {
        "dimension_id": "dim_window",
        "candidate_context_window": 128000,
        "evaluator_config": {},
    }
    with pytest.raises(ValueError, match="required_tokens"):
        evaluator.evaluate("", {}, ctx)


def test_missing_evaluator_config_raises(evaluator):
    ctx = {"dimension_id": "dim_window", "candidate_context_window": 128000}
    with pytest.raises(ValueError, match="required_tokens"):
        evaluator.evaluate("", {}, ctx)


def test_non_positive_required_raises(evaluator):
    with pytest.raises(ValueError, match="required_tokens must be >= 1"):
        evaluator.evaluate("", {}, _ctx(window=128000, required=0))


def test_non_positive_window_raises(evaluator):
    with pytest.raises(ValueError, match="candidate_context_window must be >= 1"):
        evaluator.evaluate("", {}, _ctx(window=0, required=32000))


def test_ignores_candidate_output_and_expected(evaluator):
    """Scores the envelope, not any per-example payload."""
    ctx = _ctx(window=128000, required=32000)
    a = evaluator.evaluate("anything", {"value": "ignored"}, ctx)
    b = evaluator.evaluate("", {}, ctx)
    assert a.passed == b.passed
    assert a.normalized_score == b.normalized_score
