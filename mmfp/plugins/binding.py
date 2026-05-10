"""BindingPlugin — the contract every model-provider binding implements.

P3 plugin interface. The signature is the public boundary; modifications
need explicit human approval per CLAUDE.md.

Bindings invoke a candidate model and return its response in a normalised
shape. The matrix engine (MLI-172) iterates candidates, looks up the
binding by `candidate.binding.provider` via the registry in
`mmfp.bindings`, and calls `invoke`. The first concrete binding
(`AzureFoundryBinding`) covers all 10 dev-account deployments —
OpenAI-family AND serverless (Llama, Mistral, Phi, Kimi) — through a
single Azure OpenAI route shape (MLI-166).

Reasoning models emit both `content` and `reasoning_content`.
`BindingResponse` keeps them separate; evaluators declare which they score
via `EvaluatorPlugin.scores_field` (MLI-170, MLI-165 §2). The binding
captures both verbatim and does not filter.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from mmfp.models.binding_response import BindingResponse
from mmfp.models.candidate import Candidate


class BindingPlugin(ABC):
    """Abstract base class for all model-provider bindings."""

    name: ClassVar[str]
    """Registry key — concrete subclasses must override. Matched against
    `Candidate.binding.provider` at lookup time."""

    @abstractmethod
    def invoke(
        self,
        candidate: Candidate,
        prompt: str,
        max_tokens: int,
    ) -> BindingResponse:
        """Send a single user prompt to the candidate's deployment.

        candidate: which model to call. The binding reads
            `candidate.binding.deployment`, `candidate.binding.endpoint`,
            and `candidate.binding.api_version`. The API key itself is
            resolved from process environment (e.g. `FOUNDRY_ACCOUNT_KEY`
            for the Foundry binding) — never from the Candidate, never
            from a fixture.
        prompt: the user-message content. v1 batch matrix runs use a
            single user message; multi-turn / system-prompt support
            broadens the shape later (non-breakingly).
        max_tokens: per-call completion-token cap. Typically the engine
            passes `candidate.max_tokens` (MLI-165 §1: reasoning models
            need generous budget headroom) but may override per-call
            without mutating the candidate.

        Implementations are sync at this ABC layer — async lands when the
        matrix engine surfaces concurrency need (MLI-172). Retry/backoff
        is likewise out of scope here; the engine layer adds it once the
        real failure shapes are known.
        """
        ...
