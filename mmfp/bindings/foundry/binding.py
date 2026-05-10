"""AzureFoundryBinding — Azure AI Foundry / Azure OpenAI deployments.

Calls
`{endpoint}/openai/deployments/{name}/chat/completions?api-version={ver}`
with an `api-key` header. Endpoint and api_version come from the
Candidate's binding fields; the API key is resolved from the
`FOUNDRY_ACCOUNT_KEY` env var (mapped from Key Vault secret
`foundry-account-key` in production via Container App env-var injection
— never embedded in code or fixtures).

Reasoning content: when present, Foundry returns
`choices[0].message.reasoning_content` alongside `choices[0].message.content`.
This binding captures both verbatim; the evaluator decides which to score
(MLI-170, MLI-165 §2).

Out of scope for v1 (per MLI-171 brief):
  - Streaming — batch matrix runs only.
  - Retry/backoff — added when the matrix engine (MLI-172) surfaces the
    actual failure shape.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

from mmfp.bindings._registry import register
from mmfp.models.binding_response import BindingResponse, TokenUsage
from mmfp.models.candidate import Candidate
from mmfp.plugins.binding import BindingPlugin

API_KEY_ENV = "FOUNDRY_ACCOUNT_KEY"
DEFAULT_TIMEOUT_S = 60.0


@register
class AzureFoundryBinding(BindingPlugin):
    """Single-route binding for all Azure AI Foundry deployments."""

    name = "azure_foundry"

    def __init__(self, *, client: httpx.Client | None = None) -> None:
        # Optional client injection is the test seam; production code
        # calls `AzureFoundryBinding()` and the binding owns its httpx
        # client (closed via `close()`).
        self._client = client or httpx.Client(timeout=DEFAULT_TIMEOUT_S)
        self._owns_client = client is None

    def invoke(
        self,
        candidate: Candidate,
        prompt: str,
        max_tokens: int,
    ) -> BindingResponse:
        api_key = os.environ.get(API_KEY_ENV)
        if not api_key:
            raise RuntimeError(
                f"Missing {API_KEY_ENV} in environment; bindings cannot "
                f"run without the Foundry API key. In production this is "
                f"wired from Key Vault secret 'foundry-account-key' via "
                f"the Container App env-var mapping."
            )

        url = self._build_url(candidate)
        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }
        headers = {
            "api-key": api_key,
            "content-type": "application/json",
        }

        start = time.perf_counter()
        response = self._client.post(url, json=payload, headers=headers)
        latency_ms = int((time.perf_counter() - start) * 1000)
        response.raise_for_status()
        data: dict[str, Any] = response.json()

        choice = data["choices"][0]
        message = choice["message"]
        usage = data["usage"]

        return BindingResponse(
            # Provider sometimes returns null content (reasoning models
            # whose budget was exhausted on the trace). Normalise to ""
            # so downstream evaluators don't have to special-case None.
            content=message.get("content") or "",
            reasoning_content=message.get("reasoning_content"),
            usage=TokenUsage(
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
                total_tokens=usage.get(
                    "total_tokens",
                    usage["prompt_tokens"] + usage["completion_tokens"],
                ),
            ),
            latency_ms=latency_ms,
            model_deployment=candidate.binding.deployment,
            finish_reason=choice.get("finish_reason"),
        )

    def close(self) -> None:
        """Close the owned httpx client. No-op if a client was injected."""
        if self._owns_client:
            self._client.close()

    def _build_url(self, candidate: Candidate) -> str:
        # Trailing slash on the endpoint would otherwise produce '//openai'.
        endpoint = str(candidate.binding.endpoint).rstrip("/")
        return (
            f"{endpoint}/openai/deployments/{candidate.binding.deployment}"
            f"/chat/completions?api-version={candidate.binding.api_version}"
        )
