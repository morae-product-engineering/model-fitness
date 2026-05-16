"""ConfidenceCalibrationEvaluator unit tests.

Per-example score: (1 - (confidence - correctness)^2) * 100.
Engine averages across examples to get the dimension-level inverted Brier.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from mmfp.evaluators import get


@pytest.fixture
def evaluator():
    return get("confidence_calibration")()


@pytest.fixture
def ctx():
    return {"dimension_id": "dim_calibration"}


def _output(label: str, confidence: float) -> str:
    return json.dumps({"label": label, "confidence": confidence})


def test_correct_with_full_confidence_scores_100(evaluator, ctx):
    score = evaluator.evaluate(_output("NDA", 1.0), {"value": "NDA"}, ctx)
    assert score.normalized_score == Decimal("100.00")
    assert score.passed is None
    assert score.raw_value["correctness"] == 1
    assert score.raw_value["brier_component"] == 0.0


def test_incorrect_with_zero_confidence_scores_100(evaluator, ctx):
    """Maximally calibrated 'I don't know': confidence 0, label wrong."""
    score = evaluator.evaluate(_output("NDA", 0.0), {"value": "Lease"}, ctx)
    assert score.normalized_score == Decimal("100.00")
    assert score.raw_value["correctness"] == 0
    assert score.raw_value["brier_component"] == 0.0


def test_correct_with_zero_confidence_scores_0(evaluator, ctx):
    """Correct answer, but the model said it didn't know — bad calibration."""
    score = evaluator.evaluate(_output("NDA", 0.0), {"value": "NDA"}, ctx)
    assert score.normalized_score == Decimal("0.00")
    assert score.raw_value["brier_component"] == 1.0


def test_incorrect_with_full_confidence_scores_0(evaluator, ctx):
    """Wrong and 100% sure — worst possible calibration."""
    score = evaluator.evaluate(_output("NDA", 1.0), {"value": "Lease"}, ctx)
    assert score.normalized_score == Decimal("0.00")


def test_half_confidence_correct_scores_75(evaluator, ctx):
    """Brier = (0.5 - 1)^2 = 0.25; score = (1 - 0.25) * 100 = 75."""
    score = evaluator.evaluate(_output("NDA", 0.5), {"value": "NDA"}, ctx)
    assert score.normalized_score == Decimal("75.00")


def test_half_confidence_incorrect_scores_75(evaluator, ctx):
    """Brier = (0.5 - 0)^2 = 0.25; symmetric with the correct case."""
    score = evaluator.evaluate(_output("NDA", 0.5), {"value": "Lease"}, ctx)
    assert score.normalized_score == Decimal("75.00")


def test_non_json_output_scores_0(evaluator, ctx):
    score = evaluator.evaluate("not json", {"value": "x"}, ctx)
    assert score.normalized_score == Decimal("0")
    assert "not valid JSON" in score.reason


def test_non_object_output_scores_0(evaluator, ctx):
    score = evaluator.evaluate("[1, 2, 3]", {"value": "x"}, ctx)
    assert score.normalized_score == Decimal("0")
    assert "JSON object" in score.reason


def test_missing_label_scores_0(evaluator, ctx):
    score = evaluator.evaluate(
        json.dumps({"confidence": 0.9}), {"value": "NDA"}, ctx
    )
    assert score.normalized_score == Decimal("0")
    assert "label" in score.reason


def test_missing_confidence_scores_0(evaluator, ctx):
    score = evaluator.evaluate(
        json.dumps({"label": "NDA"}), {"value": "NDA"}, ctx
    )
    assert score.normalized_score == Decimal("0")
    assert "confidence" in score.reason


def test_confidence_above_one_scores_0(evaluator, ctx):
    score = evaluator.evaluate(_output("NDA", 1.5), {"value": "NDA"}, ctx)
    assert score.normalized_score == Decimal("0")
    assert "[0, 1]" in score.reason


def test_confidence_negative_scores_0(evaluator, ctx):
    score = evaluator.evaluate(_output("NDA", -0.1), {"value": "NDA"}, ctx)
    assert score.normalized_score == Decimal("0")


def test_confidence_as_bool_scores_0(evaluator, ctx):
    """Bool is int in Python — guard against True sneaking through as 1."""
    payload = json.dumps({"label": "NDA", "confidence": True})
    score = evaluator.evaluate(payload, {"value": "NDA"}, ctx)
    assert score.normalized_score == Decimal("0")


def test_confidence_as_string_scores_0(evaluator, ctx):
    payload = json.dumps({"label": "NDA", "confidence": "0.9"})
    score = evaluator.evaluate(payload, {"value": "NDA"}, ctx)
    assert score.normalized_score == Decimal("0")


def test_missing_expected_value_raises(evaluator, ctx):
    with pytest.raises(ValueError, match="expected\\['value'\\]"):
        evaluator.evaluate(_output("NDA", 0.9), {}, ctx)


def test_non_string_expected_value_raises(evaluator, ctx):
    with pytest.raises(TypeError):
        evaluator.evaluate(_output("NDA", 0.9), {"value": 42}, ctx)


def test_custom_label_and_confidence_keys(evaluator, ctx):
    payload = json.dumps({"answer": "NDA", "prob": 1.0})
    score = evaluator.evaluate(
        payload,
        {"value": "NDA", "label_key": "answer", "confidence_key": "prob"},
        ctx,
    )
    assert score.normalized_score == Decimal("100.00")
