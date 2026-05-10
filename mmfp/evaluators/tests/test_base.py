"""ABC contract tests for EvaluatorPlugin and the registry."""

from __future__ import annotations

from typing import Any

import pytest

from mmfp.evaluators import EvaluatorPlugin, get, names, register
from mmfp.evaluators._registry import _REGISTRY
from mmfp.models.matrix_run import EvaluatorScore, SourceField
from mmfp.plugins.evaluator import EvaluatorPlugin as ABCEvaluator


def test_evaluator_plugin_is_abstract():
    with pytest.raises(TypeError):
        EvaluatorPlugin()  # type: ignore[abstract]


def test_default_scores_field_is_content():
    assert EvaluatorPlugin.scores_field is SourceField.CONTENT


def test_three_deterministic_evaluators_registered():
    registered = set(names())
    assert {"exact_match", "json_schema", "regex_match"}.issubset(registered)


def test_get_returns_class_and_is_subclass_of_abc():
    for n in ("exact_match", "json_schema", "regex_match"):
        cls = get(n)
        assert issubclass(cls, ABCEvaluator)
        assert cls.name == n


def test_get_raises_keyerror_for_unknown():
    with pytest.raises(KeyError) as exc:
        get("definitely_not_a_real_evaluator")
    msg = str(exc.value)
    assert "exact_match" in msg
    assert "json_schema" in msg


def test_register_rejects_collision():
    @register
    class _A(ABCEvaluator):
        name = "_collision_test_evaluator"

        def evaluate(self, candidate_output, expected, context):
            raise NotImplementedError

    try:
        with pytest.raises(ValueError, match="already registered"):
            @register
            class _B(ABCEvaluator):  # noqa: F841
                name = "_collision_test_evaluator"

                def evaluate(self, candidate_output, expected, context):
                    raise NotImplementedError
    finally:
        _REGISTRY.pop("_collision_test_evaluator", None)


def test_register_idempotent_for_same_class():
    @register
    class _C(ABCEvaluator):
        name = "_idempotent_test_evaluator"

        def evaluate(self, candidate_output, expected, context):
            raise NotImplementedError

    try:
        # Re-registering the same class is a no-op.
        register(_C)
        assert get("_idempotent_test_evaluator") is _C
    finally:
        _REGISTRY.pop("_idempotent_test_evaluator", None)


def test_evaluator_must_stamp_source_field_on_score():
    """Every concrete evaluator's output carries its declared scores_field."""
    for n in ("exact_match", "json_schema", "regex_match"):
        cls = get(n)
        evaluator = cls()
        ctx: dict[str, Any] = {"dimension_id": "dim_x"}
        # Use minimal valid input per evaluator type.
        if n == "exact_match":
            score = evaluator.evaluate("hello", {"value": "hello"}, ctx)
        elif n == "json_schema":
            score = evaluator.evaluate("{}", {"schema": {"type": "object"}}, ctx)
        else:  # regex_match
            score = evaluator.evaluate("abc", {"pattern": "b"}, ctx)
        assert isinstance(score, EvaluatorScore)
        assert score.source_field == cls.scores_field


def test_deterministic_same_input_same_output():
    """Stability check: two calls with identical inputs return identical scores."""
    cls = get("exact_match")
    evaluator = cls()
    ctx: dict[str, Any] = {"dimension_id": "dim_x"}
    a = evaluator.evaluate("hello\n", {"value": "hello"}, ctx)
    b = evaluator.evaluate("hello\n", {"value": "hello"}, ctx)
    # model_dump because EvaluatorScore is a Pydantic model — equality is field-by-field.
    assert a.model_dump() == b.model_dump()


def test_evaluator_score_carries_evaluator_id_from_context():
    cls = get("exact_match")
    evaluator = cls()
    score = evaluator.evaluate(
        "x",
        {"value": "x"},
        {"dimension_id": "dim_a", "evaluator_id": "custom_id_42"},
    )
    assert score.evaluator_id == "custom_id_42"


def test_evaluator_score_defaults_evaluator_id_to_class_name():
    cls = get("exact_match")
    evaluator = cls()
    score = evaluator.evaluate("x", {"value": "x"}, {"dimension_id": "dim_a"})
    assert score.evaluator_id == "exact_match"


def test_missing_dimension_id_raises():
    cls = get("exact_match")
    evaluator = cls()
    with pytest.raises(ValueError, match="dimension_id"):
        evaluator.evaluate("x", {"value": "x"}, {})
