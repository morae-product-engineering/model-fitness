"""JsonSchemaEvaluator unit tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from mmfp.evaluators import get


@pytest.fixture
def evaluator():
    return get("json_schema")()


@pytest.fixture
def ctx():
    return {"dimension_id": "dim_test"}


@pytest.fixture
def person_schema():
    return {
        "type": "object",
        "required": ["name", "age"],
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer", "minimum": 0},
        },
        "additionalProperties": False,
    }


def test_passes_on_valid_json_matching_schema(evaluator, ctx, person_schema):
    score = evaluator.evaluate(
        '{"name": "Ada", "age": 207}', {"schema": person_schema}, ctx
    )
    assert score.passed is True
    assert score.normalized_score == Decimal("100")
    assert score.reason == "schema valid"
    assert score.raw_value == {"name": "Ada", "age": 207}


def test_fails_on_invalid_json(evaluator, ctx, person_schema):
    score = evaluator.evaluate("not json {", {"schema": person_schema}, ctx)
    assert score.passed is False
    assert score.normalized_score == Decimal("0")
    assert "not valid JSON" in score.reason
    assert "decode_error" in score.raw_value


def test_fails_on_missing_required_field(evaluator, ctx, person_schema):
    score = evaluator.evaluate(
        '{"name": "Ada"}', {"schema": person_schema}, ctx
    )
    assert score.passed is False
    assert "schema invalid" in score.reason
    assert any("age" in str(e["message"]) for e in score.raw_value["errors"])


def test_fails_on_wrong_type(evaluator, ctx, person_schema):
    score = evaluator.evaluate(
        '{"name": "Ada", "age": "old"}', {"schema": person_schema}, ctx
    )
    assert score.passed is False
    assert any(e["validator"] == "type" for e in score.raw_value["errors"])


def test_fails_on_additional_properties(evaluator, ctx, person_schema):
    score = evaluator.evaluate(
        '{"name": "Ada", "age": 207, "extra": "key"}',
        {"schema": person_schema},
        ctx,
    )
    assert score.passed is False


def test_invalid_schema_itself_raises_value_error(evaluator, ctx):
    with pytest.raises(ValueError, match="not a valid JSON Schema"):
        evaluator.evaluate(
            '{}',
            {"schema": {"type": "not-a-real-type"}},
            ctx,
        )


def test_missing_schema_key_raises(evaluator, ctx):
    with pytest.raises(ValueError, match="expected\\['schema'\\]"):
        evaluator.evaluate('{}', {}, ctx)


def test_top_level_array_validates(evaluator, ctx):
    score = evaluator.evaluate(
        '[1, 2, 3]',
        {"schema": {"type": "array", "items": {"type": "integer"}}},
        ctx,
    )
    assert score.passed is True


def test_passing_score_keeps_decoded_output_in_raw(evaluator, ctx):
    score = evaluator.evaluate(
        '{"k": 1}', {"schema": {"type": "object"}}, ctx
    )
    assert score.raw_value == {"k": 1}
