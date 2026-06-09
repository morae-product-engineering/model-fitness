# @jira: MFP-92 (Slice 7 acceptance test — drift detection)
#
# Slice 7 acceptance test (sensor side). Deliberately RED until the Slice 7
# implementation sub-tasks (MFP-93+) land. It pins the *behaviour* of drift
# detection — a promoted candidate whose live sample diverges from its baseline
# matrix run produces a drift signal whose severity reflects the magnitude of
# the drop — without freezing the SensorPlugin signature (see PROPOSED block
# below, which the test does NOT assert).
#
# The `slice_acceptance` marker keeps this out of the standard unit-test job
# (`-m "not slice_acceptance"`); a separate soft-fail CI job runs it so the
# deliberate red doesn't block downstream pipelines.
#
# Expected failure modes worth recognising for "why is this red?":
#   - `mmfp.sensors.drift` does not exist yet → the deferred import inside the
#     test body raises ModuleNotFoundError → the test FAILS at call time. This
#     is the first red driver and the intended state until MFP-93 lands.
#   - Once the module exists but `DriftSignal` / `DriftSensor` are stubs, the
#     test reds on the severity / delta assertions instead — still correct
#     deliberate-red, now pinning the contract rather than the module's
#     existence.
# Both are assertion/import-time failures in the test body, NOT collection-time
# errors: the not-yet-existent symbols are imported inside the test, never at
# module top-level, so the file collects cleanly and `-m` filtering works.
#
# Determinism: baseline and live sample are inline fixtures (no external files,
# no network, no wall-clock, no RNG). Same inputs → same DriftSignal.
#
# PROPOSED SensorPlugin interface (for MFP-93 review — NOT asserted here):
#   class SensorPlugin(ABC):
#       name: ClassVar[str]
#       @abstractmethod
#       def sample(
#           self, candidate_id: str, tier_id: str, source: LiveSampleSource
#       ) -> list[LiveSample]: ...
#       @abstractmethod
#       def detect(
#           self,
#           candidate_id: str,
#           tier_id: str,
#           baseline: MatrixRun,
#           live_samples: list[LiveSample],
#       ) -> DriftSignal | None: ...
#
#   Inputs:  candidate_id + tier_id (from the CandidateStatus store, scoping
#            detection to a promoted candidate on a specific tier); the baseline
#            MatrixRun the candidate was promoted on; a LiveSampleSource
#            (seeded fixture in R1, live telemetry later).
#   Output:  DriftSignal | None — None when no material drift is detected.
#   ASSUMES: severity thresholds are configuration, not hardcoded in the sensor;
#            this proposal needs Wayne's sign-off before MFP-93 implements it.
#
# This test asserts behaviour, not the signature above. It invokes the sensor
# the simplest way a green implementation could support — `DriftSensor().detect(
# baseline=..., live_sample=..., candidate_id=..., tier_id=...)` — and pins the
# DriftSignal shape (candidate_id, tier_id, severity, delta, summary). MFP-93 is
# free to settle the exact entrypoint; if it diverges from this call, update
# this test in the same PR that lands the implementation.
from decimal import Decimal

import pytest

from mmfp.models.matrix_run import (
    EvaluatorScore,
    MatrixRun,
    MatrixRunResult,
)

pytestmark = pytest.mark.slice_acceptance

# --- Inline fixtures (deterministic; no external files, no network) ----------

_BASELINE_CANDIDATE = "kimi-k2-6"
_BASELINE_TIER = "tier_1"
_RUBRIC_VERSION = "v0.1"
# Baseline scored ~85 on tier_1; the live sample comes back ~55 — a 30-point
# drop, comfortably inside the "high" severity band (>= 20-point drop).
_BASELINE_SCORE = Decimal("85")
_LIVE_SCORE = Decimal("55")
_DIMENSION = "classification_accuracy"


def _baseline_run() -> "MatrixRun":
    """A MatrixRun where the promoted candidate scored ~85 on tier_1.

    Two examples at the baseline score so `scores_for_tier` aggregates to a
    stable 85 mean — no tie, no rounding ambiguity.
    """
    from datetime import datetime, timezone

    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    results = [
        MatrixRunResult(
            tier_id=_BASELINE_TIER,
            candidate_id=_BASELINE_CANDIDATE,
            dataset_id="r1-classification",
            example_id=f"ex-{i}",
            score=EvaluatorScore(
                dimension_id=_DIMENSION,
                evaluator_id="exact_match",
                raw_value=1.0,
                normalized_score=_BASELINE_SCORE,
            ),
        )
        for i in range(2)
    ]
    return MatrixRun(
        id="baseline-run-0001",
        rubric_version=_RUBRIC_VERSION,
        started_at=started,
        completed_at=started,
        results=results,
    )


def _live_sample() -> list[dict]:
    """The diverging live sample as EvaluatorScore-like dicts (~55).

    Dicts, not EvaluatorScore instances: a live-sample source produces loosely
    shaped telemetry, and pinning the sensor to a concrete model here would
    overconstrain the MFP-93 LiveSample shape. The sensor's job is to coerce.
    """
    return [
        {
            "dimension_id": _DIMENSION,
            "candidate_id": _BASELINE_CANDIDATE,
            "tier_id": _BASELINE_TIER,
            "normalized_score": str(_LIVE_SCORE),
        }
        for _ in range(2)
    ]


# --- The acceptance test ------------------------------------------------------


def test_drift_sensor_emits_high_severity_for_large_drop():
    # Deferred import: `mmfp.sensors.drift` does not exist until MFP-93 lands.
    # Importing here (not at module top-level) keeps collection clean so the
    # `slice_acceptance` marker can deselect this in the standard unit job.
    from mmfp.sensors.drift import DriftSensor, DriftSignal

    baseline = _baseline_run()
    live = _live_sample()

    signal = DriftSensor().detect(
        candidate_id=_BASELINE_CANDIDATE,
        tier_id=_BASELINE_TIER,
        baseline=baseline,
        live_sample=live,
    )

    # A 30-point drop is material drift — the sensor must emit a signal.
    assert signal is not None
    assert isinstance(signal, DriftSignal)

    # The signal identifies the promoted candidate and tier it concerns.
    assert signal.candidate_id == _BASELINE_CANDIDATE
    assert signal.tier_id == _BASELINE_TIER

    # Severity reflects magnitude: a >= 20-point drop is "high".
    assert signal.severity == "high"

    # `delta` is the signed score change (negative = regression). ~ -30 here.
    # Compared loosely so a green implementation may carry float or Decimal.
    assert signal.delta < 0
    assert abs(float(signal.delta) - (-30.0)) < 1.0

    # A human-readable summary the Monitor view can render verbatim.
    assert isinstance(signal.summary, str)
    assert signal.summary != ""
