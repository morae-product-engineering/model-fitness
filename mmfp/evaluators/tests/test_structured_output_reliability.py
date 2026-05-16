"""StructuredOutputReliabilityEvaluator unit tests."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from mmfp.evaluators import get


@pytest.fixture
def evaluator():
    return get("structured_output_reliability")()


@pytest.fixture
def ctx():
    return {"dimension_id": "dim_tool_reliability"}


@pytest.fixture
def schemas():
    return {
        "search": {
            "type": "object",
            "required": ["query"],
            "properties": {"query": {"type": "string"}},
            "additionalProperties": False,
        },
        "open": {
            "type": "object",
            "required": ["doc_id"],
            "properties": {"doc_id": {"type": "integer"}},
            "additionalProperties": False,
        },
    }


def _calls(*items) -> str:
    return json.dumps(list(items))


def test_all_calls_reliable_scores_100(evaluator, ctx, schemas):
    payload = _calls(
        {"name": "search", "arguments": json.dumps({"query": "foo"})},
        {"name": "open", "arguments": json.dumps({"doc_id": 7})},
    )
    score = evaluator.evaluate(payload, {"schemas": schemas}, ctx)
    assert score.normalized_score == Decimal("100.00")
    assert score.passed is None


def test_one_of_two_unreliable_scores_50(evaluator, ctx, schemas):
    payload = _calls(
        {"name": "search", "arguments": json.dumps({"query": "foo"})},
        {"name": "search", "arguments": "{not json"},
    )
    score = evaluator.evaluate(payload, {"schemas": schemas}, ctx)
    assert score.normalized_score == Decimal("50.00")
    bad = [c for c in score.raw_value["calls"] if not c["passed"]]
    assert bad[0]["failure"] == "arguments_not_json"


def test_unknown_tool_flagged_distinctly(evaluator, ctx, schemas):
    payload = _calls({"name": "delete", "arguments": json.dumps({"id": 1})})
    score = evaluator.evaluate(payload, {"schemas": schemas}, ctx)
    assert score.normalized_score == Decimal("0.00")
    assert score.raw_value["calls"][0]["failure"] == "unknown_tool"


def test_schema_mismatch_flagged_distinctly(evaluator, ctx, schemas):
    payload = _calls(
        {"name": "search", "arguments": json.dumps({"query": 42})}  # wrong type
    )
    score = evaluator.evaluate(payload, {"schemas": schemas}, ctx)
    assert score.normalized_score == Decimal("0.00")
    bad = score.raw_value["calls"][0]
    assert bad["failure"] == "schema_mismatch"
    assert any("query" in e["path"] for e in bad["errors"])


def test_missing_name_flagged_distinctly(evaluator, ctx, schemas):
    payload = _calls({"arguments": "{}"})
    score = evaluator.evaluate(payload, {"schemas": schemas}, ctx)
    assert score.raw_value["calls"][0]["failure"] == "missing_or_empty_name"


def test_missing_arguments_flagged_distinctly(evaluator, ctx, schemas):
    payload = _calls({"name": "search"})
    score = evaluator.evaluate(payload, {"schemas": schemas}, ctx)
    assert score.raw_value["calls"][0]["failure"] == "missing_arguments"


def test_non_dict_call_flagged(evaluator, ctx, schemas):
    payload = _calls("just a string")
    score = evaluator.evaluate(payload, {"schemas": schemas}, ctx)
    assert score.raw_value["calls"][0]["failure"] == "call_not_an_object"


def test_arguments_already_decoded_accepted(evaluator, ctx, schemas):
    """Some providers emit `arguments` as a JSON object (not a string)."""
    payload = _calls({"name": "search", "arguments": {"query": "foo"}})
    score = evaluator.evaluate(payload, {"schemas": schemas}, ctx)
    assert score.normalized_score == Decimal("100.00")


def test_non_json_output_scores_0(evaluator, ctx, schemas):
    score = evaluator.evaluate("not json", {"schemas": schemas}, ctx)
    assert score.normalized_score == Decimal("0")
    assert "not valid JSON" in score.reason


def test_non_array_output_scores_0(evaluator, ctx, schemas):
    score = evaluator.evaluate('{"name": "search"}', {"schemas": schemas}, ctx)
    assert score.normalized_score == Decimal("0")
    assert "must be a JSON array" in score.reason


def test_empty_call_array_raises(evaluator, ctx, schemas):
    with pytest.raises(ValueError, match="non-empty call array"):
        evaluator.evaluate("[]", {"schemas": schemas}, ctx)


def test_missing_schemas_raises(evaluator, ctx):
    with pytest.raises(ValueError, match="expected\\['schemas'\\]"):
        evaluator.evaluate("[]", {}, ctx)


def test_empty_schemas_dict_raises(evaluator, ctx):
    with pytest.raises(ValueError, match="non-empty dict"):
        evaluator.evaluate("[]", {"schemas": {}}, ctx)


def test_invalid_tool_schema_raises(evaluator, ctx):
    with pytest.raises(ValueError, match="not a valid JSON Schema"):
        evaluator.evaluate(
            _calls(),
            {"schemas": {"x": {"type": "not-a-type"}}},
            ctx,
        )
