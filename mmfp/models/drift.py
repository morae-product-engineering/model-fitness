"""DriftSignal — the artefact a drift sensor produces (MFP-93).

A `DriftSignal` records that a *promoted* candidate's live behaviour on a tier
has diverged from the baseline matrix run it was promoted on. It is the shared
data shape every later Slice 7 sub-task (sampler, store, API, Monitor UI)
reads; this module defines the shape only — the concrete `DriftSensor` that
produces it lands in MFP-94+ under `mmfp.sensors.drift`.

The model is pure and serialisable: no IO, no wall-clock, no derived state.
A sensor computes `delta`, picks a `severity`, and stamps `detected_at`; the
model just validates and round-trips. Severity is carried as a value, not
computed here — the thresholds that map a `delta` to a band are the sensor's
configuration (see MFP-ADR-005), deliberately kept out of the data model so a
re-tuning of thresholds doesn't re-classify already-persisted signals.

Scoring convention: `baseline_score`, `observed_score`, and `delta` are on the
same 0–100 normalised scale the matrix engine emits (`EvaluatorScore.
normalized_score`). `delta = observed_score - baseline_score`, so a regression
is negative. This matches the MFP-92 acceptance test, which asserts a ~30-point
drop yields `delta ≈ -30` and `severity == "high"`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from mmfp.models._common import (
    MMFP_MODEL_CONFIG,
    SCHEMA_VERSION,
    SchemaVersion,
    UTCDatetime,
)

# Severity band a sensor assigns to a signal. "none" is included so a sensor
# may emit a recorded-but-immaterial observation; whether a sensor persists
# "none" signals or drops them is the sensor's call (MFP-94+), not the model's.
DriftSeverity = Literal["none", "low", "high"]

# Lifecycle of a signal. Signals start "active"; a human acknowledges one from
# the Monitor view (7.x). No "resolved" state in v1 — acknowledgement is the
# only operator action the slice scopes; a richer lifecycle is a later concern.
DriftStatus = Literal["active", "acknowledged"]


class DriftSignal(BaseModel):
    """A detected divergence of a promoted candidate from its baseline run.

    Pure data: constructed by a sensor, persisted by a store, rendered by the
    Monitor UI. No behaviour beyond validation.
    """

    model_config = MMFP_MODEL_CONFIG

    schema_version: SchemaVersion = SCHEMA_VERSION
    product_id: str = Field(
        min_length=1,
        description="Product whose promoted candidate this signal concerns",
    )
    candidate_id: str = Field(
        min_length=1,
        description="Promoted candidate that drifted, e.g. 'kimi-k2-6'",
    )
    tier_id: str = Field(
        min_length=1,
        description="Tier the drift was detected on, e.g. 'tier_1'",
    )
    baseline_run_id: str = Field(
        min_length=1,
        description="MatrixRun.id the candidate was promoted on (the baseline)",
    )
    baseline_score: Decimal = Field(
        ge=Decimal("0"),
        le=Decimal("100"),
        description="0–100 normalised baseline score for this candidate/tier",
    )
    observed_score: Decimal = Field(
        ge=Decimal("0"),
        le=Decimal("100"),
        description="0–100 normalised score from the live sample",
    )
    delta: Decimal = Field(
        description=(
            "Signed score change: observed_score - baseline_score. Negative is "
            "a regression. Bounded to [-100, 100] since both operands are 0–100."
        ),
        ge=Decimal("-100"),
        le=Decimal("100"),
    )
    severity: DriftSeverity = Field(
        description=(
            "Severity band the sensor assigned. The delta-to-band thresholds "
            "are sensor configuration, not part of this model — see MFP-ADR-005."
        ),
    )
    detected_at: UTCDatetime = Field(
        description="When the sensor detected the drift; tz-aware UTC",
    )
    status: DriftStatus = Field(
        default="active",
        description="Lifecycle state; signals start 'active' until acknowledged",
    )
    summary: str = Field(
        min_length=1,
        description=(
            "Human-readable one-line summary the Monitor view renders verbatim, "
            "e.g. 'kimi-k2-6 dropped 30 points on tier_1 vs baseline'."
        ),
    )
