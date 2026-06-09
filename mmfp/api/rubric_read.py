"""Rubric read endpoint — GET /api/products/{product}/rubric (MLI-195, MLI-365).

Read-only counterpart to the PUT endpoint in ``rubric_write.py`` (MLI-273,
reconciled in MLI-194). Added in MLI-195 because the UI container cannot
read the YAML directly (it talks to the API over HTTP) and no GET for the
full rubric dict existed.

Architectural context (MLI-190 normalisation-boundary note):
  The Editor needs the full rubric dict — including ``evaluator_config``
  and ``gates`` — so it can POST the dict verbatim to preview-impact and
  PUT it verbatim to the write endpoint. Returning ``model_dump(mode="json")``
  round-trips cleanly through ``Rubric.model_validate`` because the model
  uses ``extra="forbid"``, which means the serialised form is exactly the
  schema the write endpoint expects.

MLI-365: reads go through ``rubric_store`` (the same durable store the write
endpoint persists to), not directly off disk. This is what makes a saved
rubric visible after a revision restart — the GET reflects the durable blob,
so the Editor's version readout increments and persists.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from mmfp.api.rubric_store import AuditRecord, RubricNotFound, RubricStore, get_rubric_store
from mmfp.models.rubric import Rubric

router = APIRouter(tags=["rubric"])


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


class RubricReadResponse(BaseModel):
    product: str
    version: str
    rubric: dict[str, Any]


class RubricAuditResponse(BaseModel):
    product: str
    entries: list[AuditRecord]


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.get(
    "/api/products/{product}/rubric",
    response_model=RubricReadResponse,
    summary="Read a product's current rubric",
)
def get_rubric(
    product: str,
    store: Annotated[RubricStore, Depends(get_rubric_store)],
) -> RubricReadResponse:
    """Return the full rubric dict for ``product``.

    The ``rubric`` field is serialised via ``model_dump(mode="json")`` so it
    round-trips through ``Rubric.model_validate`` cleanly — the Editor posts
    this dict straight back to preview-impact and PUT without re-serialising
    field-by-field (which would drop ``evaluator_config`` and other
    passthrough fields).

    Error states:
      * 404 — the product has no rubric in the store (unknown product).
    """
    try:
        raw, _version = store.load(product)
    except RubricNotFound:
        raise HTTPException(status_code=404, detail=f"Unknown product '{product}'")

    # Validate-then-dump so the returned dict is exactly the schema the write
    # and preview endpoints expect (round-trips through Rubric.model_validate).
    rubric = Rubric.model_validate(raw)
    return RubricReadResponse(
        product=product,
        version=rubric.version,
        rubric=rubric.model_dump(mode="json"),
    )


@router.get(
    "/api/products/{product}/rubric-audit",
    response_model=RubricAuditResponse,
    summary="List rubric save events for a product, newest-first",
)
def get_rubric_audit(
    product: str,
    store: Annotated[RubricStore, Depends(get_rubric_store)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> RubricAuditResponse:
    """Return the most recent rubric save audit records for ``product``.

    Each entry captures the version delta, note, steward identity, and
    timestamp of one rubric save. Empty list when no saves have been made yet.
    """
    entries = store.list_audit(product, limit=limit)
    return RubricAuditResponse(product=product, entries=entries)
