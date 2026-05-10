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
        description="dimension_id -> weighted contribution (0–100 * weight%)",
    )
    status: CandidateStatus = CandidateStatus.UNDER_EVALUATION
    tied_with: list[str] = Field(default_factory=list)


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

    def scores_for_tier(self, tier_id: str) -> list[Scorecard]:
        """Aggregate results into per-candidate Scorecards for a tier.

        Pure aggregation — no rubric reference, no thresholding. The caller
        (engine, UI route) decides whether to attach a `status` based on
        thresholds and prior runs.
        """
        per_candidate: dict[str, list[MatrixRunResult]] = defaultdict(list)
        for r in self.results:
            if r.tier_id == tier_id:
                per_candidate[r.candidate_id].append(r)

        cards: list[Scorecard] = []
        for candidate_id, rows in per_candidate.items():
            if not rows:
                continue
            # Mean normalised score per dimension; engine v1 collapses
            # multiple examples per dimension by mean. Per-dimension weighting
            # is the rubric's job — this view stays rubric-agnostic and just
            # surfaces the average normalised score per dimension. The
            # weighted score is the unweighted mean across dimensions; the
            # engine in MLI-172 will replace this with rubric-weighted maths.
            by_dim: dict[str, list[Decimal]] = defaultdict(list)
            for r in rows:
                by_dim[r.score.dimension_id].append(r.score.normalized_score)
            per_dim_mean = {
                dim_id: sum(scores, Decimal("0")) / Decimal(len(scores))
                for dim_id, scores in by_dim.items()
            }
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
