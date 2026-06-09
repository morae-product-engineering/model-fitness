"""Drift-signals API endpoints (MFP-97).

Two routes:
  GET  /api/products/{product}/drift-signals
       Returns active DriftSignals for a product.
       Optional query param `candidate_id` narrows to one candidate.

  POST /api/products/{product}/drift-signals/{signal_id}/acknowledge
       Marks a signal as acknowledged; idempotent (repeating is a no-op).

Reads from DriftSignalStore only (P3: stable boundaries — no direct sensor
access). The read endpoint is side-effect free; acknowledge is idempotent.

DECISION for Wayne (MFP-97): acknowledge requires no rationale.
Acknowledge is an operational signal dismissal in the Monitor view, not a
promotion decision — it carries no audit-trail weight. Mirroring
promotion's rationale rule would create friction for a routine UI action.
Flag if the product needs a reason field added later.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from mmfp.persistence.drift_store import DriftSignalStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["drift"])


# ---------------------------------------------------------------------------
# Dependency provider
# ---------------------------------------------------------------------------


def get_drift_store() -> DriftSignalStore:
    """Provide a DriftSignalStore from MMFP_DB_PATH (or the default).

    Follows the ADR-0001 §"DB path source" pattern — wiring owns env-var
    resolution, not the route handler.
    """
    db_path = Path(os.environ.get("MMFP_DB_PATH", "data/mmfp.db"))
    return DriftSignalStore(db_path)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class DriftSignalItem(BaseModel):
    """A single active drift signal as returned by the list endpoint.

    Includes the store-assigned ``signal_id`` alongside the DriftSignal fields
    so callers can acknowledge the signal by ID.
    """

    signal_id: str
    product_id: str
    candidate_id: str
    tier_id: str
    baseline_run_id: str
    severity: str
    delta: str
    detected_at: str
    status: str
    summary: str


class DriftSignalListResponse(BaseModel):
    product: str
    signals: list[DriftSignalItem]


class AcknowledgeResponse(BaseModel):
    signal_id: str
    acknowledged: bool


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/api/products/{product}/drift-signals",
    response_model=DriftSignalListResponse,
    summary="Active drift signals for a product",
)
def list_drift_signals(
    product: str,
    store: Annotated[DriftSignalStore, Depends(get_drift_store)],
    candidate_id: str | None = Query(default=None),
) -> DriftSignalListResponse:
    """Return active drift signals for `product`, newest first.

    Optional ``candidate_id`` query param narrows results to a single
    candidate. Returns an empty list (not 404) when no active signals exist.
    Read-only; no side effects.
    """
    records = store.list_active_for_product(
        product_id=product, candidate_id=candidate_id
    )
    items = [
        DriftSignalItem(
            signal_id=sid,
            product_id=sig.product_id,
            candidate_id=sig.candidate_id,
            tier_id=sig.tier_id,
            baseline_run_id=sig.baseline_run_id,
            severity=sig.severity,
            delta=str(sig.delta),
            detected_at=sig.detected_at.isoformat(),
            status=sig.status,
            summary=sig.summary,
        )
        for sid, sig in records
    ]
    return DriftSignalListResponse(product=product, signals=items)


@router.post(
    "/api/products/{product}/drift-signals/{signal_id}/acknowledge",
    response_model=AcknowledgeResponse,
    summary="Acknowledge a drift signal",
)
def acknowledge_drift_signal(
    product: str,
    signal_id: str,
    store: Annotated[DriftSignalStore, Depends(get_drift_store)],
) -> AcknowledgeResponse:
    """Mark a drift signal as acknowledged.

    Idempotent — repeating for an already-acknowledged or unknown signal_id
    is a no-op and still returns 200. No rationale required (see module
    docstring for the decision).
    """
    store.acknowledge(signal_id)
    logger.info(
        "drift.signal_acknowledged",
        extra={"product": product, "signal_id": signal_id},
    )
    return AcknowledgeResponse(signal_id=signal_id, acknowledged=True)
