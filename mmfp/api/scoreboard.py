"""Scoreboard API endpoint — GET /api/products/{product}/scoreboard (MLI-174).

Returns the latest MatrixRun for a product as a per-tier ranked scorecard,
enriched with candidate metadata (display_name, family, deployment, status)
from the candidate slate in `products/{product}/candidates.yaml`.

Design decisions and trade-offs are recorded in the MLI-174 sub-task comments.
Key choices:
  - `list_for_product(product, limit=1)[0]` rather than a new
    `get_latest_for_product` helper — P1 "earn complexity"; MLI-184 (trends)
    will use `list_for_product(p, N)` and the surface is already minimal.
  - Product validation is the candidate-slate load; if the file doesn't exist
    the product is unknown. Slate is loaded anyway for enrichment so the check
    is free.
  - `MMFP_PRODUCTS_DIR` env var (default: `products/`) is a new convention
    introduced here. DB path follows the same pattern as MLI-258's ADR-0001.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Annotated

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from mmfp.models._common import UTCDatetime
from mmfp.models.candidate import (
    Candidate,
    CandidateFamily,
    CandidateStatus,
    TierId,
)
from mmfp.persistence import MatrixRunRepository
from mmfp.persistence.candidate_status import CandidateStatusStore
from mmfp.persistence.candidate_status import (
    get_candidate_status_store as _get_candidate_status_store,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["scoreboard"])

# All three tiers in the order the UI expects them.
_ALL_TIERS: list[TierId] = ["tier_1", "tier_2", "tier_3"]


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ScoreboardCandidate(BaseModel):
    candidate_id: str
    display_name: str
    family: CandidateFamily
    deployment: str
    status: CandidateStatus
    weighted_score: Decimal
    per_dimension: dict[str, Decimal]


class ScoreboardTier(BaseModel):
    tier_id: TierId
    candidates: list[ScoreboardCandidate]


class ScoreboardResponse(BaseModel):
    product: str
    run_id: str
    rubric_version: str
    started_at: UTCDatetime
    completed_at: UTCDatetime | None
    tiers: list[ScoreboardTier]


# ---------------------------------------------------------------------------
# Dependency providers
# ---------------------------------------------------------------------------


def get_repository() -> MatrixRunRepository:
    """Provide a `MatrixRunRepository` from MMFP_DB_PATH (or the default).

    The wiring layer (this function) owns env-var resolution, not the router
    handler — matches the ADR-0001 §"DB path source" pattern from MLI-258.
    """
    db_path = Path(os.environ.get("MMFP_DB_PATH", "data/mmfp.db"))
    return MatrixRunRepository(db_path)


def get_candidate_loader() -> Callable[[str], list[Candidate]]:
    """Provide a callable that loads a product's candidate slate.

    Caller receives `(product: str) -> list[Candidate]`.
    Raises `FileNotFoundError` if the slate YAML doesn't exist, which the
    route handler maps to a 404. The env var `MMFP_PRODUCTS_DIR` (default:
    `products/`) is a new convention introduced in MLI-174.
    """
    products_dir = Path(os.environ.get("MMFP_PRODUCTS_DIR", "products"))

    def _load(product: str) -> list[Candidate]:
        slate_path = products_dir / product / "candidates.yaml"
        if not slate_path.exists():
            raise FileNotFoundError(f"candidates.yaml not found at {slate_path}")
        raw = yaml.safe_load(slate_path.read_text(encoding="utf-8"))
        return [Candidate.model_validate(c) for c in raw["candidates"]]

    return _load


def get_candidate_status_store() -> CandidateStatusStore:
    """Thin no-args wrapper so FastAPI doesn't try to schema the ``clock``
    Callable parameter on the underlying factory (MLI-202). Tests override
    this symbol via ``dependency_overrides``."""
    return _get_candidate_status_store()


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.get(
    "/api/products/{product}/scoreboard",
    response_model=ScoreboardResponse,
    summary="Latest matrix run scoreboard for a product",
)
def get_scoreboard(
    product: str,
    repo: Annotated[MatrixRunRepository, Depends(get_repository)],
    candidate_loader: Annotated[
        Callable[[str], list[Candidate]], Depends(get_candidate_loader)
    ],
    status_store: Annotated[CandidateStatusStore, Depends(get_candidate_status_store)],
) -> ScoreboardResponse:
    """Return the latest MatrixRun for `product` as a ranked per-tier scorecard.

    404 if the product's candidate slate doesn't exist (unknown product) or
    if no matrix runs have been recorded for this product yet.

    Per-tier status overlay (MLI-202): for each (tier_id, candidate) the
    scoreboard looks up the durable status store. If a record exists its
    ``status`` is used; otherwise the candidate's seed status from
    candidates.yaml is the fallback. With an empty store (no overrides written)
    every lookup returns None and behaviour is unchanged from pre-MLI-202.
    """
    # Validate product by loading the slate — we need it anyway for enrichment,
    # so the existence check is free (P1: earn complexity).
    try:
        candidates = candidate_loader(product)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Unknown product '{product}'")

    runs = repo.list_for_product(product, limit=1)
    if not runs:
        raise HTTPException(
            status_code=404,
            detail=f"No matrix runs found for product '{product}'",
        )

    run = runs[0]

    # Build a lookup map for O(1) candidate enrichment.
    candidate_by_id: dict[str, Candidate] = {c.id: c for c in candidates}

    tiers: list[ScoreboardTier] = []
    for tier_id in _ALL_TIERS:
        scorecards = run.scores_for_tier(tier_id)
        sc_candidates: list[ScoreboardCandidate] = []
        for card in scorecards:
            cand = candidate_by_id.get(card.candidate_id)
            if cand is None:
                # Candidate was removed from the slate after the run was scored.
                # Include it with fallback values rather than silently dropping
                # scored data — the UI can surface an "(unknown)" badge.
                logger.warning(
                    "Scorecard references candidate not in slate",
                    extra={
                        "product": product,
                        "run_id": run.id,
                        "candidate_id": card.candidate_id,
                        "tier_id": tier_id,
                    },
                )
                sc_candidates.append(
                    ScoreboardCandidate(
                        candidate_id=card.candidate_id,
                        display_name=card.candidate_id,
                        family=CandidateFamily.CHAT,
                        deployment="(unknown)",
                        status=CandidateStatus.UNDER_EVALUATION,
                        weighted_score=card.weighted_score,
                        per_dimension=card.per_dimension,
                    )
                )
            else:
                # Overlay: use the durable status store's per-tier record when
                # present; fall back to the candidate's seed status otherwise.
                status_rec = status_store.get(
                    product=product,
                    tier_id=tier_id,
                    candidate=cand.binding.deployment,
                )
                effective_status = status_rec.status if status_rec else cand.status
                sc_candidates.append(
                    ScoreboardCandidate(
                        candidate_id=cand.id,
                        display_name=cand.display_name,
                        family=cand.family,
                        deployment=cand.binding.deployment,
                        status=effective_status,
                        weighted_score=card.weighted_score,
                        per_dimension=card.per_dimension,
                    )
                )
        tiers.append(ScoreboardTier(tier_id=tier_id, candidates=sc_candidates))

    return ScoreboardResponse(
        product=product,
        run_id=run.id,
        rubric_version=run.rubric_version,
        started_at=run.started_at,
        completed_at=run.completed_at,
        tiers=tiers,
    )
