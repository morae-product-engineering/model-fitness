"""Drift signals API — GET /api/products/{product}/drift/signals (MFP-92).

Read-only endpoint that lists drift signals for a product from the local
file store. Signals are JSON files under MMFP_DRIFT_DIR (default: data/drift).

Store layout:
  <MMFP_DRIFT_DIR>/<product>/signals/<id>.json  — one file per signal

The endpoint filters by ``status`` query param (default: "active").
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["drift"])


class DriftSignalRow(BaseModel):
    candidate_id: str
    tier_id: str
    severity: str
    status: str
    summary: str
    delta: str
    detected_at: str


class DriftSignalsResponse(BaseModel):
    signals: list[DriftSignalRow]
    active_count: int


def _signals_dir(product: str) -> Path:
    drift_root = Path(os.environ.get("MMFP_DRIFT_DIR", "data/drift"))
    return drift_root / product / "signals"


@router.get(
    "/api/products/{product}/drift/signals",
    response_model=DriftSignalsResponse,
    summary="List drift signals for a product",
)
def get_drift_signals(product: str, status: str = "active") -> DriftSignalsResponse:
    """Return drift signals, optionally filtered by status (default: active)."""
    signals_dir = _signals_dir(product)
    if not signals_dir.exists():
        return DriftSignalsResponse(signals=[], active_count=0)

    rows: list[DriftSignalRow] = []
    for path in sorted(signals_dir.glob("*.json")):
        try:
            data: dict = json.loads(path.read_text(encoding="utf-8"))
            row = DriftSignalRow(
                candidate_id=str(data["candidate_id"]),
                tier_id=str(data["tier_id"]),
                severity=str(data["severity"]),
                status=str(data["status"]),
                summary=str(data["summary"]),
                delta=str(data["delta"]),
                detected_at=str(data["detected_at"]),
            )
            if status == "all" or row.status == status:
                rows.append(row)
        except (KeyError, ValueError, json.JSONDecodeError):
            continue

    active_count = sum(1 for r in rows if r.status == "active")
    return DriftSignalsResponse(signals=rows, active_count=active_count)
