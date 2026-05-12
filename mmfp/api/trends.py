"""Trends API endpoint — GET /api/products/{product}/trends (MLI-184).

Returns the last N MatrixRuns for a product, projected into a per-candidate
trend series for a single tier. Companion to the scoreboard endpoint
(MLI-174) which returns the latest run only.

Conventions follow `mmfp/api/scoreboard.py`:
  * Decimals serialise as JSON strings (Pydantic v2 default for `Decimal`).
  * Response DTO lives next to the router.
  * 404 distinguishes "unknown product" (no slate) from "no runs for product".
  * Repository and candidate-loader providers are reused from
    `scoreboard.py` rather than duplicated — single source of truth for the
    env-var resolution (`MMFP_DB_PATH`, `MMFP_PRODUCTS_DIR`).

Headless-before-UI (P9): all candidates with data in the window are returned;
any top-N candidate cap is a UI concern. Per the MLI-180 architectural
input, the `runs=N` parameter is the only cap.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from mmfp.api.scoreboard import get_candidate_loader, get_repository
from mmfp.models._common import UTCDatetime
from mmfp.models.candidate import (
    Candidate,
    CandidateFamily,
    CandidateStatus,
    TierId,
)
from mmfp.persistence import MatrixRunRepository

router = APIRouter(tags=["trends"])

_DEFAULT_RUNS = 10
_MAX_RUNS = 100


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class TrendRunRef(BaseModel):
    run_id: str
    rubric_version: str
    started_at: UTCDatetime
    completed_at: UTCDatetime | None


class TrendCandidatePoint(BaseModel):
    """One (candidate, run) datapoint. Aligns to a `TrendRunRef.run_id`."""

    run_id: str
    weighted_score: Decimal


class TrendCandidate(BaseModel):
    candidate_id: str
    display_name: str
    family: CandidateFamily
    deployment: str
    status: CandidateStatus
    points: list[TrendCandidatePoint]


class TrendsResponse(BaseModel):
    product: str
    tier_id: TierId
    runs: list[TrendRunRef]
    candidates: list[TrendCandidate]


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.get(
    "/api/products/{product}/trends",
    response_model=TrendsResponse,
    summary="Trend series for a tier across the last N matrix runs",
)
def get_trends(
    product: str,
    tier: Annotated[TierId, Query(description="Tier to project the trend for")],
    repo: Annotated[MatrixRunRepository, Depends(get_repository)],
    candidate_loader: Annotated[
        Callable[[str], list[Candidate]], Depends(get_candidate_loader)
    ],
    runs: Annotated[
        int,
        Query(
            ge=1,
            le=_MAX_RUNS,
            description="Number of most recent runs to include (newest first)",
        ),
    ] = _DEFAULT_RUNS,
) -> TrendsResponse:
    """Return up to `runs` most recent runs as a per-candidate trend series.

    404 if the product's candidate slate doesn't exist or if no matrix runs
    have been recorded for this product. Candidates without any data in the
    selected runs are omitted (rather than returned with empty series).
    """
    try:
        candidates = candidate_loader(product)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Unknown product '{product}'")

    matrix_runs = repo.list_for_product(product, limit=runs)
    if not matrix_runs:
        raise HTTPException(
            status_code=404,
            detail=f"No matrix runs found for product '{product}'",
        )

    candidate_by_id: dict[str, Candidate] = {c.id: c for c in candidates}

    # Collect (run_id -> {candidate_id -> weighted_score}) for the tier.
    scores_per_run: dict[str, dict[str, Decimal]] = {}
    for run in matrix_runs:
        per_candidate: dict[str, Decimal] = {}
        for card in run.scores_for_tier(tier):
            per_candidate[card.candidate_id] = card.weighted_score
        scores_per_run[run.id] = per_candidate

    # Per-candidate points, in the same order as `matrix_runs` (newest first).
    points_by_candidate: dict[str, list[TrendCandidatePoint]] = defaultdict(list)
    for run in matrix_runs:
        for cid, score in scores_per_run[run.id].items():
            points_by_candidate[cid].append(
                TrendCandidatePoint(run_id=run.id, weighted_score=score)
            )

    # Build candidate output. Sort by the newest run's score desc — runs are
    # newest-first, so `points[0]` is the latest available datapoint.
    out_candidates: list[TrendCandidate] = []
    for cid, points in points_by_candidate.items():
        cand = candidate_by_id.get(cid)
        if cand is None:
            # Scored but no slate entry — fall back like the scoreboard does.
            out_candidates.append(
                TrendCandidate(
                    candidate_id=cid,
                    display_name=cid,
                    family=CandidateFamily.CHAT,
                    deployment="(unknown)",
                    status=CandidateStatus.UNDER_EVALUATION,
                    points=points,
                )
            )
        else:
            out_candidates.append(
                TrendCandidate(
                    candidate_id=cand.id,
                    display_name=cand.display_name,
                    family=cand.family,
                    deployment=cand.binding.deployment,
                    status=cand.status,
                    points=points,
                )
            )

    out_candidates.sort(key=lambda c: c.points[0].weighted_score, reverse=True)

    run_refs = [
        TrendRunRef(
            run_id=run.id,
            rubric_version=run.rubric_version,
            started_at=run.started_at,
            completed_at=run.completed_at,
        )
        for run in matrix_runs
    ]

    return TrendsResponse(
        product=product,
        tier_id=tier,
        runs=run_refs,
        candidates=out_candidates,
    )
