"""Matrix run model — the artefact a scoring run produces.

A `MatrixRun` is a flat list of `MatrixRunResult`s (one per candidate × example
× evaluator), tagged with the rubric version it was scored under. `Scorecard`
is the derived per-candidate-per-tier view used by the Scoreboard UI; it isn't
persisted, it's computed by `MatrixRun.scores_for_tier()`.

This module deliberately does not implement the engine. The engine
(`mmfp.engine.matrix.MatrixEngine`) is MLI-172. This module just defines the
shapes the engine produces.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from mmfp.models._common import (
    MMFP_MODEL_CONFIG,
    SCHEMA_VERSION,
    SchemaVersion,
    UTCDatetime,
)
from mmfp.models.candidate import CandidateStatus
from mmfp.models.rubric import Tier


class SourceField(str, Enum):
    """Which response field the evaluator scored.

    Reasoning models emit `message.content` (visible) and
    `message.reasoning_content` (internal trace). Tier 1 / Tier 2 evaluators
    must score `content` only — the trace is noise. Tier 3 may score either.
    See MLI-165 §2.
    """

    CONTENT = "content"
    REASONING_CONTENT = "reasoning_content"


class EvaluatorScore(BaseModel):
    """One evaluator's output for one (candidate, example, dimension)."""

    model_config = MMFP_MODEL_CONFIG

    dimension_id: str = Field(min_length=1)
    evaluator_id: str = Field(min_length=1, description="Plugin id producing this score")
    raw_value: Any = Field(
        description=(
            "Native evaluator output before normalisation — float for accuracy, "
            "ms for latency, USD for cost, judge score on declared scale."
        )
    )
    normalized_score: Decimal = Field(
        ge=Decimal("0"),
        le=Decimal("100"),
        description="0–100 normalised score; mapped from raw via dimension direction/bounds",
    )
    passed: bool | None = Field(
        default=None,
        description="For pass/fail dimensions; None for continuous-scored dimensions",
    )
    source_field: SourceField = SourceField.CONTENT
    latency_ms: int | None = Field(default=None, ge=0)
    cost_usd: Decimal | None = Field(default=None, ge=Decimal("0"))
    reason: str | None = Field(
        default=None,
        description=(
            "Short human-readable explanation of the score (e.g. 'exact match', "
            "'json missing key foo'). Distinct from `error`: `reason` describes "
            "a normal pass/fail outcome; `error` is set only when the evaluator "
            "itself failed to run."
        ),
    )
    error: str | None = Field(
        default=None,
        description="Set if evaluator failed; raw_value undefined",
    )


class MatrixRunResult(BaseModel):
    """One row in the run matrix: candidate × example × evaluator output."""

    model_config = MMFP_MODEL_CONFIG

    tier_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    example_id: str = Field(min_length=1)
    score: EvaluatorScore
    completion_tokens: int | None = Field(default=None, ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    finish_reason: str | None = Field(default=None)


class Scorecard(BaseModel):
    """Derived per-(tier, candidate) view aggregated from results.

    Built by `MatrixRun.scores_for_tier`; not persisted on its own.
    """

    model_config = MMFP_MODEL_CONFIG

    tier_id: str
    candidate_id: str
    weighted_score: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    per_dimension: dict[str, Decimal] = Field(
        default_factory=dict,
        description=(
            "dimension_id -> mean normalised score (0–100) across the examples "
            "scored for that dimension. The aggregate `weighted_score` is the "
            "rubric-weighted combination of these means, normalised by the "
            "active-weight total per tier when a Tier is provided to "
            "`scores_for_tier`."
        ),
    )
    status: CandidateStatus = CandidateStatus.UNDER_EVALUATION
    tied_with: list[str] = Field(default_factory=list)
    rubric_version: str | None = Field(
        default=None,
        description=(
            "Rubric.version this card was scored under. Set by "
            "`mmfp.engine.scoring.ScoringEngine` when re-scoring a run under a "
            "(possibly newer) rubric; None for cards built by `scores_for_tier`, "
            "which does not carry a rubric version (the Tier it takes has none)."
        ),
    )
    source_run_id: str | None = Field(
        default=None,
        description=(
            "Id of the MatrixRun whose raw outputs produced this card, when "
            "re-scored by ScoringEngine; None for cards built directly by "
            "`scores_for_tier`."
        ),
    )
    has_complete_coverage: bool = Field(
        default=True,
        description=(
            "False when the scoring rubric declares an active dimension the run "
            "never measured (a coverage gap). Such gaps lower `weighted_score` "
            "rather than raising — see ScoringEngine (MLI-192). Defaults True: "
            "`scores_for_tier` performs no coverage analysis."
        ),
    )


class MatrixRun(BaseModel):
    """A complete scoring run: results, rubric pin, timing.

    Scorecards are built lazily — the engine emits flat `results`, the UI / API
    asks for `scores_for_tier(tier_id)` when it needs the per-tier ranking.
    """

    model_config = MMFP_MODEL_CONFIG

    schema_version: SchemaVersion = SCHEMA_VERSION
    id: str = Field(min_length=1, description="Run identifier (UUID hex preferred)")
    rubric_version: str = Field(
        min_length=1,
        pattern=r"^v\d+\.\d+$",
        description="Rubric.version pinned at run start; older runs remain re-scoreable",
    )
    started_at: UTCDatetime
    completed_at: UTCDatetime | None = Field(default=None)
    results: list[MatrixRunResult] = Field(default_factory=list)

    @model_validator(mode="after")
    def _completed_after_start(self) -> "MatrixRun":
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("completed_at must be ≥ started_at")
        return self

    def scores_for_tier(
        self, tier_id: str, tier: Tier | None = None
    ) -> list[Scorecard]:
        """Aggregate results into per-candidate Scorecards for a tier.

        When `tier` is omitted, `weighted_score` is the unweighted mean of the
        per-dimension means — the rubric-agnostic view used by callers that
        don't have a `Rubric` in hand. When `tier` is provided, `weighted_score`
        is the rubric-weighted aggregate over the tier's **active** dimensions
        only, normalised by the active-weight total. This is the path the
        scoreboard and candidate-detail surfaces will adopt once they thread
        the loaded rubric through (later sub-tasks in MLI-267).

        Normalising by the active-weight total — rather than by 100 — means a
        tier whose draft partition still owns most of the weight (e.g. Tier 3
        with 20% active in v0.1) still produces 0–100 scores rather than
        artificially-compressed ones. See MLI-269 / MLI-267.

        Pure aggregation — no thresholding. The caller decides whether to
        attach a `status` based on thresholds and prior runs.
        """
        if tier is not None and tier.id != tier_id:
            raise ValueError(
                f"scores_for_tier: tier.id='{tier.id}' does not match tier_id='{tier_id}'"
            )

        per_candidate: dict[str, list[MatrixRunResult]] = defaultdict(list)
        for r in self.results:
            if r.tier_id == tier_id:
                per_candidate[r.candidate_id].append(r)

        cards: list[Scorecard] = []
        for candidate_id, rows in per_candidate.items():
            if not rows:
                continue
            by_dim: dict[str, list[Decimal]] = defaultdict(list)
            for r in rows:
                by_dim[r.score.dimension_id].append(r.score.normalized_score)
            per_dim_mean = {
                dim_id: sum(scores, Decimal("0")) / Decimal(len(scores))
                for dim_id, scores in by_dim.items()
            }

            if tier is not None:
                # Rubric-weighted path: sum_d (mean_d * weight_d) / active_total,
                # over active dimensions only. Active dims that produced no
                # results contribute 0 to the numerator but their weight still
                # counts in the denominator — coverage gaps lower the score
                # rather than silently inflating it.
                active = tier.active_dimensions()
                active_total = sum((d.weight for d in active), start=Decimal("0"))
                numerator = sum(
                    (per_dim_mean.get(d.id, Decimal("0")) * d.weight for d in active),
                    start=Decimal("0"),
                )
                weighted = numerator / active_total if active_total > 0 else Decimal("0")
            else:
                weighted = (
                    sum(per_dim_mean.values(), Decimal("0")) / Decimal(len(per_dim_mean))
                    if per_dim_mean
                    else Decimal("0")
                )
            cards.append(
                Scorecard(
                    tier_id=tier_id,
                    candidate_id=candidate_id,
                    weighted_score=weighted,
                    per_dimension=per_dim_mean,
                )
            )
        cards.sort(key=lambda c: c.weighted_score, reverse=True)
        return cards
