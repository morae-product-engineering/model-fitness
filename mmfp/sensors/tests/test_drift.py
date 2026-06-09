"""Unit tests for DriftSensor (MFP-95).

Regular unit tests — NOT slice_acceptance — so they run in the standard
pytest job. The slice acceptance test that gates the whole slice lives in
test_drift_sensor.py (MFP-92).

Coverage:
- Boundary cases for both severity thresholds (at, just-below, just-above).
- Missing baseline → NoCandidateBaselineError.
- Empty live sample → None.
- Signal shape (delta, candidate_id, tier_id, baseline_run_id, summary).
- Custom thresholds.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from mmfp.models.matrix_run import EvaluatorScore, MatrixRun, MatrixRunResult
from mmfp.sensors.drift import DriftSensor, NoCandidateBaselineError

_FIXED_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
_STARTED = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _clock() -> datetime:
    return _FIXED_NOW


def _make_run(
    candidate_id: str,
    tier_id: str,
    score: Decimal,
    *,
    run_id: str = "run-001",
    dimension_id: str = "dim_accuracy",
) -> MatrixRun:
    result = MatrixRunResult(
        tier_id=tier_id,
        candidate_id=candidate_id,
        dataset_id="ds-test",
        example_id="ex-0",
        score=EvaluatorScore(
            dimension_id=dimension_id,
            evaluator_id="exact_match",
            raw_value=1.0,
            normalized_score=score,
        ),
    )
    return MatrixRun(
        id=run_id,
        rubric_version="v0.1",
        started_at=_STARTED,
        completed_at=_STARTED,
        results=[result],
    )


def _sample(candidate_id: str, tier_id: str, score: Decimal) -> list[dict]:
    return [
        {
            "candidate_id": candidate_id,
            "tier_id": tier_id,
            "dimension_id": "dim_accuracy",
            "normalized_score": str(score),
        }
    ]


# --- No divergence -----------------------------------------------------------


def test_identical_score_returns_none():
    sensor = DriftSensor(clock=_clock)
    baseline = _make_run("cand-a", "tier_1", Decimal("80"))
    live = _sample("cand-a", "tier_1", Decimal("80"))
    assert sensor.detect("cand-a", "tier_1", baseline, live) is None


def test_drop_below_low_threshold_returns_none():
    """A 5-point drop (< low threshold of 10) is not material."""
    sensor = DriftSensor(clock=_clock)
    baseline = _make_run("cand-a", "tier_1", Decimal("80"))
    live = _sample("cand-a", "tier_1", Decimal("75"))
    assert sensor.detect("cand-a", "tier_1", baseline, live) is None


# --- Low severity boundary ---------------------------------------------------


def test_exact_low_threshold_yields_low():
    """A 10-point drop (exactly at threshold) → 'low'."""
    sensor = DriftSensor(clock=_clock)
    baseline = _make_run("cand-a", "tier_1", Decimal("80"))
    live = _sample("cand-a", "tier_1", Decimal("70"))
    signal = sensor.detect("cand-a", "tier_1", baseline, live)
    assert signal is not None
    assert signal.severity == "low"
    assert signal.delta < 0


def test_drop_between_low_and_high_yields_low():
    """A 15-point drop (>= 10 but < 20) → 'low'."""
    sensor = DriftSensor(clock=_clock)
    baseline = _make_run("cand-a", "tier_1", Decimal("80"))
    live = _sample("cand-a", "tier_1", Decimal("65"))
    signal = sensor.detect("cand-a", "tier_1", baseline, live)
    assert signal is not None
    assert signal.severity == "low"


# --- High severity boundary --------------------------------------------------


def test_exact_high_threshold_yields_high():
    """A 20-point drop (exactly at threshold) → 'high'."""
    sensor = DriftSensor(clock=_clock)
    baseline = _make_run("cand-a", "tier_1", Decimal("80"))
    live = _sample("cand-a", "tier_1", Decimal("60"))
    signal = sensor.detect("cand-a", "tier_1", baseline, live)
    assert signal is not None
    assert signal.severity == "high"


def test_large_drop_yields_high():
    """A 30-point drop → 'high'; mirrors the MFP-92 acceptance test fixture."""
    sensor = DriftSensor(clock=_clock)
    baseline = _make_run("cand-a", "tier_1", Decimal("85"))
    live = _sample("cand-a", "tier_1", Decimal("55"))
    signal = sensor.detect("cand-a", "tier_1", baseline, live)
    assert signal is not None
    assert signal.severity == "high"
    assert signal.delta < 0
    assert abs(float(signal.delta) - (-30.0)) < 1.0


# --- Missing baseline --------------------------------------------------------


def test_missing_baseline_raises_typed_error():
    """Candidate absent from baseline run → NoCandidateBaselineError."""
    sensor = DriftSensor(clock=_clock)
    baseline = _make_run("other-cand", "tier_1", Decimal("80"))
    live = _sample("cand-a", "tier_1", Decimal("50"))
    with pytest.raises(NoCandidateBaselineError, match="cand-a"):
        sensor.detect("cand-a", "tier_1", baseline, live)


def test_missing_tier_raises_typed_error():
    """Tier absent from baseline run → NoCandidateBaselineError."""
    sensor = DriftSensor(clock=_clock)
    baseline = _make_run("cand-a", "tier_2", Decimal("80"))
    live = _sample("cand-a", "tier_1", Decimal("50"))
    with pytest.raises(NoCandidateBaselineError, match="tier_1"):
        sensor.detect("cand-a", "tier_1", baseline, live)


# --- Empty live sample -------------------------------------------------------


def test_empty_live_sample_returns_none():
    """No live data → no signal (not an error)."""
    sensor = DriftSensor(clock=_clock)
    baseline = _make_run("cand-a", "tier_1", Decimal("80"))
    assert sensor.detect("cand-a", "tier_1", baseline, []) is None


# --- Signal shape ------------------------------------------------------------


def test_signal_carries_expected_fields():
    """Emitted signal correctly populates all required DriftSignal fields."""
    sensor = DriftSensor(product_id="mmfp-test", clock=_clock)
    baseline = _make_run("cand-a", "tier_1", Decimal("85"), run_id="run-xyz")
    live = _sample("cand-a", "tier_1", Decimal("55"))
    signal = sensor.detect("cand-a", "tier_1", baseline, live)
    assert signal is not None
    assert signal.product_id == "mmfp-test"
    assert signal.candidate_id == "cand-a"
    assert signal.tier_id == "tier_1"
    assert signal.baseline_run_id == "run-xyz"
    assert signal.baseline_score == Decimal("85")
    assert signal.observed_score == Decimal("55")
    assert signal.delta == Decimal("55") - Decimal("85")
    assert signal.severity == "high"
    assert signal.detected_at == _FIXED_NOW
    assert signal.status == "active"
    assert "cand-a" in signal.summary
    assert "tier_1" in signal.summary


def test_summary_mentions_direction_and_magnitude():
    """Summary says 'dropped' and rounds the magnitude."""
    sensor = DriftSensor(clock=_clock)
    baseline = _make_run("my-model", "tier_1", Decimal("85"))
    live = _sample("my-model", "tier_1", Decimal("55"))
    signal = sensor.detect("my-model", "tier_1", baseline, live)
    assert signal is not None
    assert "dropped" in signal.summary
    assert "30" in signal.summary


# --- Custom thresholds -------------------------------------------------------


def test_custom_high_threshold():
    """Sensor with high_threshold=15 classifies a 15-point drop as 'high'."""
    sensor = DriftSensor(high_threshold=Decimal("15"), low_threshold=Decimal("5"), clock=_clock)
    baseline = _make_run("cand-a", "tier_1", Decimal("80"))
    live = _sample("cand-a", "tier_1", Decimal("65"))  # 15-point drop
    signal = sensor.detect("cand-a", "tier_1", baseline, live)
    assert signal is not None
    assert signal.severity == "high"


def test_custom_low_threshold():
    """Sensor with low_threshold=5 classifies a 7-point drop as 'low'."""
    sensor = DriftSensor(high_threshold=Decimal("20"), low_threshold=Decimal("5"), clock=_clock)
    baseline = _make_run("cand-a", "tier_1", Decimal("80"))
    live = _sample("cand-a", "tier_1", Decimal("73"))  # 7-point drop
    signal = sensor.detect("cand-a", "tier_1", baseline, live)
    assert signal is not None
    assert signal.severity == "low"


# --- Aggregate scoring -------------------------------------------------------


def test_aggregate_across_multiple_samples():
    """Observed score is the mean across all live samples."""
    sensor = DriftSensor(clock=_clock)
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    baseline = MatrixRun(
        id="run-001",
        rubric_version="v0.1",
        started_at=started,
        completed_at=started,
        results=[
            MatrixRunResult(
                tier_id="tier_1",
                candidate_id="cand-a",
                dataset_id="ds",
                example_id=f"ex-{i}",
                score=EvaluatorScore(
                    dimension_id="dim_a",
                    evaluator_id="em",
                    raw_value=1.0,
                    normalized_score=Decimal("80"),
                ),
            )
            for i in range(2)
        ],
    )
    # Two samples averaging to 55 → delta = -25 → high
    live = [
        {"candidate_id": "cand-a", "tier_id": "tier_1", "dimension_id": "dim_a",
         "normalized_score": "50"},
        {"candidate_id": "cand-a", "tier_id": "tier_1", "dimension_id": "dim_a",
         "normalized_score": "60"},
    ]
    signal = sensor.detect("cand-a", "tier_1", baseline, live)
    assert signal is not None
    assert signal.observed_score == Decimal("55")
    assert signal.severity == "high"
