"""Judge-queue endpoints (MFP-75).

  GET  /api/products/{product}/judge-queue?status={pending|reviewed}
  POST /api/products/{product}/judge-queue/{sample_id}/mark

Samples are inserted by the matrix engine when an LLM-judge evaluator runs
(MFP-77). This router exposes them for curator review and persists decisions.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Annotated, Literal

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from mmfp.models.candidate import Candidate
from mmfp.persistence.judge_queue_repository import JudgeQueueRepository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["judge-queue"])

_PRODUCT_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class JudgeMarkRequest(BaseModel):
    decision: Literal["agree", "disagree"]
    note: str | None = None


class JudgeSampleResponse(BaseModel):
    id: str
    product: str
    tier_id: str
    example_id: str
    candidate_id: str
    model_output: str
    judge_score: float | None
    judge_reasoning: str | None
    decision: str
    note: str | None
    decided_at: str | None
    created_at: str


# ---------------------------------------------------------------------------
# Dependency providers
# ---------------------------------------------------------------------------


def get_judge_queue_repo() -> JudgeQueueRepository:
    db_path = Path(os.environ.get("MMFP_DB_PATH", "data/mmfp.db"))
    return JudgeQueueRepository(db_path)


def get_candidate_loader():
    products_dir = Path(os.environ.get("MMFP_PRODUCTS_DIR", "products"))

    def _load(product: str) -> list[Candidate]:
        slate_path = products_dir / product / "candidates.yaml"
        if not slate_path.exists():
            raise FileNotFoundError(f"candidates.yaml not found at {slate_path}")
        raw = yaml.safe_load(slate_path.read_text(encoding="utf-8"))
        return [Candidate.model_validate(c) for c in raw["candidates"]]

    return _load


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_product(product: str, candidate_loader) -> None:
    if not _PRODUCT_SLUG_RE.match(product):
        raise HTTPException(status_code=404, detail=f"Unknown product '{product}'")
    try:
        candidate_loader(product)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Unknown product '{product}'")


def _row_to_response(row: dict) -> JudgeSampleResponse:
    return JudgeSampleResponse(
        id=row["id"],
        product=row["product"],
        tier_id=row["tier_id"],
        example_id=row["example_id"],
        candidate_id=row["candidate_id"],
        model_output=row["model_output"],
        judge_score=row.get("judge_score"),
        judge_reasoning=row.get("judge_reasoning"),
        decision=row["decision"],
        note=row.get("note"),
        decided_at=row.get("decided_at"),
        created_at=row["created_at"],
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/api/products/{product}/judge-queue",
    response_model=list[JudgeSampleResponse],
    summary="List judge-queue samples for a product",
)
def list_judge_queue(
    product: str,
    status: str | None = Query(default=None, pattern="^(pending|reviewed)$"),
    repo: Annotated[JudgeQueueRepository, Depends(get_judge_queue_repo)] = None,
    candidate_loader: Annotated[object, Depends(get_candidate_loader)] = None,
) -> list[JudgeSampleResponse]:
    _validate_product(product, candidate_loader)
    rows = repo.list_samples(product, status=status)
    return [_row_to_response(r) for r in rows]


@router.post(
    "/api/products/{product}/judge-queue/{sample_id}/mark",
    response_model=JudgeSampleResponse,
    summary="Mark a judge-queue sample with a curator decision",
)
def mark_sample(
    product: str,
    sample_id: str,
    body: JudgeMarkRequest,
    repo: Annotated[JudgeQueueRepository, Depends(get_judge_queue_repo)] = None,
    candidate_loader: Annotated[object, Depends(get_candidate_loader)] = None,
) -> JudgeSampleResponse:
    _validate_product(product, candidate_loader)
    try:
        row = repo.mark(sample_id, product, body.decision, body.note)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Sample '{sample_id}' not found")
    return _row_to_response(row)
