"""Registry-level checks for the deterministic evaluators added in MLI-271.

The original deterministic trio (exact_match, json_schema, regex_match)
is implicitly verified by each evaluator's own test module via `get(name)`.
These explicit assertions exist because the MLI-271 batch adds five new
families simultaneously and the AC requires loadability from YAML by name.
"""

from __future__ import annotations

from mmfp.evaluators import get, names
from mmfp.evaluators.deterministic.confidence_calibration import (
    ConfidenceCalibrationEvaluator,
)
from mmfp.evaluators.deterministic.context_window_adequacy import (
    ContextWindowAdequacyEvaluator,
)
from mmfp.evaluators.deterministic.parse_rate import ParseRateEvaluator
from mmfp.evaluators.deterministic.query_correctness import (
    QueryCorrectnessEvaluator,
)
from mmfp.evaluators.deterministic.structured_output_reliability import (
    StructuredOutputReliabilityEvaluator,
)


def test_parse_rate_registered():
    assert "parse_rate" in names()
    assert get("parse_rate") is ParseRateEvaluator


def test_structured_output_reliability_registered():
    assert "structured_output_reliability" in names()
    assert get("structured_output_reliability") is StructuredOutputReliabilityEvaluator


def test_context_window_adequacy_registered():
    assert "context_window_adequacy" in names()
    assert get("context_window_adequacy") is ContextWindowAdequacyEvaluator


def test_confidence_calibration_registered():
    assert "confidence_calibration" in names()
    assert get("confidence_calibration") is ConfidenceCalibrationEvaluator


def test_query_correctness_registered():
    assert "query_correctness" in names()
    assert get("query_correctness") is QueryCorrectnessEvaluator
