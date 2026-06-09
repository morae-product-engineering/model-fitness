# Tests for judge evaluator factory wiring (MFP-77).
#
# Covers _make_judge_evaluator_factory: the function that builds a custom
# evaluator factory for the CLI when the rubric's judge config points at
# azure_foundry. All tests mock the binding registry so no real Azure
# connections are attempted.

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mmfp.cli.__main__ import _make_judge_evaluator_factory
from mmfp.models.rubric import JudgeConfig, Rubric


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rubric_with_judge(**kwargs) -> JudgeConfig:
    """Build a JudgeConfig with azure_foundry defaults; override via kwargs."""
    defaults = {
        "model": "gpt-4o",
        "provider": "azure_foundry",
        "deployment": "gpt-4o",
        "endpoint": "https://mmfp-dev-models-resource.cognitiveservices.azure.com",
        "version_pin": "2024-12-01-preview",
        "calibration_set": "products/mli/datasets/judge_calibration.jsonl",
    }
    defaults.update(kwargs)
    return JudgeConfig(**defaults)


# ---------------------------------------------------------------------------
# Returns None paths
# ---------------------------------------------------------------------------


def test_make_judge_factory_returns_none_for_non_azure_provider() -> None:
    cfg = _rubric_with_judge(provider="anthropic")
    rubric = MagicMock()
    rubric.judge = cfg

    result = _make_judge_evaluator_factory(rubric)

    assert result is None


def test_make_judge_factory_returns_none_when_deployment_missing() -> None:
    cfg = _rubric_with_judge(deployment=None)
    rubric = MagicMock()
    rubric.judge = cfg

    result = _make_judge_evaluator_factory(rubric)

    assert result is None


def test_make_judge_factory_returns_none_when_endpoint_missing() -> None:
    cfg = _rubric_with_judge(endpoint=None)
    rubric = MagicMock()
    rubric.judge = cfg

    result = _make_judge_evaluator_factory(rubric)

    assert result is None


# ---------------------------------------------------------------------------
# Returns factory path
# ---------------------------------------------------------------------------


@patch("mmfp.bindings._registry.get")
def test_make_judge_factory_returns_callable_for_azure_foundry(mock_get) -> None:
    mock_get.return_value = lambda: MagicMock()
    cfg = _rubric_with_judge()
    rubric = MagicMock()
    rubric.judge = cfg

    result = _make_judge_evaluator_factory(rubric)

    assert callable(result)


@patch("mmfp.bindings._registry.get")
def test_judge_factory_returns_llm_judge_evaluator(mock_get) -> None:
    from mmfp.evaluators.inferential.llm_judge import LLMJudgeEvaluator

    mock_get.return_value = lambda: MagicMock()
    cfg = _rubric_with_judge()
    rubric = MagicMock()
    rubric.judge = cfg

    factory = _make_judge_evaluator_factory(rubric)
    assert factory is not None

    evaluator = factory("llm_judge_synthesis_quality")

    assert isinstance(evaluator, LLMJudgeEvaluator)
    assert evaluator._binding is not None
    assert evaluator._judge_candidate is not None


@patch("mmfp.bindings._registry.get")
def test_judge_factory_delegates_non_judge_names(mock_get) -> None:
    mock_binding = MagicMock()
    mock_get.return_value = lambda: mock_binding

    cfg = _rubric_with_judge()
    rubric = MagicMock()
    rubric.judge = cfg

    factory = _make_judge_evaluator_factory(rubric)
    assert factory is not None

    # For a non-judge evaluator name, it should call evaluator_registry.get()
    with patch("mmfp.evaluators._registry.get") as mock_eval_get:
        stub_evaluator = MagicMock()
        mock_eval_get.return_value = lambda: stub_evaluator

        result = factory("exact_match")

        mock_eval_get.assert_called_once_with("exact_match")
        assert result is stub_evaluator
