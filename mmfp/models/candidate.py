"""Candidate model — the model under evaluation, plus its provider binding.

`max_tokens` is per-candidate and required (no default). MLI-165 closing
comments captured why: reasoning models (Kimi-K2.6, future R1 / o-series /
reasoning-class candidates) consume completion-token budget on internal
reasoning before emitting visible content, and a slate-wide default truncates
visible output to nothing. Forcing the choice at candidate-definition time
keeps that footgun off the operator.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

from mmfp.models._common import MMFP_MODEL_CONFIG, SCHEMA_VERSION, SchemaVersion

TierId = Literal["tier_1", "tier_2", "tier_3"]


class CandidateFamily(str, Enum):
    """Distinguishes reasoning models (whose output carries `reasoning_content`
    alongside `content`) from chat models. Evaluators consult this to decide
    whether a response's reasoning trace is in scope. See MLI-165 §2.
    """

    CHAT = "chat"
    REASONING = "reasoning"


class CandidateStatus(str, Enum):
    """Portfolio state. Promotion to a primary/fallback requires a written
    rationale (recorded out-of-band on the matrix run audit log).
    """

    UNDER_EVALUATION = "under_evaluation"
    APPROVED_PRIMARY = "approved_primary"
    APPROVED_FALLBACK = "approved_fallback"
    REJECTED = "rejected"


class CandidateBinding(BaseModel):
    """How to call a candidate.

    MLI-166 confirmed all 10 dev-account deployments — OpenAI-family AND
    serverless — serve via a single Azure OpenAI route shape, so a single
    binding shape suffices for v1. The binding plugin reads these fields; the
    actual API key is resolved from Key Vault by `key_vault_secret_name`, never
    embedded here.
    """

    model_config = MMFP_MODEL_CONFIG

    provider: str = Field(
        min_length=1,
        description="Logical provider id, e.g. 'azure_foundry'",
    )
    endpoint: HttpUrl = Field(
        description="Inference endpoint, e.g. https://*.cognitiveservices.azure.com",
    )
    deployment: str = Field(
        min_length=1,
        description="Provider-side deployment name, e.g. 'Kimi-K2.6'",
    )
    api_version: str = Field(
        default="2024-12-01-preview",
        min_length=1,
        description="Azure OpenAI / Foundry API version pin",
    )
    auth_method: str = Field(
        default="api_key_header",
        min_length=1,
        description="How the binding plugin authenticates; 'api_key_header' is the v1 default",
    )
    key_vault_secret_name: str = Field(
        min_length=1,
        description="Key Vault secret name holding the API key — never the key itself",
    )


class Candidate(BaseModel):
    """A model candidate in the slate."""

    model_config = MMFP_MODEL_CONFIG

    schema_version: SchemaVersion = SCHEMA_VERSION
    id: str = Field(min_length=1, description="Stable identifier across runs, e.g. 'kimi-k2-6'")
    display_name: str = Field(min_length=1)
    family: CandidateFamily
    max_tokens: int = Field(
        gt=0,
        description=(
            "Required, no default. Reasoning-class candidates need budget headroom for the "
            "reasoning trace before visible content emits — see MLI-165 §1."
        ),
    )
    context_window: int = Field(
        gt=0,
        description=(
            "Total context window in tokens (prompt + completion). Required, no default — "
            "the `context_window_adequacy` evaluator consults this to decide whether a "
            "candidate's window fits the dimension's representative budget, and inferring "
            "it from the deployment name is fragile. Distinct from `max_tokens`, which is "
            "the per-call completion budget."
        ),
    )
    binding: CandidateBinding
    # Tier candidacy is recorded once, here. MLI-166's tagging is for
    # discoverability; tier-fit lives only in the candidate slate per
    # MLI-165's "single source of truth per item" rule.
    tiers: list[TierId] = Field(
        min_length=1,
        description="Tiers this candidate is being evaluated against",
    )
    status: CandidateStatus = CandidateStatus.UNDER_EVALUATION
    notes: str | None = Field(default=None)

    @model_validator(mode="after")
    def _unique_tiers(self) -> "Candidate":
        if len(set(self.tiers)) != len(self.tiers):
            raise ValueError(f"candidate '{self.id}' has duplicate tiers: {self.tiers}")
        return self
