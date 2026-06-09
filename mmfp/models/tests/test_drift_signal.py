"""Unit tests for `DriftSignal` (MFP-93).

Pin the model's contract: a well-formed signal validates, an unknown field is
rejected (`extra="forbid"`), the model round-trips through JSON, and a dumped
instance conforms to the published `schemas/v1/driftsignal.json`.

Deterministic — fixed UTC datetime, no `datetime.now()`, no RNG. NOT marked
`slice_acceptance`: these gate this sub-task, not the Slice 7 implementation.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from mmfp.models.drift import DriftSignal

# A 30-point regression on tier_1 — the MFP-92 acceptance scenario, "high".
_DETECTED_AT = datetime(2026, 6, 9, 12, 0, 0, tzinfo=timezone.utc)
_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schemas" / "v1" / "driftsignal.json"


def _well_formed_signal() -> DriftSignal:
    return DriftSignal(
        product_id="contract-triage",
        candidate_id="kimi-k2-6",
        tier_id="tier_1",
        baseline_run_id="baseline-run-0001",
        baseline_score=Decimal("85"),
        observed_score=Decimal("55"),
        delta=Decimal("-30"),
        severity="high",
        detected_at=_DETECTED_AT,
        status="active",
        summary="kimi-k2-6 dropped 30 points on tier_1 vs baseline",
    )


def test_drift_signal_well_formed() -> None:
    signal = _well_formed_signal()

    assert signal.product_id == "contract-triage"
    assert signal.candidate_id == "kimi-k2-6"
    assert signal.tier_id == "tier_1"
    assert signal.baseline_run_id == "baseline-run-0001"
    assert signal.baseline_score == Decimal("85")
    assert signal.observed_score == Decimal("55")
    assert signal.delta == Decimal("-30")
    assert signal.severity == "high"
    assert signal.detected_at == _DETECTED_AT
    assert signal.status == "active"
    assert signal.summary != ""
    # schema_version follows the _common convention for persisted models.
    assert signal.schema_version == "v1"


def test_drift_signal_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        DriftSignal(
            product_id="contract-triage",
            candidate_id="kimi-k2-6",
            tier_id="tier_1",
            baseline_run_id="baseline-run-0001",
            baseline_score=Decimal("85"),
            observed_score=Decimal("55"),
            delta=Decimal("-30"),
            severity="high",
            detected_at=_DETECTED_AT,
            summary="…",
            unexpected_field="boom",  # type: ignore[call-arg]
        )


def test_drift_signal_round_trips_json() -> None:
    original = _well_formed_signal()

    restored = DriftSignal.model_validate_json(original.model_dump_json())

    assert restored == original


def test_drift_signal_conforms_to_published_schema() -> None:
    """A dumped signal validates against `schemas/v1/driftsignal.json`.

    Closes the AC "the model validates against it in a test" — guards against
    the hand-maintained schema drifting from the Pydantic model.
    """
    import jsonschema

    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    instance = json.loads(_well_formed_signal().model_dump_json())

    jsonschema.validate(instance=instance, schema=schema)
