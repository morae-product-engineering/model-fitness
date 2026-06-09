"""Unit tests for LangSmithSampler (MFP-94).

All tests mock HTTP via httpx.MockTransport — no LangSmith credentials
required, no network access. Fixture payload loaded from
tests/fixtures/langsmith_seed.json so the seed and the tests share a
single source of truth for the expected run shape.

Deterministic: fixed datetime bounds, no wall-clock, no RNG.
NOT marked slice_acceptance: these gate MFP-94, not the Slice 7 slice itself.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from mmfp.sensors.langsmith_sampler import (
    LANGSMITH_API_KEY_ENV,
    LANGSMITH_ENDPOINT_ENV,
    LangSmithSampler,
)

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "langsmith_seed.json"
_FAKE_KEY = "sk-fake-test-key-xxx"
_PROJECT = "mmfp-drift-seed"
_CANDIDATE = "kimi-k2-6"
_TIER = "tier_1"
_START = datetime(2026, 6, 1, tzinfo=timezone.utc)
_END = datetime(2026, 6, 9, tzinfo=timezone.utc)


def _seed_runs() -> list[dict]:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


def _make_sampler(handler, *, api_key: str = _FAKE_KEY) -> LangSmithSampler:
    transport = httpx.MockTransport(handler)
    return LangSmithSampler(
        project_name=_PROJECT,
        api_key=api_key,
        client=httpx.Client(transport=transport),
    )


# ---------------------------------------------------------------------------
# Core behaviour
# ---------------------------------------------------------------------------


def test_returns_normalised_samples_from_seeded_source():
    """The seeded fixture yields normalised LiveSample dicts for the target candidate/tier."""
    seed = _seed_runs()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=seed)

    sampler = _make_sampler(handler)
    samples = sampler.fetch(_CANDIDATE, _TIER, start_time=_START, end_time=_END)

    # The fixture has 5 runs for kimi-k2-6/tier_1 and 2 for other combos.
    assert len(samples) == 5
    for s in samples:
        assert s["candidate_id"] == _CANDIDATE
        assert s["tier_id"] == _TIER
        assert isinstance(s["normalized_score"], Decimal)
        assert Decimal("0") <= s["normalized_score"] <= Decimal("100")
        assert s["dimension_id"] != ""
        assert s["run_id"] != ""


def test_empty_window_returns_empty_list_without_error():
    """An empty API response yields [] — no exception raised."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    sampler = _make_sampler(handler)
    result = sampler.fetch(_CANDIDATE, _TIER, start_time=_START, end_time=_END)

    assert result == []


def test_filters_out_other_candidates():
    """Runs for a different candidate are excluded from the returned sample."""
    seed = _seed_runs()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=seed)

    sampler = _make_sampler(handler)
    samples = sampler.fetch("gpt-4o", _TIER)

    assert len(samples) == 1
    assert all(s["candidate_id"] == "gpt-4o" for s in samples)


def test_filters_out_other_tiers():
    """Runs for a different tier are excluded even when candidate_id matches."""
    seed = _seed_runs()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=seed)

    sampler = _make_sampler(handler)
    samples = sampler.fetch(_CANDIDATE, "tier_2")

    assert len(samples) == 1
    assert all(s["tier_id"] == "tier_2" for s in samples)


def test_normalised_scores_match_fixture_values():
    """Each returned score matches the raw float in the fixture, coerced to Decimal."""
    seed = _seed_runs()
    target_runs = [
        r for r in seed
        if (r.get("extra") or {}).get("metadata", {}).get("candidate_id") == _CANDIDATE
        and (r.get("extra") or {}).get("metadata", {}).get("tier_id") == _TIER
    ]
    expected_scores = {
        r["id"]: Decimal(str(r["outputs"]["normalized_score"])) for r in target_runs
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=seed)

    sampler = _make_sampler(handler)
    samples = sampler.fetch(_CANDIDATE, _TIER)

    returned = {s["run_id"]: s["normalized_score"] for s in samples}
    assert returned == expected_scores


# ---------------------------------------------------------------------------
# API request shape
# ---------------------------------------------------------------------------


def test_sends_correct_api_key_header():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["key"] = request.headers.get("x-api-key")
        return httpx.Response(200, json=[])

    sampler = _make_sampler(handler, api_key=_FAKE_KEY)
    sampler.fetch(_CANDIDATE, _TIER)

    assert captured["key"] == _FAKE_KEY


def test_sends_session_and_limit_params():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=[])

    sampler = _make_sampler(handler)
    sampler.fetch(_CANDIDATE, _TIER, limit=10)

    assert captured["params"]["session"] == _PROJECT
    assert captured["params"]["limit"] == "10"


def test_sends_time_window_params_when_provided():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=[])

    sampler = _make_sampler(handler)
    sampler.fetch(_CANDIDATE, _TIER, start_time=_START, end_time=_END)

    assert "start_time" in captured["params"]
    assert "end_time" in captured["params"]


def test_omits_time_params_when_not_provided():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=[])

    sampler = _make_sampler(handler)
    sampler.fetch(_CANDIDATE, _TIER)

    assert "start_time" not in captured["params"]
    assert "end_time" not in captured["params"]


def test_hits_runs_endpoint_on_configured_endpoint():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)
    sampler = LangSmithSampler(
        project_name=_PROJECT,
        api_key=_FAKE_KEY,
        endpoint="https://custom.langchain.example.com",
        client=httpx.Client(transport=transport),
    )
    sampler.fetch(_CANDIDATE, _TIER)

    assert captured["url"].startswith("https://custom.langchain.example.com/api/v1/runs")


def test_endpoint_trailing_slash_is_stripped():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)
    sampler = LangSmithSampler(
        project_name=_PROJECT,
        api_key=_FAKE_KEY,
        endpoint="https://eu.api.smith.langchain.com/",
        client=httpx.Client(transport=transport),
    )
    sampler.fetch(_CANDIDATE, _TIER)

    assert "//api" not in captured["url"]


# ---------------------------------------------------------------------------
# Wraps-dict response format
# ---------------------------------------------------------------------------


def test_accepts_runs_wrapped_in_dict():
    """LangSmith may return {"runs": [...]} instead of a plain list."""
    seed = _seed_runs()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"runs": seed})

    sampler = _make_sampler(handler)
    samples = sampler.fetch(_CANDIDATE, _TIER)

    assert len(samples) == 5


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_missing_api_key_raises_runtime_error(monkeypatch):
    monkeypatch.delenv(LANGSMITH_API_KEY_ENV, raising=False)
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=[]))
    sampler = LangSmithSampler(
        project_name=_PROJECT,
        client=httpx.Client(transport=transport),
    )
    with pytest.raises(RuntimeError, match=LANGSMITH_API_KEY_ENV):
        sampler.fetch(_CANDIDATE, _TIER)


def test_api_key_from_env_when_not_passed_in_constructor(monkeypatch):
    monkeypatch.setenv(LANGSMITH_API_KEY_ENV, _FAKE_KEY)
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["key"] = request.headers.get("x-api-key")
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)
    sampler = LangSmithSampler(
        project_name=_PROJECT,
        client=httpx.Client(transport=transport),
    )
    sampler.fetch(_CANDIDATE, _TIER)

    assert captured["key"] == _FAKE_KEY


def test_endpoint_from_env_when_not_passed_in_constructor(monkeypatch):
    monkeypatch.setenv(LANGSMITH_ENDPOINT_ENV, "https://env-override.example.com")
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)
    sampler = LangSmithSampler(
        project_name=_PROJECT,
        api_key=_FAKE_KEY,
        client=httpx.Client(transport=transport),
    )
    sampler.fetch(_CANDIDATE, _TIER)

    assert captured["url"].startswith("https://env-override.example.com/api/v1/runs")


def test_non_2xx_raises_http_status_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "rate limited"})

    sampler = _make_sampler(handler)
    with pytest.raises(httpx.HTTPStatusError):
        sampler.fetch(_CANDIDATE, _TIER)


# ---------------------------------------------------------------------------
# Malformed-run tolerance
# ---------------------------------------------------------------------------


def test_run_without_normalized_score_is_skipped():
    """A run missing outputs.normalized_score is silently dropped."""
    runs = [
        {
            "id": "bad-run",
            "outputs": {},
            "extra": {"metadata": {"candidate_id": _CANDIDATE, "tier_id": _TIER}},
        },
        {
            "id": "good-run",
            "outputs": {"normalized_score": 55.0},
            "extra": {"metadata": {"candidate_id": _CANDIDATE, "tier_id": _TIER,
                                   "dimension_id": "accuracy"}},
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=runs)

    sampler = _make_sampler(handler)
    result = sampler.fetch(_CANDIDATE, _TIER)

    assert len(result) == 1
    assert result[0]["run_id"] == "good-run"


def test_run_with_unparseable_score_is_skipped():
    """A run whose normalized_score cannot be coerced to Decimal is dropped."""
    runs = [
        {
            "id": "bad-score-run",
            "outputs": {"normalized_score": "not-a-number"},
            "extra": {"metadata": {"candidate_id": _CANDIDATE, "tier_id": _TIER}},
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=runs)

    sampler = _make_sampler(handler)
    result = sampler.fetch(_CANDIDATE, _TIER)

    assert result == []
