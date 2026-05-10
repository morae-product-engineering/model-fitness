"""Unit tests for AzureFoundryBinding via httpx.MockTransport."""

from __future__ import annotations

import json

import httpx
import pytest

from mmfp.bindings.foundry.binding import API_KEY_ENV, AzureFoundryBinding
from mmfp.models.binding_response import BindingResponse
from mmfp.models.candidate import Candidate, CandidateBinding, CandidateFamily

FAKE_KEY = "sk-fake-test-key-xxx"
FAKE_ENDPOINT = "https://mmfp-dev-models-resource.cognitiveservices.azure.com"


@pytest.fixture(autouse=True)
def _set_api_key(monkeypatch):
    monkeypatch.setenv(API_KEY_ENV, FAKE_KEY)


def _candidate(
    deployment: str, family: CandidateFamily = CandidateFamily.CHAT
) -> Candidate:
    return Candidate(
        id=f"id-{deployment}",
        display_name=deployment,
        family=family,
        max_tokens=1024,
        binding=CandidateBinding(
            provider="azure_foundry",
            endpoint=FAKE_ENDPOINT,
            deployment=deployment,
            key_vault_secret_name="foundry-account-key",
        ),
    )


def _make_binding(handler) -> AzureFoundryBinding:
    transport = httpx.MockTransport(handler)
    return AzureFoundryBinding(client=httpx.Client(transport=transport))


def test_invokes_openai_family_deployment_and_captures_content():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "pong"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 7,
                    "completion_tokens": 1,
                    "total_tokens": 8,
                },
            },
        )

    binding = _make_binding(handler)
    response = binding.invoke(_candidate("gpt-4o"), "Reply with exactly: pong", 200)

    assert isinstance(response, BindingResponse)
    assert response.content == "pong"
    assert response.reasoning_content is None
    assert response.model_deployment == "gpt-4o"
    assert response.usage.prompt_tokens == 7
    assert response.usage.completion_tokens == 1
    assert response.usage.total_tokens == 8
    assert response.finish_reason == "stop"
    assert response.latency_ms >= 0

    assert captured["url"] == (
        f"{FAKE_ENDPOINT}/openai/deployments/gpt-4o/chat/completions"
        "?api-version=2024-12-01-preview"
    )
    assert captured["headers"]["api-key"] == FAKE_KEY
    assert captured["body"]["messages"] == [
        {"role": "user", "content": "Reply with exactly: pong"}
    ]
    assert captured["body"]["max_tokens"] == 200


def test_invokes_non_openai_family_deployment_with_same_route_shape():
    """MLI-166: all 10 deployments serve through the same Azure OpenAI route."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert "/openai/deployments/Phi-4/chat/completions" in str(request.url)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": "phi response"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 5,
                    "completion_tokens": 2,
                    "total_tokens": 7,
                },
            },
        )

    binding = _make_binding(handler)
    response = binding.invoke(_candidate("Phi-4"), "hello", 100)
    assert response.content == "phi response"
    assert response.model_deployment == "Phi-4"


def test_captures_reasoning_content_for_kimi_k2_6():
    """MLI-165 §2: reasoning models emit both content and reasoning_content."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "pong",
                            "reasoning_content": (
                                "The user asked me to reply with pong; "
                                "I will reply with pong."
                            ),
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 50,
                    "total_tokens": 60,
                },
            },
        )

    binding = _make_binding(handler)
    response = binding.invoke(
        _candidate("Kimi-K2.6", family=CandidateFamily.REASONING),
        "Reply with exactly: pong",
        500,
    )

    assert response.content == "pong"
    assert response.reasoning_content is not None
    assert "user asked" in response.reasoning_content
    assert response.reasoning_content != response.content


def test_empty_content_and_length_finish_when_reasoning_starves_budget():
    """MLI-165 §1: reasoning models can emit empty content if budget is tight."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "reasoning_content": "thinking...",
                        },
                        "finish_reason": "length",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 10,
                    "total_tokens": 20,
                },
            },
        )

    binding = _make_binding(handler)
    response = binding.invoke(
        _candidate("Kimi-K2.6", family=CandidateFamily.REASONING),
        "Reply with exactly: pong",
        10,
    )
    # Provider's null content normalised to "" so downstream evaluators
    # don't have to special-case None vs absent vs empty.
    assert response.content == ""
    assert response.reasoning_content == "thinking..."
    assert response.finish_reason == "length"


def test_missing_api_key_raises_runtime_error(monkeypatch):
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    binding = _make_binding(lambda request: httpx.Response(200, json={}))
    with pytest.raises(RuntimeError, match=API_KEY_ENV):
        binding.invoke(_candidate("gpt-4o"), "hello", 100)


def test_non_2xx_response_raises_http_status_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "rate limited"}})

    binding = _make_binding(handler)
    with pytest.raises(httpx.HTTPStatusError):
        binding.invoke(_candidate("gpt-4o"), "hello", 100)


def test_endpoint_with_trailing_slash_does_not_double_up():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "ok"}, "finish_reason": "stop"}
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            },
        )

    binding = _make_binding(handler)
    cand = _candidate("gpt-4o")
    cand = cand.model_copy(
        update={
            "binding": cand.binding.model_copy(
                update={"endpoint": f"{FAKE_ENDPOINT}/"}
            )
        }
    )
    binding.invoke(cand, "hello", 50)
    # No '//openai' segment after the host means trailing slash was stripped.
    assert "//openai" not in captured["url"]


def test_total_tokens_inferred_when_provider_omits():
    """Some serverless deployments omit total_tokens; we sum prompt+completion."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "ok"}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 11, "completion_tokens": 2},
            },
        )

    binding = _make_binding(handler)
    response = binding.invoke(_candidate("Mistral-large"), "hello", 50)
    assert response.usage.total_tokens == 13


def test_uses_candidate_api_version():
    """API version comes from candidate.binding.api_version, not a constant."""
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "ok"}, "finish_reason": "stop"}
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            },
        )

    binding = _make_binding(handler)
    cand = _candidate("gpt-4o")
    cand = cand.model_copy(
        update={
            "binding": cand.binding.model_copy(update={"api_version": "2025-03-01"})
        }
    )
    binding.invoke(cand, "hello", 50)
    assert "api-version=2025-03-01" in captured["url"]
