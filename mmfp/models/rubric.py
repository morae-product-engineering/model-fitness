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
from typing import Annotated, Literal

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


class Dimension(BaseModel):
    """One scorable dimension within a tier."""

    model_config = MMFP_MODEL_CONFIG

    id: str = Field(min_length=1, description="Stable identifier, e.g. 'classification_accuracy'")
    name: str = Field(min_length=1, description="Human-readable label")
    description: str = Field(min_length=1, description="What this dimension measures")
    weight: Weight = Field(description="Percentage weight within its tier; tier weights sum to 100")
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
            "must match a key in the EvaluatorPlugin registry."
        ),
    )


class Tier(BaseModel):
    """One tier in the rubric (Classification & Routing / Structured Generation / Synthesis)."""

    model_config = MMFP_MODEL_CONFIG

    id: Literal["tier_1", "tier_2", "tier_3"] = Field(
        description="Stable tier identifier — kept Literal to enforce the three-tier shape"
    )
    name: str = Field(min_length=1)
    intent: str = Field(min_length=1, description="One-line statement of evaluation intent")
    mode: EvaluationMode
    dimensions: list[Dimension] = Field(min_length=1)

    @model_validator(mode="after")
    def _dimensions_sum_to_100(self) -> "Tier":
        total = sum((d.weight for d in self.dimensions), start=Decimal("0"))
        if abs(total - Decimal("100")) > _WEIGHT_SUM_TOLERANCE:
            raise ValueError(
                f"tier '{self.id}' dimension weights must sum to 100, got {total}"
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
