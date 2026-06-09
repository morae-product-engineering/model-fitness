"""Rubric model — the versioned scoring framework.

Mirrors the structure described in the v0.1 rubric reference doc:
tiers → dimensions → weights, with gates as binary entry conditions and a
pinned LLM judge for inferential dimensions. Every persisted artefact records
`schema_version`; the rubric itself also carries an editable semver-style
`version` (`v0.1`, `v0.2`, …) used by `MatrixRun.rubric_version` so old runs
remain re-scoreable under new rubrics.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

from mmfp.models._common import MMFP_MODEL_CONFIG, SCHEMA_VERSION, SchemaVersion

# Tolerance for per-tier weight sums. Weights are declared as percentages and
# can come from YAML floats; insisting on exact 100.0 is hostile to authors.
_WEIGHT_SUM_TOLERANCE = Decimal("0.001")


class Method(str, Enum):
    """How a dimension is measured.

    Mirrors the "Method" column of each tier in the rubric reference doc.
    """

    DETERMINISTIC = "deterministic"
    METRIC = "metric"
    LLM_JUDGE = "llm_judge"
    COMPOSITE = "composite"
    QUALITATIVE = "qualitative"


class EvaluationMode(str, Enum):
    SINGLE_TURN = "single_turn"
    MULTI_TURN = "multi_turn"


class Direction(str, Enum):
    """Whether higher or lower raw values map to higher normalised scores.

    Latency and cost dimensions are lower-is-better; everything else defaults
    to higher-is-better.
    """

    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


# Type alias: weight is a percentage in [0, 100].
Weight = Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("100"))]


DimensionStatus = Literal["active", "draft"]


class Dimension(BaseModel):
    """One scorable dimension within a tier.

    `status` partitions a tier into the dimensions that contribute to scoring
    today (`active`) and those that are declared in the rubric YAML so the
    shape matches the v0.1 reference document but are not yet measured
    (`draft` — typically waiting on an evaluator family that ships in a
    later slice). Draft dimensions are excluded from the per-tier weight
    sum and from the matrix-engine's weighted aggregation; activation
    happens by flipping the field once the evaluator lands.
    """

    model_config = MMFP_MODEL_CONFIG

    id: str = Field(min_length=1, description="Stable identifier, e.g. 'classification_accuracy'")
    name: str = Field(min_length=1, description="Human-readable label")
    description: str = Field(min_length=1, description="What this dimension measures")
    weight: Weight = Field(
        description=(
            "Percentage weight within its tier. The active partition's weights "
            "sum to (0, 100]; draft dimensions must declare `weight: 0` (see "
            "Tier validator and the MLI-267 architectural-input from MLI-269)."
        )
    )
    status: DimensionStatus = Field(
        default="active",
        description=(
            "Whether this dimension contributes to scoring (`active`) or is "
            "declared-but-not-yet-measured (`draft`). Existing rubrics without "
            "this field load as fully active."
        ),
    )
    method: Method
    direction: Direction = Direction.HIGHER_IS_BETTER
    # The MLI-258 engine signature still takes `dimension_evaluators` as an
    # explicit Mapping[str, str] so `MatrixEngine.run()` doesn't change shape;
    # the loader derives that mapping from this field. Single source of truth
    # in the rubric YAML — see ADR-0001 §"Open question for MLI-173" /
    # MLI-173 closing comment.
    evaluator: str = Field(
        min_length=1,
        description=(
            "Registered evaluator name (e.g. 'exact_match', 'json_schema'); "
            "must match a key in the EvaluatorPlugin registry for active "
            "dimensions. Draft dimensions may name a not-yet-registered "
            "evaluator as documentary intent (the engine never dispatches "
            "to a draft dimension, so registry membership is enforced at "
            "load time only for the active partition)."
        ),
    )
    evaluator_config: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Free-form per-evaluator config (e.g. `reference_p95_ms` for "
            "`latency_p95`, `reference_usd` + `per_calls` for `cost_per_call`, "
            "`golden_db_path` for `query_correctness`, `required_tokens` for "
            "`context_window_adequacy`). The matrix engine merges this into "
            "`context['evaluator_config']` before dispatch; each evaluator "
            "validates its own shape. Per MLI-267 architectural-input from "
            "MLI-270 — keeps Dimension a stable boundary while letting new "
            "evaluator families add config keys without model churn."
        ),
    )


class Tier(BaseModel):
    """One tier in the rubric (Classification & Routing / Structured Generation / Synthesis).

    A tier's dimensions are partitioned by `Dimension.status` into the active
    set (contributes to scoring; weights sum to 100 within the active partition)
    and the draft set (declared so the rubric shape matches the v0.1 reference
    doc but not yet measured; weights must be 0). The matrix engine normalises
    its weighted aggregation against the active-weight total, so a tier with
    sparse active coverage still produces 0–100 scores.
    """

    model_config = MMFP_MODEL_CONFIG

    id: Literal["tier_1", "tier_2", "tier_3"] = Field(
        description="Stable tier identifier — kept Literal to enforce the three-tier shape"
    )
    name: str = Field(min_length=1)
    intent: str = Field(min_length=1, description="One-line statement of evaluation intent")
    mode: EvaluationMode
    dimensions: list[Dimension] = Field(min_length=1)

    def active_dimensions(self) -> list[Dimension]:
        """Dimensions that contribute to scoring (status='active'), preserving declaration order."""
        return [d for d in self.dimensions if d.status == "active"]

    def draft_dimensions(self) -> list[Dimension]:
        """Dimensions declared in the rubric but not yet measured (status='draft')."""
        return [d for d in self.dimensions if d.status == "draft"]

    @model_validator(mode="after")
    def _dimensions_partition_is_valid(self) -> "Tier":
        # Active partition weights must sum to (0, 100]. Strictly > 0 so a tier
        # with no active dimensions fails fast at load time rather than producing
        # a divide-by-zero in the engine. <= 100 mirrors the per-dimension cap
        # and the v0.1 reference's "weights are tier shares" intent.
        active = self.active_dimensions()
        active_total = sum((d.weight for d in active), start=Decimal("0"))
        if active_total <= Decimal("0"):
            raise ValueError(
                f"tier '{self.id}' has no active dimension weight (sum={active_total}); "
                "at least one dimension must have status='active' with weight > 0"
            )
        if active_total - Decimal("100") > _WEIGHT_SUM_TOLERANCE:
            raise ValueError(
                f"tier '{self.id}' active dimension weights must sum to <= 100, got {active_total}"
            )

        # Per MLI-267 architectural-input (MLI-269): draft dimensions are
        # documentary placeholders; their weight must be exactly 0 to avoid
        # the "this 25 doesn't count" footgun in the YAML. Stewards re-balance
        # weights at activation time anyway.
        nonzero_drafts = [d.id for d in self.draft_dimensions() if d.weight != Decimal("0")]
        if nonzero_drafts:
            raise ValueError(
                f"tier '{self.id}' draft dimensions must have weight=0, "
                f"got non-zero weights for: {nonzero_drafts}"
            )

        ids = [d.id for d in self.dimensions]
        if len(set(ids)) != len(ids):
            raise ValueError(f"tier '{self.id}' has duplicate dimension ids: {ids}")
        return self


class Gate(BaseModel):
    """A binary entry condition. Failing any applicable gate excludes a candidate."""

    model_config = MMFP_MODEL_CONFIG

    id: str = Field(min_length=1, description="e.g. 'gate.compliance.soc2'")
    description: str = Field(min_length=1)
    # Empty list means "applies to all tiers" — keeps the YAML terse for the
    # common case (most gates apply uniformly).
    applies_to_tiers: list[Literal["tier_1", "tier_2", "tier_3"]] = Field(default_factory=list)


class JudgeConfig(BaseModel):
    """Pinned LLM-judge config for inferential dimensions."""

    model_config = MMFP_MODEL_CONFIG

    model: str = Field(min_length=1, description="Judge model identifier, e.g. 'claude-sonnet-4-5'")
    provider: str = Field(min_length=1)
    version_pin: str = Field(min_length=1, description="Provider-side version, e.g. '2025-10-01'")
    temperature: Decimal = Field(default=Decimal("0.0"), ge=Decimal("0"), le=Decimal("2"))
    calibration_set: str = Field(
        min_length=1,
        description="Path to JSONL of human-curated examples used to verify the judge",
    )
    human_sample_rate: Decimal = Field(
        default=Decimal("0.10"),
        ge=Decimal("0"),
        le=Decimal("1"),
        description="Fraction of judge scores reviewed by a human curator",
    )
    drift_threshold: Decimal = Field(
        default=Decimal("0.85"),
        ge=Decimal("0"),
        le=Decimal("1"),
        description="Re-pin when calibration agreement drops below this value",
    )
    deployment: str | None = Field(
        default=None,
        description="Foundry deployment name for azure_foundry provider",
    )
    endpoint: str | None = Field(
        default=None,
        description="Foundry endpoint URL for azure_foundry provider",
    )


class PortfolioThresholds(BaseModel):
    """Score boundaries that govern candidate status. Versioned with the rubric."""

    model_config = MMFP_MODEL_CONFIG

    approved_primary_min: Decimal = Field(default=Decimal("75"), ge=Decimal("0"), le=Decimal("100"))
    approved_fallback_min: Decimal = Field(
        default=Decimal("70"), ge=Decimal("0"), le=Decimal("100")
    )
    rejected_max: Decimal = Field(default=Decimal("60"), ge=Decimal("0"), le=Decimal("100"))
    tiebreak_band: Decimal = Field(
        default=Decimal("3"),
        ge=Decimal("0"),
        description="Candidates within this many points of each other are tied",
    )

    @model_validator(mode="after")
    def _ordered(self) -> "PortfolioThresholds":
        if not (self.rejected_max <= self.approved_fallback_min <= self.approved_primary_min):
            raise ValueError(
                "thresholds must be ordered "
                "rejected_max ≤ approved_fallback_min ≤ approved_primary_min"
            )
        return self


class ObservabilityConfig(BaseModel):
    """Per-rubric observability bindings.

    LangSmith endpoint lives here, not in env-only config: the rubric YAML is
    authoritative for the *intent* (EU residency for Morae), and any deployment
    artefact that overrides it has to do so deliberately. See MLI-167.
    """

    model_config = MMFP_MODEL_CONFIG

    langsmith_endpoint: HttpUrl = Field(
        default=HttpUrl("https://eu.api.smith.langchain.com"),
        description="LangSmith API endpoint — EU instance for Morae data residency",
    )
    langsmith_project: str = Field(
        default="mmfp-dev",
        min_length=1,
        description="LangSmith project name; per-environment override expected",
    )


class Rubric(BaseModel):
    """The full rubric: tiers, gates, judge, thresholds, observability."""

    model_config = MMFP_MODEL_CONFIG

    schema_version: SchemaVersion = SCHEMA_VERSION
    version: str = Field(
        min_length=1,
        pattern=r"^v\d+\.\d+$",
        description="Editable rubric version, e.g. 'v0.1'",
    )
    tiers: list[Tier] = Field(min_length=1)
    gates: list[Gate] = Field(default_factory=list)
    judge: JudgeConfig
    thresholds: PortfolioThresholds = Field(default_factory=PortfolioThresholds)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)

    @model_validator(mode="after")
    def _unique_tier_ids(self) -> "Rubric":
        ids = [t.id for t in self.tiers]
        if len(set(ids)) != len(ids):
            raise ValueError(f"rubric has duplicate tier ids: {ids}")
        return self
