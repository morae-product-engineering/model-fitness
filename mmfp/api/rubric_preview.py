"""Rubric preview-impact endpoint — POST /api/products/{product}/rubric/preview-impact (MLI-193).

Read-only: accepts a candidate rubric, re-scores the product's latest MatrixRun
under both the current (live, on-disk) rubric and the posted candidate rubric,
and returns the per-tier ranking change. Nothing is persisted.

This endpoint is the consumer of `mmfp.engine.scoring.ScoringEngine`, which was
introduced in MLI-192 precisely to make this preview cheap: historical
normalised scores are re-weighted without re-invoking any model.

Convention notes:

  * **Empty state (200, `has_run=False`)** — returned when the product's rubric
    exists (known product) but no MatrixRun has been stored yet. The tiers list
    is empty and both version fields are populated. This mirrors the empty-state
    convention used elsewhere in the API (candidate-detail, scoreboard) rather
    than 404-ing on a legitimate but unrun product.

  * **Coverage flag** — `coverage_complete=False` on a candidate delta means
    that under at least one of the two rubrics the run did not measure every
    active dimension in the tier for that candidate. Re-scored deltas are valid
    in this case but the client should surface a warning: the score gap may be
    partly explained by missing coverage rather than purely by weight changes.

  * **Normalisation staleness** — ScoringEngine re-applies *weights*, not
    normalisation. If the candidate rubric changes a dimension's `direction` or
    `evaluator_config` (which governs the normalisation bounds), the per-run
    normalised values for that dimension are stale relative to the new rubric
    intent. The `normalization_stale_dimensions` list on each tier names those
    dimension ids so the client can caveat the delta. See MLI-192 decisions-
    to-flag for the full discussion of this boundary.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError

from mmfp.api.scoreboard import get_repository
from mmfp.engine.scoring import ScoringEngine
from mmfp.models.candidate import TierId
from mmfp.models.matrix_run import MatrixRun, Scorecard
from mmfp.models.rubric import Rubric
from mmfp.persistence import MatrixRunRepository
from mmfp.products.loader import load_rubric

logger = logging.getLogger(__name__)

router = APIRouter(tags=["rubric"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class PreviewImpactRequest(BaseModel):
    rubric: dict[str, Any] = Field(
        description="The full candidate rubric dict, in the YAML/JSON shape `Rubric` expects"
    )


class PreviewCandidateDelta(BaseModel):
    """Per-candidate score and rank delta between the current rubric and the candidate rubric."""

    candidate: str
    score_before: Decimal
    score_after: Decimal
    rank_before: int  # 1-based rank within the tier under the current rubric
    rank_after: int  # 1-based rank within the tier under the candidate rubric
    coverage_complete: bool  # True iff before AND after cards fully cover the tier's active dims


class PreviewTier(BaseModel):
    tier_id: TierId
    candidates: list[PreviewCandidateDelta]  # ordered by rank_after ascending
    normalization_stale_dimensions: list[str]
    """Active dim ids whose direction or evaluator_config (bounds) changed vs the current rubric.

    Re-scored deltas for these dims are computed on stale normalised values and
    are potentially misleading. Newly-added dimensions are not listed here — their
    coverage impact already appears via `coverage_complete` on the deltas.
    See MLI-192 for the normalisation-staleness boundary.
    """


class PreviewImpactResponse(BaseModel):
    product: str
    run_id: str | None  # None in the no-run empty state
    current_version: str
    candidate_version: str
    has_run: bool  # False → empty state, tiers == []
    tiers: list[PreviewTier]


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def get_current_rubric_loader() -> Callable[[str], Rubric]:
    """Provide a callable that loads a product's current (live, on-disk) rubric.

    Same `MMFP_PRODUCTS_DIR` convention as the rubric loader in
    `candidate_detail.py` and the write endpoint in `rubric_write.py` — single
    source of truth for env-var resolution. `FileNotFoundError` from the loader
    signals an unknown product (mapped to 404 by the route).

    Defined here rather than imported from `candidate_detail` so the two
    endpoints remain independently overridable in tests — the same pattern
    `trends.py` uses when it reuses scoreboard's providers while
    `candidate_detail` defines its own rubric loader.
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


def _cards_by_tier(cards: list[Scorecard]) -> dict[str, list[Scorecard]]:
    """Group a flat card list by tier_id, preserving the engine's within-tier order."""
    grouped: dict[str, list[Scorecard]] = {}
    for card in cards:
        grouped.setdefault(card.tier_id, []).append(card)
    return grouped


def _stale_dims(current_tier_dims: dict[str, Any], candidate_tier_active: list[Any]) -> list[str]:
    """Return ids of dims that exist in both tiers but changed direction or evaluator_config.

    A dim that is newly added by the candidate rubric is not listed — its
    impact is already captured by `coverage_complete` on the deltas.
    """
    stale: list[str] = []
    for dim in candidate_tier_active:
        current = current_tier_dims.get(dim.id)
        if current is None:
            # New dim — coverage concern, not a normalisation-staleness concern.
            continue
        if current.direction != dim.direction or current.evaluator_config != dim.evaluator_config:
            stale.append(dim.id)
    return stale


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post(
    "/api/products/{product}/rubric/preview-impact",
    response_model=PreviewImpactResponse,
    summary="Preview ranking impact of a candidate rubric change",
)
def post_rubric_preview_impact(
    product: str,
    payload: PreviewImpactRequest,
    repo: Annotated[MatrixRunRepository, Depends(get_repository)],
    rubric_loader: Annotated[Callable[[str], Rubric], Depends(get_current_rubric_loader)],
) -> PreviewImpactResponse:
    """Return per-tier ranking deltas for a candidate rubric against the latest run.

    Re-scores the product's latest MatrixRun under both the current (live) rubric
    and the posted candidate rubric using `ScoringEngine` (MLI-192), which
    re-applies weights to already-normalised scores — no model invocation occurs.

    Error states:
      * 404 — product's rubric.yaml doesn't exist (unknown product).
      * 422 — candidate rubric fails `Rubric.model_validate` (schema error) or
        `ScoringEngine` raises `ValueError` (schema_version mismatch).
      * 200 with `has_run=False` — product is known but has no run yet. The
        tiers list is empty; both versions are populated from the loaded rubrics.
    """
    # --- 1. Load current rubric (product-existence check is free) ---
    try:
        current_rubric = rubric_loader(product)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Unknown product '{product}'")

    # --- 2. Validate the posted candidate rubric ---
    try:
        candidate_rubric = Rubric.model_validate(payload.rubric)
    except ValidationError as exc:
        # Mirror the EXACT call from rubric_write.py (lines ~247-249) so the
        # UI has one error shape to render — FastAPI's `{"detail": [...]}`.
        raise HTTPException(
            status_code=422,
            detail=exc.errors(include_url=False, include_context=False, include_input=False),
        ) from exc

    # --- 3. Fetch the latest run; return empty state if none ---
    runs = repo.list_for_product(product, limit=1)
    if not runs:
        return PreviewImpactResponse(
            product=product,
            run_id=None,
            current_version=current_rubric.version,
            candidate_version=candidate_rubric.version,
            has_run=False,
            tiers=[],
        )

    run: MatrixRun = runs[0]

    # --- 4. Re-score under both rubrics ---
    try:
        before_cards = ScoringEngine().score(run, current_rubric)
        after_cards = ScoringEngine().score(run, candidate_rubric)
    except ValueError as exc:
        # ScoringEngine raises ValueError on schema_version mismatch — a
        # client-side rubric problem, not a server fault (MLI-192).
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # --- 5. Build per-tier deltas ---
    before_by_tier = _cards_by_tier(before_cards)
    after_by_tier = _cards_by_tier(after_cards)

    # Build a lookup map from current rubric tier id → its active dims, for
    # normalisation-staleness comparison.
    current_tier_active_by_id: dict[str, dict[str, Any]] = {
        t.id: {d.id: d for d in t.active_dimensions()} for t in current_rubric.tiers
    }

    tiers: list[PreviewTier] = []
    for cand_tier in candidate_rubric.tiers:
        tier_id: str = cand_tier.id

        current_before = before_by_tier.get(tier_id, [])
        current_after = after_by_tier.get(tier_id, [])

        if not current_before and not current_after:
            # Tier present in candidate rubric but absent from current rubric AND
            # has no run data — skip; nothing to show.
            continue

        if tier_id not in current_tier_active_by_id:
            # Tier is new in the candidate rubric (absent from the current rubric).
            # Log a warning; the re-scored cards are still valid but there's no
            # "before" reference to compare against for normalisation staleness.
            logger.warning(
                "rubric_preview.tier_absent_from_current_rubric",
                extra={"product": product, "tier_id": tier_id},
            )

        # Map candidate_id → (rank_before, score_before, has_complete_coverage_before)
        # from the before cards (engine order = rank order, 1-based).
        before_map: dict[str, tuple[int, Decimal, bool]] = {
            card.candidate_id: (rank, card.weighted_score, card.has_complete_coverage)
            for rank, card in enumerate(current_before, start=1)
        }

        deltas: list[PreviewCandidateDelta] = []
        for rank_after, after_card in enumerate(current_after, start=1):
            cid = after_card.candidate_id
            if cid in before_map:
                rank_before, score_before, cov_before = before_map[cid]
            else:
                # Candidate appears in after but not in before — score of 0, last rank.
                rank_before = len(current_before) + 1
                score_before = Decimal("0")
                cov_before = False

            deltas.append(
                PreviewCandidateDelta(
                    candidate=cid,
                    score_before=score_before,
                    score_after=after_card.weighted_score,
                    rank_before=rank_before,
                    rank_after=rank_after,
                    # Coverage is complete only when BOTH scorings fully covered this tier.
                    coverage_complete=cov_before and after_card.has_complete_coverage,
                )
            )

        # Normalisation-staleness: dims that exist in both rubrics but changed
        # direction or evaluator_config. New dims are not listed (coverage concern).
        current_dims_for_tier = current_tier_active_by_id.get(tier_id, {})
        stale = _stale_dims(current_dims_for_tier, cand_tier.active_dimensions())

        tiers.append(
            PreviewTier(
                tier_id=tier_id,
                candidates=deltas,
                normalization_stale_dimensions=stale,
            )
        )

    return PreviewImpactResponse(
        product=product,
        run_id=run.id,
        current_version=current_rubric.version,
        candidate_version=candidate_rubric.version,
        has_run=True,
        tiers=tiers,
    )
