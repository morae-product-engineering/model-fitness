"""DriftSensor — compares a live sample against a baseline run (MFP-95).

Implements the SensorPlugin interface (MFP-93 / MFP-ADR-005). Pure
comparison: given a baseline MatrixRun and a live sample, computes the
per-tier aggregate score delta and maps it to a severity band.

Severity thresholds (defaults, tunable per sensor instance):
    HIGH_THRESHOLD = 20  |delta| >= 20 → "high"
    LOW_THRESHOLD  = 10  |delta| >= 10 → "low"
    (|delta| <  10 → None, no material drift)

Thresholds are constructor parameters so they can be tuned per product
without re-classifying already-persisted signals (MFP-ADR-005 §3).

DECISION for Wayne (MFP-95): drift is measured on the aggregate score
per tier — the unweighted mean of all normalized_score values in the
live sample. Rationale: the baseline uses scores_for_tier() which
aggregates across dimensions, and the resulting 0–100 delta is the same
scale the Scoreboard shows, making it legible to a human reviewer.
Per-dimension drift (e.g. "accuracy held but latency spiked") would
require nominating a dimension at call-time, coupling the sensor to
rubric structure. Recommend aggregate for R1; flag for review if
per-dimension breakdown is wanted before the slice lands.

PARAMETER NAME NOTE: the SensorPlugin ABC (MFP-93) names the third
argument of detect() `live_samples` (plural). The MFP-92 acceptance
test calls detect() with `live_sample=` (singular). This implementation
uses `live_sample` to keep the acceptance test green without modifying
it. Python ABCs do not enforce parameter names at runtime, so the
boundary is satisfied. Align the name on review.

Re-export: the MFP-92 acceptance test does
    `from mmfp.sensors.drift import DriftSensor, DriftSignal`
DriftSignal's authoritative definition is mmfp.models.drift; we
re-export it here for that import path to work.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from mmfp.models.drift import DriftSignal
from mmfp.models.matrix_run import MatrixRun
from mmfp.plugins.sensor import LiveSample, LiveSampleSource, SensorPlugin

__all__ = ["DriftSensor", "DriftSignal", "NoCandidateBaselineError"]

_HIGH_THRESHOLD = Decimal("20")
_LOW_THRESHOLD = Decimal("10")


class NoCandidateBaselineError(ValueError):
    """No baseline results found for the requested candidate/tier."""


class DriftSensor(SensorPlugin):
    """Concrete drift sensor: aggregate-score comparison against a baseline run."""

    name = "drift"

    def __init__(
        self,
        *,
        product_id: str = "unknown",
        high_threshold: Decimal = _HIGH_THRESHOLD,
        low_threshold: Decimal = _LOW_THRESHOLD,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._product_id = product_id
        self._high = Decimal(str(high_threshold))
        self._low = Decimal(str(low_threshold))
        # ASSUMES: caller passes a clock that returns tz-aware UTC datetimes.
        self._clock = clock or (lambda: datetime.now(tz=timezone.utc))

    def sample(
        self,
        candidate_id: str,
        tier_id: str,
        source: LiveSampleSource,
    ) -> list[LiveSample]:
        """Delegate acquisition to the source (e.g. LangSmithSampler.fetch)."""
        return source.fetch(candidate_id=candidate_id, tier_id=tier_id)

    def detect(
        self,
        candidate_id: str,
        tier_id: str,
        baseline: MatrixRun,
        live_sample: list[Any],
    ) -> DriftSignal | None:
        """Compare live samples against the baseline; return a signal or None.

        Raises NoCandidateBaselineError when the baseline run has no results
        for the requested candidate/tier — a missing baseline is a typed error,
        not a silent pass.

        Returns None when the live sample is empty or the absolute delta falls
        below the low threshold (no material drift).
        """
        cards = baseline.scores_for_tier(tier_id)
        card = next((c for c in cards if c.candidate_id == candidate_id), None)
        if card is None:
            raise NoCandidateBaselineError(
                f"No baseline results for candidate '{candidate_id}' on tier "
                f"'{tier_id}' in run '{baseline.id}'"
            )

        if not live_sample:
            return None

        scores: list[Decimal] = []
        for s in live_sample:
            raw = (
                s.get("normalized_score") if isinstance(s, dict)
                else getattr(s, "normalized_score", None)
            )
            if raw is None:
                continue
            try:
                scores.append(Decimal(str(raw)))
            except InvalidOperation:
                pass

        if not scores:
            return None

        observed = sum(scores, Decimal("0")) / Decimal(len(scores))
        baseline_score = card.weighted_score
        delta = observed - baseline_score
        abs_delta = abs(delta)

        if abs_delta >= self._high:
            severity = "high"
        elif abs_delta >= self._low:
            severity = "low"
        else:
            return None

        direction = "dropped" if delta < 0 else "gained"
        summary = (
            f"{candidate_id} {direction} {abs(float(delta)):.0f} points "
            f"on {tier_id} vs baseline (run {baseline.id})"
        )

        return DriftSignal(
            product_id=self._product_id,
            candidate_id=candidate_id,
            tier_id=tier_id,
            baseline_run_id=baseline.id,
            baseline_score=baseline_score,
            observed_score=observed,
            delta=delta,
            severity=severity,
            detected_at=self._clock(),
            summary=summary,
        )
