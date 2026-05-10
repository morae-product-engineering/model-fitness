"""ExactMatchEvaluator unit tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from mmfp.evaluators import get


@pytest.fixture
def evaluator():
    return get("exact_match")()


@pytest.fixture
def ctx():
    return {"dimension_id": "dim_test"}


def test_passes_on_identical_strings(evaluator, ctx):
    score = evaluator.evaluate("hello", {"value": "hello"}, ctx)
    assert score.passed is True
    assert score.normalized_score == Decimal("100")
    assert score.reason == "exact match"


def test_fails_on_different_strings(evaluator, ctx):
    score = evaluator.evaluate("hello", {"value": "world"}, ctx)
    assert score.passed is False
    assert score.normalized_score == Decimal("0")
    assert "differ" in score.reason


def test_default_mode_trims_whitespace(evaluator, ctx):
    """Trailing newline is the chat-completion failure mode this trims away."""
    score = evaluator.evaluate("hello\n", {"value": "hello"}, ctx)
    assert score.passed is True


def test_exact_mode_does_not_trim(evaluator, ctx):
    score = evaluator.evaluate(
        "hello\n", {"value": "hello", "normalize": "exact"}, ctx
    )
    assert score.passed is False


def test_casefold_mode_passes_case_difference(evaluator, ctx):
    score = evaluator.evaluate(
        "Hello", {"value": "HELLO", "normalize": "casefold"}, ctx
    )
    assert score.passed is True


def test_unknown_normalize_mode_raises(evaluator, ctx):
    with pytest.raises(ValueError, match="unknown normalize mode"):
        evaluator.evaluate("x", {"value": "x", "normalize": "wat"}, ctx)


def test_missing_value_raises(evaluator, ctx):
    with pytest.raises(ValueError, match="expected\\['value'\\]"):
        evaluator.evaluate("x", {}, ctx)


def test_non_string_value_raises(evaluator, ctx):
    with pytest.raises(TypeError):
        evaluator.evaluate("x", {"value": 42}, ctx)


def test_raw_value_carries_normalised_strings(evaluator, ctx):
    score = evaluator.evaluate("  hello  ", {"value": "hello"}, ctx)
    assert score.raw_value == {
        "candidate": "hello",
        "expected": "hello",
        "mode": "trim",
    }
