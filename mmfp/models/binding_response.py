"""BindingResponse — the normalised return shape for every BindingPlugin.

Captured from one provider call: visible content, the reasoning trace (if
any), token usage, wall-clock latency, the deployment that served the
request, and the provider-reported finish reason. The matrix engine
(MLI-172) consumes this and produces a `MatrixRunResult`; BindingResponse
is a runtime contract, not a persisted artefact, so it does not carry
`schema_version` (cf. Candidate, MatrixRun).

Reasoning vs content: reasoning models (Kimi-K2.6 today; future R1 /
o-series) emit both `message.content` and `message.reasoning_content`. The
binding captures both verbatim; the evaluator declares which to score via
its `scores_field` ClassVar (MLI-170, MLI-165 §2). Non-reasoning models
leave `reasoning_content` as None.

Provider raw response: deliberately not carried. LangSmith captures the
full request/response trace at the network layer for observability;
BindingResponse stays a clean platform-internal contract free of provider
ephemera. Broaden non-breakingly later if a real need surfaces.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from mmfp.models._common import MMFP_MODEL_CONFIG


class TokenUsage(BaseModel):
    """Per-call token accounting reported by the provider."""

    model_config = MMFP_MODEL_CONFIG

    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class BindingResponse(BaseModel):
    """A normalised model response from one BindingPlugin.invoke() call."""

    model_config = MMFP_MODEL_CONFIG

    content: str = Field(
        description=(
            "Visible response (`message.content`). Empty string if the provider "
            "returned no visible output (e.g. a reasoning model whose entire "
            "budget was spent on the trace — see MLI-165 §1)."
        ),
    )
    reasoning_content: str | None = Field(
        default=None,
        description=(
            "Internal reasoning trace (`message.reasoning_content`). Set for "
            "reasoning-class models; None for chat-only models."
        ),
    )
    usage: TokenUsage
    latency_ms: int = Field(ge=0, description="Wall-clock invoke duration")
    model_deployment: str = Field(
        min_length=1,
        description=(
            "Deployment name the request was routed to; echoes "
            "candidate.binding.deployment for audit."
        ),
    )
    finish_reason: str | None = Field(
        default=None,
        description=(
            "Provider-reported finish reason ('stop', 'length', "
            "'content_filter', ...). 'length' on a reasoning model with empty "
            "content typically means the budget was exhausted on the trace."
        ),
    )
