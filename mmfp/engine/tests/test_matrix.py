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

import threading
import time
from datetime import datetime, timezone
from decimal import Decimal
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
