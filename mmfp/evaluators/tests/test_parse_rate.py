"""ParseRateEvaluator unit tests.

Trajectory contract: candidate_output is a JSON-encoded array of already-
decoded per-turn objects. The schema in expected['schema'] is applied to
each turn; score is the % of turns that validate.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from mmfp.evaluators import get


@pytest.fixture
def evaluator():
    return get("parse_rate")()


@pytest.fixture
def ctx():
    return {"dimension_id": "dim_parse_rate"}


@pytest.fixture
def turn_schema():
    return {
        "type": "object",
        "required": ["intent", "args"],
        "properties": {
            "intent": {"type": "string"},
            "args": {"type": "object"},
        },
        "additionalProperties": True,
    }


def _trajectory(*turns: dict) -> str:
    return json.dumps(list(turns))


def test_all_turns_valid_scores_100(evaluator, ctx, turn_schema):
    traj = _trajectory(
        {"intent": "search", "args": {"q": "foo"}},
        {"intent": "open", "args": {"id": 1}},
    )
    score = evaluator.evaluate(traj, {"schema": turn_schema}, ctx)
    assert score.normalized_score == Decimal("100.00")
    assert score.passed is None
    assert score.raw_value["passed_count"] == 2
    assert score.raw_value["total"] == 2


def test_one_of_two_turns_valid_scores_50(evaluator, ctx, turn_schema):
    traj = _trajectory(
        {"intent": "search", "args": {"q": "foo"}},
        {"intent": "open"},  # missing args
    )
    score = evaluator.evaluate(traj, {"schema": turn_schema}, ctx)
    assert score.normalized_score == Decimal("50.00")
    assert score.raw_value["passed_count"] == 1
    failed = [t for t in score.raw_value["turns"] if not t["passed"]]
    assert len(failed) == 1
    assert failed[0]["turn"] == 1
    assert any("args" in e["message"] for e in failed[0]["errors"])


def test_three_of_four_turns_valid_scores_75(evaluator, ctx, turn_schema):
    traj = _trajectory(
        {"intent": "a", "args": {}},
        {"intent": "b", "args": {}},
        {"intent": "c", "args": {}},
        {"intent": 99, "args": {}},  # wrong type
    )
    score = evaluator.evaluate(traj, {"schema": turn_schema}, ctx)
    assert score.normalized_score == Decimal("75.00")


def test_no_turns_valid_scores_0(evaluator, ctx, turn_schema):
    traj = _trajectory({"intent": 1}, {"intent": 2})
    score = evaluator.evaluate(traj, {"schema": turn_schema}, ctx)
    assert score.normalized_score == Decimal("0.00")
    assert score.raw_value["passed_count"] == 0


def test_non_json_output_scores_0(evaluator, ctx, turn_schema):
    score = evaluator.evaluate("not json {", {"schema": turn_schema}, ctx)
    assert score.normalized_score == Decimal("0")
    assert "not valid JSON" in score.reason
    assert "decode_error" in score.raw_value


def test_non_array_output_scores_0(evaluator, ctx, turn_schema):
    """A single JSON object is not a trajectory — caller is expected to wrap."""
    score = evaluator.evaluate(
        '{"intent": "x", "args": {}}', {"schema": turn_schema}, ctx
    )
    assert score.normalized_score == Decimal("0")
    assert "must be a JSON array" in score.reason


def test_empty_trajectory_raises(evaluator, ctx, turn_schema):
    """Empty trajectory is a dataset bug, not a candidate failure."""
    with pytest.raises(ValueError, match="non-empty trajectory"):
        evaluator.evaluate("[]", {"schema": turn_schema}, ctx)


def test_missing_schema_raises(evaluator, ctx):
    with pytest.raises(ValueError, match="expected\\['schema'\\]"):
        evaluator.evaluate("[]", {}, ctx)


def test_invalid_schema_itself_raises(evaluator, ctx):
    with pytest.raises(ValueError, match="not a valid JSON Schema"):
        evaluator.evaluate(
            _trajectory({"x": 1}),
            {"schema": {"type": "not-a-real-type"}},
            ctx,
        )


def test_raw_value_lists_each_turn(evaluator, ctx, turn_schema):
    traj = _trajectory(
        {"intent": "a", "args": {}},
        {"intent": "b"},
    )
    score = evaluator.evaluate(traj, {"schema": turn_schema}, ctx)
    turns = score.raw_value["turns"]
    assert [t["turn"] for t in turns] == [0, 1]
    assert turns[0]["passed"] is True
    assert turns[1]["passed"] is False


def test_quantises_to_two_decimal_places(evaluator, ctx, turn_schema):
    """Three turns with one pass — 1/3 = 33.33...; should quantise cleanly."""
    traj = _trajectory(
        {"intent": "a", "args": {}},
        {"intent": 1},
        {"intent": 2},
    )
    score = evaluator.evaluate(traj, {"schema": turn_schema}, ctx)
    assert score.normalized_score == Decimal("33.33")
