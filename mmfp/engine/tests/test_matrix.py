"""Unit + in-process integration tests for MatrixEngine.

Tests construct Rubric / Dataset / Candidate Pydantic objects in-memory;
they don't load YAML. The slice acceptance test
(`mmfp/tests/test_matrix_run.py`) is a separate file that stays
deliberately red until subtask 2.8 lands real fixtures.

Real evaluators are used (deterministic-trio is registered side-effect on
import of `mmfp.evaluators`); bindings are mocked because production
bindings hit Azure Foundry.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from mmfp.engine import MatrixEngine
from mmfp.models.binding_response import BindingResponse, TokenUsage
from mmfp.models.candidate import Candidate, CandidateBinding, CandidateFamily
from mmfp.models.dataset import Dataset, DatasetExample
from mmfp.models.matrix_run import MatrixRun, MatrixRunResult, SourceField
from mmfp.models.rubric import (
    Dimension,
    Direction,
    EvaluationMode,
    JudgeConfig,
    Method,
    Rubric,
    Tier,
)
from mmfp.plugins.binding import BindingPlugin
from mmfp.plugins.evaluator import EvaluatorPlugin
from mmfp.products.loader import load_candidates

REPO_ROOT = Path(__file__).resolve().parents[3]
MLI_CANDIDATES_YAML = REPO_ROOT / "products" / "mli" / "candidates.yaml"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _disable_langsmith(monkeypatch):
    """Ensure tests don't accidentally emit traces to a real LangSmith
    instance. The SDK no-ops without these vars; setting them explicitly
    keeps behaviour deterministic regardless of the developer's shell env.
    """
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)


def _judge() -> JudgeConfig:
    return JudgeConfig(
        model="claude-sonnet-4-5",
        provider="anthropic",
        version_pin="2025-10-01",
        calibration_set="tests/calibration/judge.jsonl",
    )


def _rubric_three_tiers() -> Rubric:
    """A minimal three-tier rubric (one dimension per tier)."""
    return Rubric(
        version="v0.1",
        tiers=[
            Tier(
                id="tier_1",
                name="Classification & Routing",
                intent="classify input",
                mode=EvaluationMode.SINGLE_TURN,
                dimensions=[
                    Dimension(
                        id="t1.classification_accuracy",
                        name="Classification Accuracy",
                        description="exact-match against label",
                        weight=Decimal("100"),
                        method=Method.DETERMINISTIC,
                        direction=Direction.HIGHER_IS_BETTER,
                        evaluator="exact_match",
                    )
                ],
            ),
            Tier(
                id="tier_2",
                name="Structured Generation",
                intent="emit valid JSON",
                mode=EvaluationMode.SINGLE_TURN,
                dimensions=[
                    Dimension(
                        id="t2.schema_validity",
                        name="Schema Validity",
                        description="json schema validation",
                        weight=Decimal("100"),
                        method=Method.DETERMINISTIC,
                        evaluator="json_schema",
                    )
                ],
            ),
            Tier(
                id="tier_3",
                name="Synthesis",
                intent="produce coherent answer",
                mode=EvaluationMode.SINGLE_TURN,
                dimensions=[
                    Dimension(
                        id="t3.contains_keyword",
                        name="Contains Keyword",
                        description="regex check",
                        weight=Decimal("100"),
                        method=Method.DETERMINISTIC,
                        evaluator="regex_match",
                    )
                ],
            ),
        ],
        judge=_judge(),
    )


def _datasets_three_tiers() -> list[Dataset]:
    return [
        Dataset(
            id="ds-tier1",
            name="tier_1 set",
            version="v0.1",
            tier_id="tier_1",
            examples=[
                DatasetExample(id="t1.e1", input="classify A", expected={"value": "A"}),
                DatasetExample(id="t1.e2", input="classify B", expected={"value": "B"}),
            ],
        ),
        Dataset(
            id="ds-tier2",
            name="tier_2 set",
            version="v0.1",
            tier_id="tier_2",
            examples=[
                DatasetExample(
                    id="t2.e1",
                    input="emit json",
                    expected={
                        "schema": {
                            "type": "object",
                            "required": ["ok"],
                            "properties": {"ok": {"type": "boolean"}},
                        }
                    },
                ),
            ],
        ),
        Dataset(
            id="ds-tier3",
            name="tier_3 set",
            version="v0.1",
            tier_id="tier_3",
            examples=[
                DatasetExample(
                    id="t3.e1",
                    input="answer question",
                    expected={"pattern": r"\bdogs?\b"},
                ),
            ],
        ),
    ]


def _candidate(
    id: str,
    deployment: str = "gpt-4o",
    family: CandidateFamily = CandidateFamily.CHAT,
    max_tokens: int = 256,
) -> Candidate:
    return Candidate(
        id=id,
        display_name=id,
        family=family,
        max_tokens=max_tokens,
        tiers=["tier_1", "tier_2", "tier_3"],
        binding=CandidateBinding(
            provider="azure_foundry",
            endpoint="https://example.com",
            deployment=deployment,
            key_vault_secret_name="foundry-account-key",
        ),
    )


_DEFAULT_EVALUATORS: dict[str, str] = {
    "t1.classification_accuracy": "exact_match",
    "t2.schema_validity": "json_schema",
    "t3.contains_keyword": "regex_match",
}


# ---------------------------------------------------------------------------
# Mock binding helpers
# ---------------------------------------------------------------------------


class _MockBinding(BindingPlugin):
    """A binding whose `invoke` is supplied by a callable.

    The callable receives (candidate, prompt, max_tokens) and returns a
    `BindingResponse` or raises. The binding records every call so tests
    can assert on what the engine sent.
    """

    name = "mock"

    def __init__(self, fn) -> None:
        self._fn = fn
        self.calls: list[tuple[Candidate, str, int]] = []

    def invoke(self, candidate, prompt, max_tokens) -> BindingResponse:
        self.calls.append((candidate, prompt, max_tokens))
        return self._fn(candidate, prompt, max_tokens)


def _ok_response(
    text: str,
    deployment: str,
    *,
    reasoning: str | None = None,
    finish_reason: str = "stop",
) -> BindingResponse:
    return BindingResponse(
        content=text,
        reasoning_content=reasoning,
        usage=TokenUsage(prompt_tokens=5, completion_tokens=3, total_tokens=8),
        latency_ms=10,
        model_deployment=deployment,
        finish_reason=finish_reason,
    )


def _http_status(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.com/x")
    response = httpx.Response(code, request=request)
    return httpx.HTTPStatusError(f"status {code}", request=request, response=response)


def _make_engine(binding: BindingPlugin, **overrides: Any) -> MatrixEngine:
    kwargs: dict[str, Any] = {
        "max_workers": overrides.get("max_workers", 2),
        "retry_attempts": overrides.get("retry_attempts", 3),
        "retry_base_delay_s": overrides.get("retry_base_delay_s", 0.0),
        "sleep": overrides.get("sleep", lambda _s: None),
        "clock": overrides.get(
            "clock", lambda: datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
        ),
        "run_id_factory": overrides.get("run_id_factory", lambda: "deadbeef"),
        "binding_factory": overrides.get(
            "binding_factory", lambda _provider: binding
        ),
    }
    if "evaluator_factory" in overrides:
        kwargs["evaluator_factory"] = overrides["evaluator_factory"]
    return MatrixEngine(**kwargs)


# ---------------------------------------------------------------------------
# Acceptance-shape tests (mirror the slice-acceptance assertions)
# ---------------------------------------------------------------------------


def test_run_returns_matrix_run_with_results_per_cell():
    """End-to-end: rubric × datasets × candidates → MatrixRun with one
    result per (candidate × example × dimension).
    """

    def respond(candidate, prompt, max_tokens):
        # Tier-aware canned responses so each evaluator scores something
        # meaningful (and pass) for the assertion.
        if "classify A" in prompt:
            return _ok_response("A", candidate.binding.deployment)
        if "classify B" in prompt:
            return _ok_response("B", candidate.binding.deployment)
        if "emit json" in prompt:
            return _ok_response('{"ok": true}', candidate.binding.deployment)
        if "answer question" in prompt:
            return _ok_response(
                "I love dogs in the park.", candidate.binding.deployment
            )
        raise AssertionError(f"unexpected prompt: {prompt}")

    binding = _MockBinding(respond)
    engine = _make_engine(binding)
    rubric = _rubric_three_tiers()
    candidates = [_candidate("c1"), _candidate("c2", deployment="Phi-4")]

    run = engine.run(
        rubric,
        _datasets_three_tiers(),
        candidates,
        dimension_evaluators=_DEFAULT_EVALUATORS,
    )

    assert isinstance(run, MatrixRun)
    assert run.id == "deadbeef"
    assert run.rubric_version == "v0.1"
    assert run.completed_at is not None
    assert run.completed_at >= run.started_at

    # 2 candidates × (2 + 1 + 1 examples) × 1 dim/tier = 8 results
    assert len(run.results) == 8

    # Every dimension covered for every candidate, on the correct tier.
    by_candidate_tier: dict[tuple[str, str], list[MatrixRunResult]] = {}
    for r in run.results:
        by_candidate_tier.setdefault((r.candidate_id, r.tier_id), []).append(r)
    for cid in ("c1", "c2"):
        assert {t for (c, t) in by_candidate_tier if c == cid} == {
            "tier_1",
            "tier_2",
            "tier_3",
        }

    # Acceptance-criterion-shape: scores_for_tier returns scorecards per tier.
    for tier_id in ("tier_1", "tier_2", "tier_3"):
        cards = run.scores_for_tier(tier_id)
        assert len(cards) == 2  # one per candidate
        for card in cards:
            assert Decimal("0") <= card.weighted_score <= Decimal("100")

    # All expected-pass examples scored 100.
    for r in run.results:
        assert r.score.error is None
        assert r.score.passed is True
        assert r.score.normalized_score == Decimal("100")


def test_rubric_version_is_pinned_on_the_run():
    binding = _MockBinding(lambda c, p, mt: _ok_response("A", c.binding.deployment))
    engine = _make_engine(binding)
    rubric = _rubric_three_tiers()
    run = engine.run(
        rubric,
        [
            Dataset(
                id="ds",
                name="t1",
                version="v0.1",
                tier_id="tier_1",
                examples=[
                    DatasetExample(id="e", input="x", expected={"value": "A"})
                ],
            )
        ],
        [_candidate("c1")],
        dimension_evaluators=_DEFAULT_EVALUATORS,
    )
    assert run.rubric_version == rubric.version


# ---------------------------------------------------------------------------
# Reasoning-content routing (MLI-165 §2)
# ---------------------------------------------------------------------------


class _ReasoningEvaluator(EvaluatorPlugin):
    """Test evaluator that scores `reasoning_content` and records what it saw."""

    name = "_test_reasoning_evaluator"
    scores_field = SourceField.REASONING_CONTENT
    received: list[str] = []

    def evaluate(self, candidate_output, expected, context):
        type(self).received.append(candidate_output)
        from mmfp.evaluators.deterministic._helpers import make_score

        return make_score(
            context=context,
            evaluator_name=self.name,
            source_field=self.scores_field,
            raw_value={"got": candidate_output},
            passed=True,
            reason="seen",
        )


def test_evaluator_with_reasoning_field_receives_reasoning_content():
    _ReasoningEvaluator.received = []

    binding = _MockBinding(
        lambda c, p, mt: _ok_response(
            "visible answer",
            c.binding.deployment,
            reasoning="hidden trace",
        )
    )
    rubric = Rubric(
        version="v0.1",
        tiers=[
            Tier(
                id="tier_3",
                name="t3",
                intent="x",
                mode=EvaluationMode.SINGLE_TURN,
                dimensions=[
                    Dimension(
                        id="t3.reasoning_quality",
                        name="Reasoning Quality",
                        description="x",
                        weight=Decimal("100"),
                        method=Method.QUALITATIVE,
                        evaluator="_test_reasoning_evaluator",
                    )
                ],
            )
        ],
        judge=_judge(),
    )
    datasets = [
        Dataset(
            id="ds",
            name="t3",
            version="v0.1",
            tier_id="tier_3",
            examples=[DatasetExample(id="e", input="x", expected={})],
        )
    ]
    engine = _make_engine(
        binding,
        evaluator_factory=lambda _name: _ReasoningEvaluator(),
    )
    run = engine.run(
        rubric,
        datasets,
        [_candidate("c1", family=CandidateFamily.REASONING)],
        dimension_evaluators={"t3.reasoning_quality": "_test_reasoning_evaluator"},
    )

    assert _ReasoningEvaluator.received == ["hidden trace"]
    assert all(r.score.source_field is SourceField.REASONING_CONTENT for r in run.results)


def test_reasoning_evaluator_on_chat_model_marks_errored():
    """MLI-165 §2: scoring reasoning_content on a chat model has no field
    to score; surface as an errored cell rather than silently scoring "".
    """
    _ReasoningEvaluator.received = []

    binding = _MockBinding(
        lambda c, p, mt: _ok_response("visible only", c.binding.deployment)
    )  # reasoning=None
    rubric = Rubric(
        version="v0.1",
        tiers=[
            Tier(
                id="tier_3",
                name="t3",
                intent="x",
                mode=EvaluationMode.SINGLE_TURN,
                dimensions=[
                    Dimension(
                        id="t3.reasoning_quality",
                        name="x",
                        description="x",
                        weight=Decimal("100"),
                        method=Method.QUALITATIVE,
                        evaluator="_test_reasoning_evaluator",
                    )
                ],
            )
        ],
        judge=_judge(),
    )
    engine = _make_engine(
        binding, evaluator_factory=lambda _n: _ReasoningEvaluator()
    )
    run = engine.run(
        rubric,
        [
            Dataset(
                id="d",
                name="d",
                version="v0.1",
                tier_id="tier_3",
                examples=[DatasetExample(id="e", input="x", expected={})],
            )
        ],
        [_candidate("c1", family=CandidateFamily.CHAT)],
        dimension_evaluators={"t3.reasoning_quality": "_test_reasoning_evaluator"},
    )

    assert _ReasoningEvaluator.received == []
    assert len(run.results) == 1
    assert run.results[0].score.error is not None
    assert "reasoning_content" in run.results[0].score.error


# ---------------------------------------------------------------------------
# Failure isolation + retry policy
# ---------------------------------------------------------------------------


def test_single_candidate_failure_does_not_abort_run():
    def respond(candidate, prompt, max_tokens):
        if candidate.id == "c_bad":
            raise _http_status(400)  # non-retriable
        return _ok_response("A", candidate.binding.deployment)

    binding = _MockBinding(respond)
    engine = _make_engine(binding, retry_attempts=1)

    rubric = _rubric_three_tiers()
    datasets = _datasets_three_tiers()
    candidates = [_candidate("c_bad"), _candidate("c_ok", deployment="Phi-4")]

    run = engine.run(
        rubric, datasets, candidates, dimension_evaluators=_DEFAULT_EVALUATORS
    )

    bad_results = [r for r in run.results if r.candidate_id == "c_bad"]
    ok_results = [r for r in run.results if r.candidate_id == "c_ok"]

    assert all(r.score.error is not None for r in bad_results)
    assert all("binding error" in r.score.error for r in bad_results)
    assert all(r.score.error is None for r in ok_results)


def test_429_is_retried_with_exponential_backoff():
    sleeps: list[float] = []
    state = {"attempts": 0}

    def respond(candidate, prompt, max_tokens):
        state["attempts"] += 1
        if state["attempts"] < 3:
            raise _http_status(429)
        return _ok_response("A", candidate.binding.deployment)

    binding = _MockBinding(respond)
    engine = _make_engine(
        binding,
        retry_attempts=3,
        retry_base_delay_s=1.0,
        sleep=sleeps.append,
    )

    run = engine.run(
        _rubric_three_tiers(),
        [
            Dataset(
                id="ds",
                name="t1",
                version="v0.1",
                tier_id="tier_1",
                examples=[
                    DatasetExample(id="e", input="x", expected={"value": "A"})
                ],
            )
        ],
        [_candidate("c1")],
        dimension_evaluators=_DEFAULT_EVALUATORS,
    )

    assert state["attempts"] == 3
    assert sleeps == [1.0, 2.0]
    assert run.results[0].score.error is None
    assert run.results[0].score.passed is True


def test_persistent_5xx_marks_cell_errored():
    def _raise(*_args):
        raise _http_status(503)

    binding = _MockBinding(_raise)
    engine = _make_engine(binding, retry_attempts=2)

    run = engine.run(
        _rubric_three_tiers(),
        [
            Dataset(
                id="ds",
                name="t1",
                version="v0.1",
                tier_id="tier_1",
                examples=[
                    DatasetExample(id="e", input="x", expected={"value": "A"})
                ],
            )
        ],
        [_candidate("c1")],
        dimension_evaluators=_DEFAULT_EVALUATORS,
    )
    assert run.results[0].score.error is not None
    assert "binding error" in run.results[0].score.error


def test_evaluator_raising_is_captured_as_errored_score():
    class _BoomEvaluator(EvaluatorPlugin):
        name = "_test_boom"
        scores_field = SourceField.CONTENT

        def evaluate(self, candidate_output, expected, context):
            raise RuntimeError("evaluator exploded")

    binding = _MockBinding(lambda c, p, mt: _ok_response("x", c.binding.deployment))
    rubric = Rubric(
        version="v0.1",
        tiers=[
            Tier(
                id="tier_1",
                name="t1",
                intent="x",
                mode=EvaluationMode.SINGLE_TURN,
                dimensions=[
                    Dimension(
                        id="dim",
                        name="x",
                        description="x",
                        weight=Decimal("100"),
                        method=Method.DETERMINISTIC,
                        evaluator="_test_boom",
                    )
                ],
            )
        ],
        judge=_judge(),
    )
    engine = _make_engine(
        binding, evaluator_factory=lambda _n: _BoomEvaluator()
    )
    run = engine.run(
        rubric,
        [
            Dataset(
                id="ds",
                name="t1",
                version="v0.1",
                tier_id="tier_1",
                examples=[DatasetExample(id="e", input="x", expected={})],
            )
        ],
        [_candidate("c1")],
        dimension_evaluators={"dim": "_test_boom"},
    )
    assert run.results[0].score.error == "RuntimeError: evaluator exploded"
    assert run.results[0].score.normalized_score == Decimal("0")


# ---------------------------------------------------------------------------
# Coverage validation
# ---------------------------------------------------------------------------


def test_missing_dimension_evaluator_raises_before_any_invocation():
    binding = _MockBinding(lambda *args: pytest.fail("must not be called"))
    engine = _make_engine(binding)

    with pytest.raises(ValueError, match="dimension_evaluators missing"):
        engine.run(
            _rubric_three_tiers(),
            _datasets_three_tiers(),
            [_candidate("c1")],
            dimension_evaluators={
                "t1.classification_accuracy": "exact_match",
                # tier 2 + tier 3 missing
            },
        )


def test_unknown_evaluator_name_raises_before_any_invocation():
    binding = _MockBinding(lambda *args: pytest.fail("must not be called"))

    def evaluator_factory(name: str) -> EvaluatorPlugin:
        # Default factory hits the registry; simulate an unknown name.
        from mmfp.evaluators import _registry

        return _registry.get(name)()

    engine = _make_engine(binding, evaluator_factory=evaluator_factory)

    with pytest.raises(KeyError):
        engine.run(
            _rubric_three_tiers(),
            _datasets_three_tiers(),
            [_candidate("c1")],
            dimension_evaluators={
                "t1.classification_accuracy": "exact_match",
                "t2.schema_validity": "json_schema",
                "t3.contains_keyword": "no_such_evaluator",
            },
        )


# ---------------------------------------------------------------------------
# Engine / binding contract details
# ---------------------------------------------------------------------------


def test_uses_candidate_max_tokens_when_invoking():
    binding = _MockBinding(lambda c, p, mt: _ok_response("A", c.binding.deployment))
    engine = _make_engine(binding)
    rubric = _rubric_three_tiers()
    cand = _candidate("c1", max_tokens=1234)

    engine.run(
        rubric,
        _datasets_three_tiers(),
        [cand],
        dimension_evaluators=_DEFAULT_EVALUATORS,
    )

    # All four examples were invoked with the candidate's declared budget.
    max_tokens_used = {call[2] for call in binding.calls}
    assert max_tokens_used == {1234}


def test_persisted_token_usage_and_finish_reason_come_from_binding_response():
    response = BindingResponse(
        content="A",
        usage=TokenUsage(prompt_tokens=42, completion_tokens=7, total_tokens=49),
        latency_ms=12,
        model_deployment="dep",
        finish_reason="length",
    )
    binding = _MockBinding(lambda c, p, mt: response)
    engine = _make_engine(binding)

    run = engine.run(
        _rubric_three_tiers(),
        [
            Dataset(
                id="ds",
                name="t1",
                version="v0.1",
                tier_id="tier_1",
                examples=[
                    DatasetExample(id="e", input="x", expected={"value": "A"})
                ],
            )
        ],
        [_candidate("c1")],
        dimension_evaluators=_DEFAULT_EVALUATORS,
    )
    r = run.results[0]
    assert r.prompt_tokens == 42
    assert r.completion_tokens == 7
    assert r.finish_reason == "length"


def test_binding_close_is_called_after_run():
    closed: list[bool] = []

    class _ClosableBinding(_MockBinding):
        def close(self) -> None:
            closed.append(True)

    binding = _ClosableBinding(
        lambda c, p, mt: _ok_response("A", c.binding.deployment)
    )
    engine = _make_engine(binding)
    engine.run(
        _rubric_three_tiers(),
        [
            Dataset(
                id="ds",
                name="t1",
                version="v0.1",
                tier_id="tier_1",
                examples=[
                    DatasetExample(id="e", input="x", expected={"value": "A"})
                ],
            )
        ],
        [_candidate("c1")],
        dimension_evaluators=_DEFAULT_EVALUATORS,
    )
    assert closed == [True]


def test_dict_input_is_json_serialised_for_the_prompt():
    seen: list[str] = []

    def respond(candidate, prompt, max_tokens):
        seen.append(prompt)
        return _ok_response("A", candidate.binding.deployment)

    binding = _MockBinding(respond)
    engine = _make_engine(binding)
    engine.run(
        _rubric_three_tiers(),
        [
            Dataset(
                id="ds",
                name="t1",
                version="v0.1",
                tier_id="tier_1",
                examples=[
                    DatasetExample(
                        id="e",
                        input={"system": "you classify", "user": "X"},
                        expected={"value": "A"},
                    )
                ],
            )
        ],
        [_candidate("c1")],
        dimension_evaluators=_DEFAULT_EVALUATORS,
    )
    assert seen == ['{"system": "you classify", "user": "X"}']


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


def test_per_candidate_concurrency_overlaps_invocations():
    """Two candidates, each with a slow binding. With max_workers=2 both
    invocations should run concurrently — verified via a Barrier that
    deadlocks if work is serialised.
    """
    n_candidates = 2
    barrier = threading.Barrier(n_candidates, timeout=2.0)

    def respond(candidate, prompt, max_tokens):
        # Each candidate's first invoke waits for the others; if work is
        # serial, the barrier times out and the test fails loudly.
        barrier.wait()
        return _ok_response("A", candidate.binding.deployment)

    binding = _MockBinding(respond)
    engine = _make_engine(binding, max_workers=n_candidates)
    rubric = _rubric_three_tiers()
    candidates = [
        _candidate(f"c{i}", deployment=f"dep{i}") for i in range(n_candidates)
    ]

    start = time.perf_counter()
    run = engine.run(
        rubric,
        [
            Dataset(
                id="ds",
                name="t1",
                version="v0.1",
                tier_id="tier_1",
                examples=[
                    DatasetExample(id="e", input="x", expected={"value": "A"})
                ],
            )
        ],
        candidates,
        dimension_evaluators=_DEFAULT_EVALUATORS,
    )
    duration = time.perf_counter() - start
    # Sanity: didn't deadlock
    assert len(run.results) == n_candidates
    assert duration < 2.0


# ---------------------------------------------------------------------------
# In-process integration: real evaluators + a stand-alone fake binding
# ---------------------------------------------------------------------------


class _FakeFoundryBinding(BindingPlugin):
    """A tiny in-process fake of a real provider — no httpx, no network.

    Returns a fixed canned answer per (deployment, prompt) tuple, so the
    full rubric × dataset × candidate matrix runs end-to-end against real
    evaluators (exact_match / json_schema / regex_match).
    """

    name = "fake_foundry"

    _ANSWERS: dict[tuple[str, str], str] = {
        ("Kimi-K2.6", "classify A"): "A",
        ("Kimi-K2.6", "classify B"): "B",
        ("Kimi-K2.6", "emit json"): '{"ok": true}',
        ("Kimi-K2.6", "answer question"): "dogs are great companions.",
        ("Phi-4", "classify A"): "A",
        ("Phi-4", "classify B"): "wrong-label",  # one mis-classification
        ("Phi-4", "emit json"): '{"ok": "yes"}',  # schema violation
        ("Phi-4", "answer question"): "cats are great companions.",  # regex miss
    }

    def invoke(self, candidate, prompt, max_tokens) -> BindingResponse:
        text = self._ANSWERS[(candidate.binding.deployment, prompt)]
        return BindingResponse(
            content=text,
            usage=TokenUsage(
                prompt_tokens=len(prompt) // 4,
                completion_tokens=len(text) // 4 or 1,
                total_tokens=(len(prompt) + len(text)) // 4 or 1,
            ),
            latency_ms=1,
            model_deployment=candidate.binding.deployment,
            finish_reason="stop",
        )


def test_integration_with_real_evaluators_and_fake_binding():
    binding = _FakeFoundryBinding()
    engine = _make_engine(binding)

    rubric = _rubric_three_tiers()
    candidates = [
        _candidate("kimi", deployment="Kimi-K2.6"),
        _candidate("phi", deployment="Phi-4"),
    ]

    run = engine.run(
        rubric,
        _datasets_three_tiers(),
        candidates,
        dimension_evaluators=_DEFAULT_EVALUATORS,
    )

    # Kimi answers correctly on every cell.
    kimi_scores = run.scores_for_tier("tier_1")
    kimi_card = next(c for c in kimi_scores if c.candidate_id == "kimi")
    phi_card = next(c for c in kimi_scores if c.candidate_id == "phi")
    # Tier 1: kimi gets 100 (both A and B exact-match), phi gets 50 (only A).
    assert kimi_card.weighted_score == Decimal("100")
    assert phi_card.weighted_score == Decimal("50")

    # Tier 2: kimi's json validates, phi's doesn't.
    t2 = {c.candidate_id: c for c in run.scores_for_tier("tier_2")}
    assert t2["kimi"].weighted_score == Decimal("100")
    assert t2["phi"].weighted_score == Decimal("0")

    # Tier 3: kimi mentions dogs, phi doesn't.
    t3 = {c.candidate_id: c for c in run.scores_for_tier("tier_3")}
    assert t3["kimi"].weighted_score == Decimal("100")
    assert t3["phi"].weighted_score == Decimal("0")


# ---------------------------------------------------------------------------
# Tier filtering (MLI-259)
# ---------------------------------------------------------------------------


def _canned_response(candidate, prompt, _max_tokens):
    # Tier-1/2/3 canned answers that match the prompts emitted by
    # `_datasets_three_tiers()`. Any prompt the engine actually sends gets a
    # valid response; if filtering broke and we ran a cross-tier cell we'd
    # still get a number, so the test asserts on the result *grid* shape and
    # on which (candidate, tier) pairs hit the binding — not on scores.
    canned = {
        "classify A": "A",
        "classify B": "B",
        "emit json": '{"ok": true}',
        "answer question": "I love dogs.",
    }
    return _ok_response(canned[prompt], candidate.binding.deployment)


def test_engine_skips_candidate_tier_pairs_outside_candidate_tiers(caplog):
    """Real `products/mli/candidates.yaml` slate — only 4 of 10 candidates
    cover every tier today; the rest are tier-restricted (MLI-178 live
    Foundry run showed Phi-4 burning Tier 3 cells that never feed a routing
    decision). Engine must skip `(candidate, tier)` pairs where
    `tier.id not in candidate.tiers`: no binding call, no LangSmith span,
    no `MatrixRunResult`.
    """
    candidates = load_candidates(MLI_CANDIDATES_YAML)
    # Sanity: this test depends on the slate having tier-restricted
    # candidates. If a future slate edit makes every candidate cover every
    # tier, the test becomes trivially green and we need to revisit.
    assert any(set(c.tiers) != {"tier_1", "tier_2", "tier_3"} for c in candidates)

    binding = _MockBinding(_canned_response)
    engine = _make_engine(binding)
    rubric = _rubric_three_tiers()
    datasets = _datasets_three_tiers()

    with caplog.at_level(logging.INFO, logger="mmfp.engine.matrix"):
        run = engine.run(
            rubric, datasets, candidates, dimension_evaluators=_DEFAULT_EVALUATORS
        )

    # 1. No result exists for a (candidate, tier) pair outside candidate.tiers.
    tiers_by_candidate = {c.id: set(c.tiers) for c in candidates}
    for r in run.results:
        assert r.tier_id in tiers_by_candidate[r.candidate_id], (
            f"{r.candidate_id} scored on {r.tier_id} but claims tiers="
            f"{sorted(tiers_by_candidate[r.candidate_id])}"
        )

    # 2. Result count matches the filtered grid exactly. The three-tier
    # rubric in this file has 1 dimension per tier and (2, 1, 1) examples
    # per tier; expected = sum over candidates of sum over claimed tiers of
    # examples_per_tier.
    examples_per_tier = {"tier_1": 2, "tier_2": 1, "tier_3": 1}
    expected_results = sum(
        examples_per_tier[t] for c in candidates for t in c.tiers
    )
    assert len(run.results) == expected_results

    # 3. Specifically: `phi-4-mini-instruct` (tiers=[tier_1]) does NOT score
    # against tier_3 even though Tier 3 datasets are present. This is the
    # exact case called out in the MLI-259 acceptance criteria.
    phi_results = [r for r in run.results if r.candidate_id == "phi-4-mini-instruct"]
    assert phi_results, "expected Phi-4 mini to score *some* cells (tier_1)"
    assert {r.tier_id for r in phi_results} == {"tier_1"}

    # 4. And the cross-tier example: `gpt-4-1-mini` (tiers=[tier_1, tier_2])
    # is scored on tier_1 and tier_2 but never tier_3.
    gpt_mini_results = [r for r in run.results if r.candidate_id == "gpt-4-1-mini"]
    assert {r.tier_id for r in gpt_mini_results} == {"tier_1", "tier_2"}

    # 5. The binding was not invoked for skipped pairs. We can't distinguish
    # tier directly from a binding call (prompts repeat across tiers via
    # `_to_prompt`), so assert per (candidate, prompt): a candidate is only
    # asked prompts whose tier it claims.
    prompts_by_tier = {
        "tier_1": {"classify A", "classify B"},
        "tier_2": {"emit json"},
        "tier_3": {"answer question"},
    }
    allowed_prompts: dict[str, set[str]] = {
        c.id: set().union(*(prompts_by_tier[t] for t in c.tiers)) for c in candidates
    }
    for c, prompt, _mt in binding.calls:
        assert prompt in allowed_prompts[c.id], (
            f"binding invoked for {c.id} with prompt {prompt!r} but candidate's "
            f"tiers={sorted(tiers_by_candidate[c.id])} don't cover it"
        )

    # 6. Single INFO log per run summarising skipped-pair counts and ran-pair
    # counts (the audit trail MLI-259 requires before the next live Foundry
    # run, per MLI-178 cost-leak follow-up).
    summary_records = [
        rec
        for rec in caplog.records
        if rec.name == "mmfp.engine.matrix" and "tier filter" in rec.getMessage()
    ]
    assert len(summary_records) == 1
    msg = summary_records[0].getMessage()
    # Breakdown by tier present in the message.
    assert "'tier_1'" in msg and "'tier_2'" in msg and "'tier_3'" in msg
    # Totals: 16 skipped pairs, 14 ran pairs, 10 candidates (counted from the
    # live slate above — fails loudly if the slate changes so the next reader
    # knows to re-derive the expected numbers).
    total_pairs = len(candidates) * len(rubric.tiers)
    ran_pairs = sum(len(c.tiers) for c in candidates)
    skipped_pairs = total_pairs - ran_pairs
    assert f"skipped {skipped_pairs}" in msg
    assert f"ran {ran_pairs}" in msg
    assert f"across {len(candidates)} candidate(s)" in msg
