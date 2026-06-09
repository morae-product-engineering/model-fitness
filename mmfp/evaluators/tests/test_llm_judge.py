"""LLMJudgeEvaluator unit tests (MFP-74).

The judge calls a model under the hood, so every test injects a fake
BindingPlugin whose `invoke` returns a scripted `BindingResponse`. No network.

Covered:
  - happy path: well-formed JSON -> normalised score, content source field
  - malformed JSON, retry succeeds on the stricter second prompt
  - malformed JSON twice -> low-confidence error score, no raise
  - sampling: a deterministic RNG seed verifies the configured rate writes
    to the judge_samples.jsonl queue
  - cost guard: cumulative tokens over budget raises JudgeBudgetExceededError
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from mmfp.models.binding_response import BindingResponse, TokenUsage
from mmfp.models.candidate import (
    Candidate,
    CandidateBinding,
    CandidateFamily,
)
from mmfp.models.matrix_run import SourceField


class FakeBinding:
    """A scripted BindingPlugin. Each invoke pops the next scripted response.

    `name` and `invoke` satisfy the structural contract the evaluator uses;
    it does not subclass BindingPlugin because the evaluator only calls
    `invoke` (duck-typed seam — same as the engine's binding factory).
    """

    name = "fake"

    def __init__(self, responses: list[BindingResponse]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []
        self.calls = 0

    def invoke(self, candidate, prompt, max_tokens):  # noqa: ANN001
        self.calls += 1
        self.prompts.append(prompt)
        if not self._responses:
            raise AssertionError("FakeBinding.invoke called more times than scripted")
        return self._responses.pop(0)


def _response(
    text: str, *, prompt_tokens: int = 100, completion_tokens: int = 50
) -> BindingResponse:
    return BindingResponse(
        content=text,
        usage=TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
        latency_ms=12,
        model_deployment="judge-deployment",
        finish_reason="stop",
    )


def _judge_candidate() -> Candidate:
    return Candidate(
        id="judge-model",
        display_name="Judge Model",
        family=CandidateFamily.CHAT,
        max_tokens=1024,
        context_window=128_000,
        binding=CandidateBinding(
            provider="fake",
            endpoint="https://judge.example.com",
            deployment="judge-deployment",
            key_vault_secret_name="judge-key",
        ),
        tiers=["tier_3"],
    )


def _judge_json(score: float, confidence: str = "high", reasoning: str = "looks good") -> str:
    return json.dumps({"score": score, "reasoning": reasoning, "confidence": confidence})


@pytest.fixture
def prompt_file(tmp_path):
    """A stand-in for MFP-73's prompt. Real file ships in MFP-73; the
    evaluator only needs the placeholders it formats."""
    p = tmp_path / "synthesis_quality_v1.md"
    p.write_text(
        "Question: {question}\n"
        "Expected: {expected_themes_or_facts}\n"
        "Candidate: {candidate_output}\n"
        "Dimension: {rubric_dimension_definition}\n"
    )
    return p


def _make_evaluator(prompt_file, binding, *, judge_candidate=None):
    from mmfp.evaluators.inferential.llm_judge import LLMJudgeEvaluator

    return LLMJudgeEvaluator(
        prompt_path=str(prompt_file),
        binding=binding,
        judge_candidate=judge_candidate or _judge_candidate(),
    )


def _ctx(tmp_path, **overrides):
    ctx = {
        "dimension_id": "synthesis_quality",
        "dimension_description": "Does the answer synthesise the source material?",
        "run_id": "run-001",
        "candidate_id": "cand-xyz",
        "product_id": "mli",
        "evaluator_config": {
            "products_root": str(tmp_path),
            "sample_rate": 0.0,
            "max_tokens_per_run": 500_000,
        },
    }
    ec = overrides.pop("evaluator_config", {})
    ctx["evaluator_config"].update(ec)
    ctx.update(overrides)
    return ctx


# --- happy path -----------------------------------------------------------


def test_happy_path_parses_score_and_scales_to_0_100(prompt_file, tmp_path):
    binding = FakeBinding([_response(_judge_json(0.8))])
    ev = _make_evaluator(prompt_file, binding)
    score = ev.evaluate(
        "the candidate's synthesised answer",
        {"themes": ["a", "b"]},
        _ctx(tmp_path),
    )
    assert binding.calls == 1
    assert score.raw_value["score"] == 0.8
    assert score.normalized_score == Decimal("80.00")
    assert score.source_field == SourceField.CONTENT
    assert score.error is None
    assert score.passed is None


def test_prompt_is_formatted_with_all_placeholders(prompt_file, tmp_path):
    binding = FakeBinding([_response(_judge_json(0.5))])
    ev = _make_evaluator(prompt_file, binding)
    ev.evaluate("CAND-TEXT", {"facts": ["F1"]}, _ctx(tmp_path, question="Q-TEXT"))
    sent = binding.prompts[0]
    assert "Q-TEXT" in sent
    assert "CAND-TEXT" in sent
    assert "F1" in sent
    assert "synthesise the source material" in sent


def test_confidence_carried_in_raw_value(prompt_file, tmp_path):
    binding = FakeBinding([_response(_judge_json(0.9, confidence="medium"))])
    ev = _make_evaluator(prompt_file, binding)
    score = ev.evaluate("x", {}, _ctx(tmp_path))
    assert score.raw_value["confidence"] == "medium"


# --- retry / parse-failure ------------------------------------------------


def test_malformed_json_retries_once_and_succeeds(prompt_file, tmp_path):
    binding = FakeBinding([_response("not json at all"), _response(_judge_json(0.6))])
    ev = _make_evaluator(prompt_file, binding)
    score = ev.evaluate("x", {}, _ctx(tmp_path))
    assert binding.calls == 2
    assert score.normalized_score == Decimal("60.00")
    assert score.error is None
    # The retry prompt must differ from the first (stricter framing).
    assert binding.prompts[1] != binding.prompts[0]


def test_two_parse_failures_return_low_confidence_error_score(prompt_file, tmp_path):
    binding = FakeBinding([_response("garbage"), _response("still garbage")])
    ev = _make_evaluator(prompt_file, binding)
    score = ev.evaluate("x", {}, _ctx(tmp_path))
    assert binding.calls == 2
    assert score.error is not None
    assert score.normalized_score == Decimal("0")
    assert score.raw_value is None or score.raw_value == {}


def test_out_of_range_score_treated_as_parse_failure(prompt_file, tmp_path):
    # 1.5 is outside [0,1]; first call invalid, second valid -> recovers.
    binding = FakeBinding([_response(_judge_json(1.5)), _response(_judge_json(0.4))])
    ev = _make_evaluator(prompt_file, binding)
    score = ev.evaluate("x", {}, _ctx(tmp_path))
    assert binding.calls == 2
    assert score.normalized_score == Decimal("40.00")


# --- sampling -------------------------------------------------------------


def test_sample_rate_one_always_writes_queue(prompt_file, tmp_path):
    binding = FakeBinding([_response(_judge_json(0.7))])
    ev = _make_evaluator(prompt_file, binding)
    ev.evaluate(
        "candidate text",
        {},
        _ctx(tmp_path, evaluator_config={"sample_rate": 1.0}),
    )
    queue = tmp_path / "mli" / "judge_samples.jsonl"
    assert queue.exists()
    entry = json.loads(queue.read_text().strip())
    assert entry["run_id"] == "run-001"
    assert entry["candidate_id"] == "cand-xyz"
    assert entry["dimension_id"] == "synthesis_quality"
    assert entry["judge_score"] == 0.7
    assert entry["judge_confidence"] == "high"
    assert "sample_id" in entry and "created_at" in entry


def test_sample_rate_zero_never_writes_queue(prompt_file, tmp_path):
    binding = FakeBinding([_response(_judge_json(0.7))])
    ev = _make_evaluator(prompt_file, binding)
    ev.evaluate("x", {}, _ctx(tmp_path, evaluator_config={"sample_rate": 0.0}))
    assert not (tmp_path / "mli" / "judge_samples.jsonl").exists()


def test_sampling_rate_is_statistically_honoured(prompt_file, tmp_path):
    """Over many judgements at rate 0.2, the sampled fraction lands near 0.2.

    Deterministic: the evaluator seeds its RNG so the count is fixed for a
    given seed, not flaky. We assert a tolerant band, not an exact count."""
    n = 400
    binding = FakeBinding([_response(_judge_json(0.5)) for _ in range(n)])
    ev = _make_evaluator(prompt_file, binding)
    for _ in range(n):
        ev.evaluate("x", {}, _ctx(tmp_path, evaluator_config={"sample_rate": 0.2}))
    queue = tmp_path / "mli" / "judge_samples.jsonl"
    sampled = len(queue.read_text().splitlines()) if queue.exists() else 0
    assert 0.12 * n <= sampled <= 0.28 * n


# --- cost guard -----------------------------------------------------------


def test_budget_exceeded_raises_before_next_call(prompt_file, tmp_path):
    from mmfp.evaluators.inferential.llm_judge import JudgeBudgetExceededError

    # Each call burns 150 tokens (100 prompt + 50 completion). Budget 100:
    # the first call runs (nothing accumulated yet), leaving the run at 150
    # tokens; the second call sees cumulative 150 > 100 and trips the guard
    # before invoking the binding again.
    binding = FakeBinding(
        [_response(_judge_json(0.5)), _response(_judge_json(0.5))]
    )
    ev = _make_evaluator(prompt_file, binding)
    ctx = _ctx(tmp_path, evaluator_config={"max_tokens_per_run": 100})
    ev.evaluate("x", {}, ctx)  # 150 cumulative after this call
    with pytest.raises(JudgeBudgetExceededError):
        ev.evaluate("x", {}, ctx)  # cumulative 150 > 100 -> raise
    # The second judge call must not have been made.
    assert binding.calls == 1


def test_budget_tracked_per_run_id(prompt_file, tmp_path):
    """Different run_ids have independent budgets."""
    binding = FakeBinding(
        [_response(_judge_json(0.5)), _response(_judge_json(0.5))]
    )
    ev = _make_evaluator(prompt_file, binding)
    cfg = {"max_tokens_per_run": 100}
    ev.evaluate("x", {}, _ctx(tmp_path, run_id="run-A", evaluator_config=cfg))
    # run-B starts fresh; this call succeeds despite run-A's usage.
    score = ev.evaluate("x", {}, _ctx(tmp_path, run_id="run-B", evaluator_config=cfg))
    assert score.error is None
    assert binding.calls == 2


# --- registration ---------------------------------------------------------


def test_registered_under_expected_name():
    from mmfp.evaluators import get

    cls = get("llm_judge_synthesis_quality")
    assert cls.name == "llm_judge_synthesis_quality"
    assert cls.scores_field == SourceField.CONTENT
