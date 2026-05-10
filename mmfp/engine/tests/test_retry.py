"""Unit tests for the engine-level retry helper (mmfp.engine._retry)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from mmfp.engine._retry import invoke_with_retry
from mmfp.models.binding_response import BindingResponse, TokenUsage
from mmfp.models.candidate import Candidate, CandidateBinding, CandidateFamily
from mmfp.plugins.binding import BindingPlugin


def _candidate() -> Candidate:
    return Candidate(
        id="cand-test",
        display_name="test",
        family=CandidateFamily.CHAT,
        max_tokens=128,
        tiers=["tier_1"],
        binding=CandidateBinding(
            provider="azure_foundry",
            endpoint="https://example.com",
            deployment="dep-test",
            key_vault_secret_name="foundry-account-key",
        ),
    )


def _ok_response(deployment: str) -> BindingResponse:
    return BindingResponse(
        content="ok",
        usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        latency_ms=1,
        model_deployment=deployment,
        finish_reason="stop",
    )


class _ScriptedBinding(BindingPlugin):
    """Plays a fixed script of behaviours per invoke call."""

    name = "scripted"

    def __init__(self, script: list[Any]) -> None:
        self._script = list(script)
        self.calls = 0

    def invoke(self, candidate, prompt, max_tokens) -> BindingResponse:
        self.calls += 1
        item = self._script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def _http_status(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.com/x")
    response = httpx.Response(code, request=request)
    return httpx.HTTPStatusError(f"status {code}", request=request, response=response)


def test_retries_on_429_then_succeeds():
    sleeps: list[float] = []
    binding = _ScriptedBinding(
        [_http_status(429), _http_status(429), _ok_response("dep-test")]
    )

    response = invoke_with_retry(
        binding,
        _candidate(),
        "hello",
        128,
        max_attempts=3,
        base_delay_s=1.0,
        sleep=sleeps.append,
    )

    assert response.content == "ok"
    assert binding.calls == 3
    # Backoff between attempt 1→2 and 2→3, no sleep after the final success.
    assert sleeps == [1.0, 2.0]


def test_retries_on_5xx_then_succeeds():
    sleeps: list[float] = []
    binding = _ScriptedBinding(
        [_http_status(503), _ok_response("dep-test")]
    )

    invoke_with_retry(
        binding,
        _candidate(),
        "hello",
        128,
        max_attempts=3,
        sleep=sleeps.append,
    )
    assert binding.calls == 2
    assert sleeps == [1.0]


def test_persistent_5xx_raises_after_exhausting():
    sleeps: list[float] = []
    binding = _ScriptedBinding(
        [_http_status(503), _http_status(503), _http_status(503)]
    )

    with pytest.raises(httpx.HTTPStatusError):
        invoke_with_retry(
            binding,
            _candidate(),
            "hello",
            128,
            max_attempts=3,
            sleep=sleeps.append,
        )
    assert binding.calls == 3
    # Two backoffs between three attempts; no sleep after the final failure.
    assert sleeps == [1.0, 2.0]


def test_non_retriable_4xx_raises_immediately():
    sleeps: list[float] = []
    binding = _ScriptedBinding([_http_status(400)])

    with pytest.raises(httpx.HTTPStatusError):
        invoke_with_retry(
            binding,
            _candidate(),
            "hello",
            128,
            max_attempts=3,
            sleep=sleeps.append,
        )
    assert binding.calls == 1
    assert sleeps == []


def test_network_error_is_retried():
    sleeps: list[float] = []
    request = httpx.Request("POST", "https://example.com/x")
    binding = _ScriptedBinding(
        [
            httpx.ConnectError("dns fail", request=request),
            _ok_response("dep-test"),
        ]
    )

    invoke_with_retry(
        binding,
        _candidate(),
        "hello",
        128,
        max_attempts=2,
        sleep=sleeps.append,
    )
    assert binding.calls == 2
    assert sleeps == [1.0]
