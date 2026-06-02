"""Scoring engine — re-scores an existing MatrixRun under a (newer) Rubric.

Distinct from the matrix engine (`mmfp.engine.matrix.MatrixEngine`), which
*produces* a run by invoking models. This engine never invokes a model: it
takes a run's already-normalised evaluator outputs and re-applies a rubric's
weights to them, so an old run can be re-scored under a newer rubric cheaply.
That is what underwrites the impact-preview hypothesis (MLI-193): a rubric edit
doesn't require re-running the matrix.

The per-tier weighting is delegated to `MatrixRun.scores_for_tier(tier_id, tier)`
— the same aggregation the scoreboard uses — so there is one weighting code
path, not two. This module only adds what re-scoring needs on top: provenance
(which rubric version, which run) and a coverage flag for the case the rubric
demands an active dimension the historical run never measured.

ASSUMES: normalisation (raw value -> `normalized_score` 0–100) is pinned at run
time using the dimension direction/bounds in force then. Re-scoring re-applies
*weights*, not normalisation; a newer rubric that changes a dimension's
direction or bounds is NOT re-normalised here (the raw values would have to be
re-interpreted). For the rubric edits this serves — weight changes and adding /
removing dimensions — that distinction does not bite. See the MLI-192 closing
comment for the decision trail.
"""

from __future__ import annotations

from mmfp.models.matrix_run import MatrixRun, Scorecard
from mmfp.models.rubric import Rubric


class ScoringEngine:
    """Re-scores a MatrixRun under a Rubric. Sync, pure, side-effect-free.

    Stateless — the class exists to name the P3 boundary the impact-preview API
    (MLI-193) consumes, mirroring `MatrixEngine`'s shape; it carries no ctor
    state.
    """

    def score(self, run: MatrixRun, rubric: Rubric) -> list[Scorecard]:
        """Re-score `run`'s raw outputs under `rubric`.

        Returns one `Scorecard` per (tier, candidate) that has results in the
        run, grouped by tier in rubric order and, within a tier, ranked by
        `weighted_score` descending (as `scores_for_tier` orders them). Each card
        is stamped with `rubric.version` and the source run id, and carries
        `has_complete_coverage=False` when the tier's active dimensions are not
        all present in the run.

        Idempotent: the same `(run, rubric)` always yields equal Scorecards.
        Pure: neither argument is mutated; no IO, no model invocation.
        """
        # Schema-version mismatch is refused, not migrated. Only "v1" exists
        # today (`mmfp.models._common.SCHEMA_VERSION`), so any mismatch is an
        # artefact from a schema this code predates — migrating blind would
        # fabricate semantics (P9). Whoever introduces v2 owns the migration,
        # with the actual diff in hand. See MLI-192 decisions-to-flag.
        if run.schema_version != rubric.schema_version:
            raise ValueError(
                f"cannot re-score: run schema_version={run.schema_version!r} "
                f"!= rubric schema_version={rubric.schema_version!r}; schema "
                "migration is out of scope (MLI-192)"
            )

        cards: list[Scorecard] = []
        for tier in rubric.tiers:
            active_ids = {d.id for d in tier.active_dimensions()}
            for card in run.scores_for_tier(tier.id, tier):
                # Coverage is knowable from the card alone: `per_dimension` holds
                # exactly the active dims that produced ≥1 result for this
                # candidate. A missing active dim was weighted as 0 by
                # scores_for_tier (depressing the score) — we only flag it here.
                complete = active_ids <= set(card.per_dimension)
                cards.append(
                    card.model_copy(
                        update={
                            "rubric_version": rubric.version,
                            "source_run_id": run.id,
                            "has_complete_coverage": complete,
                        }
                    )
                )
        return cards
