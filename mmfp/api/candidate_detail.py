"""Candidate detail API endpoint —
GET /api/products/{product}/candidates/{deployment_name} (MLI-184).

Returns the candidate's slate metadata plus:
  * `latest_run`: per-dimension scores from the most recent run that contains
    this candidate (None if no run ever did).
  * `history`: last N runs' per-tier aggregate scores (newest first; only the
    runs that contain this candidate appear).
  * `rubric`: the live rubric's per-tier dimension list (active + draft),
    inlined so the CandidateDetail UI can render weight × score breakdowns
    in one round-trip. Per the MLI-267 architectural-input from MLI-274;
    `rubric.version` is also the source the Slice 4 Editor will use as its
    `expected_version` for the rubric write endpoint (MLI-273).

Lookup is by `binding.deployment` rather than the slate `id` — that matches
the value the scoreboard endpoint surfaces and the URL form the UI uses to
link from a scoreboard row to its detail page.

Convention notes:
  * 200 with `latest_run: null, history: []` when the candidate exists in the
    slate but has no scoring data — exemplified by `phi-4-mini-instruct`,
    which the dev seeder skips by default (MLI-183). The candidate's detail
    page must still load.
  * 404 distinguishes "unknown product" from "unknown candidate".
  * Repository and candidate-loader providers are reused from
    `scoreboard.py` — single source of truth for env-var resolution.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
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
from mmfp.models.matrix_run import MatrixRun
from mmfp.models.rubric import Direction, DimensionStatus, Method, Rubric
from mmfp.persistence import MatrixRunRepository
from mmfp.products.loader import load_rubric

router = APIRouter(tags=["candidate-detail"])

_DEFAULT_RUNS = 10
_MAX_RUNS = 100


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class CandidateTierResult(BaseModel):
    """Per-tier aggregate + per-dimension scores from a single run."""

    tier_id: TierId
    weighted_score: Decimal
    per_dimension: dict[str, Decimal]


class CandidateLatestRun(BaseModel):
    run_id: str
    rubric_version: str
    started_at: UTCDatetime
    completed_at: UTCDatetime | None
    per_tier: list[CandidateTierResult]


class CandidateHistoryEntry(BaseModel):
    """One entry per run in which the candidate appears. Aggregate per tier."""

    run_id: str
    started_at: UTCDatetime
    completed_at: UTCDatetime | None
    per_tier_scores: dict[TierId, Decimal]


class RubricDimensionView(BaseModel):
    """The slice of `Dimension` the candidate-detail UI renders.

    Deliberately narrower than `mmfp.models.rubric.Dimension`: the full model
    carries `evaluator` and `evaluator_config` for the engine, which are not
    surface for the modal. Trimming the payload at the boundary keeps the
    rubric block small and makes it obvious which fields the UI depends on.
    """

    id: str
    name: str
    description: str
    weight: Decimal
    status: DimensionStatus
    method: Method
    direction: Direction


class RubricTierView(BaseModel):
    tier_id: TierId
    name: str
    dimensions: list[RubricDimensionView]


class RubricView(BaseModel):
    """The rubric as the candidate-detail UI consumes it.

    `version` is the same field the Slice 4 Editor will pass back as
    `expected_version` to the rubric write endpoint (MLI-273); inlining it
    here means the Editor doesn't need a second fetch to seed its handshake.
    """

    version: str
    tiers: list[RubricTierView]


class CandidateDetailResponse(BaseModel):
    product: str
    candidate_id: str
    display_name: str
    family: CandidateFamily
    deployment: str
    status: CandidateStatus
    tiers: list[TierId]
    latest_run: CandidateLatestRun | None
    history: list[CandidateHistoryEntry]
    rubric: RubricView


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def get_rubric_loader() -> Callable[[str], Rubric]:
    """Provide a callable that loads a product's rubric.

    Same `MMFP_PRODUCTS_DIR` convention as the candidate-slate loader in
    `scoreboard.py` and the write endpoint in `rubric_write.py` — single
    source of truth for env-var resolution. `FileNotFoundError` from the
    loader signals an unknown product (mapped to 404 by the route).
    """
    products_dir = Path(os.environ.get("MMFP_PRODUCTS_DIR", "products"))

    def _load(product: str) -> Rubric:
        rubric_path = products_dir / product / "rubric.yaml"
        if not rubric_path.exists():
            raise FileNotFoundError(f"rubric.yaml not found at {rubric_path}")
        return load_rubric(rubric_path)

    return _load


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rubric_view(rubric: Rubric) -> RubricView:
    """Project the full `Rubric` model into the trimmed UI-facing view.

    Preserves the rubric's declaration order so the modal renders dimensions
    in the same order the steward sees them in the YAML (active and draft
    interleaved). The component is responsible for visually grouping or
    de-emphasising drafts.
    """
    return RubricView(
        version=rubric.version,
        tiers=[
            RubricTierView(
                tier_id=t.id,
                name=t.name,
                dimensions=[
                    RubricDimensionView(
                        id=d.id,
                        name=d.name,
                        description=d.description,
                        weight=d.weight,
                        status=d.status,
                        method=d.method,
                        direction=d.direction,
                    )
                    for d in t.dimensions
                ],
            )
            for t in rubric.tiers
        ],
    )


def _candidate_tier_results(
    run: MatrixRun, candidate_id: str, tiers: list[TierId]
) -> list[CandidateTierResult]:
    """Project a run's results into per-tier results for one candidate.

    Only emits tiers where the candidate has at least one scored row.
    """
    out: list[CandidateTierResult] = []
    for tier_id in tiers:
        for card in run.scores_for_tier(tier_id):
            if card.candidate_id == candidate_id:
                out.append(
                    CandidateTierResult(
                        tier_id=tier_id,
                        weighted_score=card.weighted_score,
                        per_dimension=card.per_dimension,
                    )
                )
                break
    return out


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.get(
    "/api/products/{product}/candidates/{deployment_name}",
    response_model=CandidateDetailResponse,
    summary="Per-candidate detail: latest dimensions and run history",
)
def get_candidate_detail(
    product: str,
    deployment_name: str,
    repo: Annotated[MatrixRunRepository, Depends(get_repository)],
    candidate_loader: Annotated[
        Callable[[str], list[Candidate]], Depends(get_candidate_loader)
    ],
    rubric_loader: Annotated[Callable[[str], Rubric], Depends(get_rubric_loader)],
    runs: Annotated[
        int,
        Query(
            ge=1,
            le=_MAX_RUNS,
            description="Number of most recent runs to scan for history (newest first)",
        ),
    ] = _DEFAULT_RUNS,
) -> CandidateDetailResponse:
    """Return per-dimension + history detail for one candidate.

    404 if the product slate is unknown, or the deployment name doesn't
    match any binding in the slate. 200 with empty `latest_run` / `history`
    if the candidate exists but has no scoring data in the last `runs`.
    """
    try:
        candidates = candidate_loader(product)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Unknown product '{product}'")

    # Rubric.load is the same path the rubric-write endpoint validates against,
    # so the version returned here is the version a Slice 4 Editor would have
    # to send as `expected_version`.
    try:
        rubric = rubric_loader(product)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Unknown product '{product}'")

    # Slate-lookup by binding.deployment (case-sensitive — provider-side
    # deployment names are themselves case-sensitive in Azure Foundry URLs).
    candidate = next(
        (c for c in candidates if c.binding.deployment == deployment_name), None
    )
    if candidate is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown candidate '{deployment_name}' for product '{product}'",
        )

    matrix_runs = repo.list_for_product(product, limit=runs)

    # Walk newest-first; collect history entries for runs that contain the
    # candidate, and record the first such run as `latest_run`.
    latest_run: CandidateLatestRun | None = None
    history: list[CandidateHistoryEntry] = []
    for run in matrix_runs:
        tier_results = _candidate_tier_results(run, candidate.id, candidate.tiers)
        if not tier_results:
            continue
        history.append(
            CandidateHistoryEntry(
                run_id=run.id,
                started_at=run.started_at,
                completed_at=run.completed_at,
                per_tier_scores={t.tier_id: t.weighted_score for t in tier_results},
            )
        )
        if latest_run is None:
            latest_run = CandidateLatestRun(
                run_id=run.id,
                rubric_version=run.rubric_version,
                started_at=run.started_at,
                completed_at=run.completed_at,
                per_tier=tier_results,
            )

    return CandidateDetailResponse(
        product=product,
        candidate_id=candidate.id,
        display_name=candidate.display_name,
        family=candidate.family,
        deployment=candidate.binding.deployment,
        status=candidate.status,
        tiers=candidate.tiers,
        latest_run=latest_run,
        history=history,
        rubric=_rubric_view(rubric),
    )
