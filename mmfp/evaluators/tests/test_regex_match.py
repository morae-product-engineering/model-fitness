"""RegexMatchEvaluator unit tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from mmfp.evaluators import get


@pytest.fixture
def evaluator():
    return get("regex_match")()


@pytest.fixture
def ctx():
    return {"dimension_id": "dim_test"}


def test_search_passes_on_substring(evaluator, ctx):
    score = evaluator.evaluate("hello world", {"pattern": "world"}, ctx)
    assert score.passed is True
    assert score.normalized_score == Decimal("100")
    assert score.raw_value["match"] == "world"


def test_search_fails_on_no_match(evaluator, ctx):
    score = evaluator.evaluate("hello world", {"pattern": "zebra"}, ctx)
    assert score.passed is False
    assert score.normalized_score == Decimal("0")
    assert "did not match" in score.reason


def test_fullmatch_mode_requires_complete_match(evaluator, ctx):
    score = evaluator.evaluate(
        "hello", {"pattern": "hel", "mode": "fullmatch"}, ctx
    )
    assert score.passed is False


def test_fullmatch_mode_passes_on_complete_match(evaluator, ctx):
    score = evaluator.evaluate(
        "hello", {"pattern": "hello", "mode": "fullmatch"}, ctx
    )
    assert score.passed is True


def test_ignore_case_flag(evaluator, ctx):
    score_no = evaluator.evaluate("HELLO", {"pattern": "hello"}, ctx)
    assert score_no.passed is False
    score_yes = evaluator.evaluate(
        "HELLO", {"pattern": "hello", "flags": ["I"]}, ctx
    )
    assert score_yes.passed is True


def test_full_flag_names_accepted(evaluator, ctx):
    score = evaluator.evaluate(
        "HELLO", {"pattern": "hello", "flags": ["IGNORECASE"]}, ctx
    )
    assert score.passed is True


def test_groups_captured_in_raw_value(evaluator, ctx):
    score = evaluator.evaluate(
        "year=2026", {"pattern": r"year=(\d+)"}, ctx
    )
    assert score.passed is True
    assert score.raw_value["groups"] == ["2026"]


def test_named_groups_in_groupdict(evaluator, ctx):
    score = evaluator.evaluate(
        "year=2026",
        {"pattern": r"year=(?P<year>\d+)"},
        ctx,
    )
    assert score.raw_value["groupdict"] == {"year": "2026"}


def test_invalid_pattern_raises(evaluator, ctx):
    with pytest.raises(ValueError, match="could not compile pattern"):
        evaluator.evaluate("x", {"pattern": "["}, ctx)


def test_unknown_mode_raises(evaluator, ctx):
    with pytest.raises(ValueError, match="mode must be"):
        evaluator.evaluate("x", {"pattern": "x", "mode": "match-or-something"}, ctx)


def test_unknown_flag_raises(evaluator, ctx):
    with pytest.raises(ValueError, match="unknown regex flag"):
        evaluator.evaluate("x", {"pattern": "x", "flags": ["ZZZ"]}, ctx)


def test_missing_pattern_raises(evaluator, ctx):
    with pytest.raises(ValueError, match="expected\\['pattern'\\]"):
        evaluator.evaluate("x", {}, ctx)


def test_non_string_pattern_raises(evaluator, ctx):
    with pytest.raises(TypeError):
        evaluator.evaluate("x", {"pattern": 42}, ctx)
