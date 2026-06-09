"""LLM-judge evaluator for the `synthesis_quality` dimension (MFP-74).

Scores a candidate's answer by asking a pinned judge model to rate it against
the dimension definition. The judge is itself a `Candidate`, invoked through
the standard `BindingPlugin` — this evaluator never bypasses the binding, so
LangSmith tracing wired at the binding layer applies unchanged.

Departure from the `EvaluatorPlugin` docstring's "deterministic, no side
effects" rule: inferential evaluators call a model (network) and append to a
human-review queue (disk). The rubric design explicitly tolerates this for the
inferential family — see MFP-74 brief and `mmfp.evaluators.inferential`.

Robustness:
  - Judge output is `{"score": 0.0-1.0, "reasoning": str, "confidence": ...}`.
  - On a parse/validation failure the judge is re-asked once with a stricter
    prompt suffix. A second failure yields a low-confidence error score
    (`error` set, `normalized_score` 0) rather than raising — one bad judge
    response shouldn't abort a matrix run.
  - A configurable sample of judgements is appended to a per-product
    `judge_samples.jsonl` queue for human calibration review.
  - A per-`run_id` token budget guards against a runaway run; exceeding it
    raises `JudgeBudgetExceededError` before the next judge call.

Wiring note (judgement worth review): the matrix engine's evaluator factory
instantiates evaluators with no arguments (`get(name)()`), and the dispatch
context (`mmfp.engine.matrix._evaluate_traced`) does NOT yet carry a binding
or a judge candidate. This evaluator therefore takes them via `__init__`
(injection — also the unit-test seam) and raises a clear configuration error
if asked to `evaluate` without them. Threading the judge binding + candidate
into engine dispatch is follow-up work (engine-side), out of this sub-task's
file scope.
"""

from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from mmfp.evaluators._registry import register
from mmfp.models.binding_response import BindingResponse
from mmfp.models.candidate import Candidate
from mmfp.models.matrix_run import EvaluatorScore, SourceField
from mmfp.plugins.binding import BindingPlugin
from mmfp.plugins.evaluator import EvaluatorPlugin

DEFAULT_SAMPLE_RATE = 0.05
DEFAULT_MAX_TOKENS_PER_RUN = 500_000
DEFAULT_PRODUCT_ID = "mli"

# Appended to the prompt on the single retry. The first attempt uses the
# MFP-73 prompt verbatim; if the model returned prose or fenced JSON we ask
# again, this time forbidding anything but the bare object.
_STRICT_RETRY_SUFFIX = (
    "\n\nIMPORTANT: Your previous response could not be parsed. Reply with "
    "ONLY a single JSON object and nothing else — no prose, no code fences. "
    'Shape: {"score": <number 0.0-1.0>, "reasoning": "<string>", '
    '"confidence": "low"|"medium"|"high"}.'
)


class JudgeBudgetExceededError(RuntimeError):
    """Raised when a run's cumulative judge token usage exceeds its budget."""


@register
class LLMJudgeEvaluator(EvaluatorPlugin):
    """Scores `synthesis_quality` via a pinned LLM judge."""

    name = "llm_judge_synthesis_quality"
    scores_field = SourceField.CONTENT

    def __init__(
        self,
        *,
        prompt_path: str = "products/mli/judge/prompts/synthesis_quality_v1.md",
        binding: BindingPlugin | None = None,
        judge_candidate: Candidate | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self._prompt_path = prompt_path
        self._binding = binding
        self._judge_candidate = judge_candidate
        # Seeded RNG keeps the sampling decision deterministic for a given
        # construction — tests assert a stable fraction, not a flaky one.
        self._rng = rng or random.Random(0)
        # Per-run cumulative judge token usage, for the cost guard.
        self._tokens_by_run: dict[str, int] = {}
        self._prompt_template: str | None = None

    # -- public contract ---------------------------------------------------

    def evaluate(
        self,
        candidate_output: str,
        expected: dict[str, Any],
        context: dict[str, Any],
    ) -> EvaluatorScore:
        if self._binding is None or self._judge_candidate is None:
            raise RuntimeError(
                "LLMJudgeEvaluator requires a judge binding and candidate; "
                "construct it with binding= and judge_candidate=. The engine "
                "does not yet wire these into evaluator dispatch (see module "
                "docstring)."
            )

        cfg = context.get("evaluator_config") or {}
        run_id = context.get("run_id", "")
        budget = int(cfg.get("max_tokens_per_run", DEFAULT_MAX_TOKENS_PER_RUN))

        # Cost guard: refuse to start another judge call once this run has
        # already burned more than its budget.
        if self._tokens_by_run.get(run_id, 0) > budget:
            raise JudgeBudgetExceededError(
                f"run '{run_id}' exceeded judge token budget {budget} "
                f"(used {self._tokens_by_run[run_id]})"
            )

        prompt = self._render_prompt(candidate_output, expected, context)
        judgement = self._invoke_and_parse(prompt, run_id)

        if judgement is None:
            return EvaluatorScore(
                dimension_id=context["dimension_id"],
                evaluator_id=context.get("evaluator_id", self.name),
                raw_value=None,
                normalized_score=Decimal("0"),
                passed=None,
                source_field=self.scores_field,
                error="judge output unparseable after retry; low-confidence fallback",
            )

        self._maybe_sample(judgement, candidate_output, context, cfg)

        # 0.0-1.0 -> 0-100. raw_value keeps the judge's native shape; the
        # reasoning trace is debug-only and not promoted to `reason`.
        return EvaluatorScore(
            dimension_id=context["dimension_id"],
            evaluator_id=context.get("evaluator_id", self.name),
            raw_value=judgement,
            normalized_score=(Decimal(str(judgement["score"])) * Decimal("100")).quantize(
                Decimal("0.01")
            ),
            passed=None,
            source_field=self.scores_field,
            reason=f"judge confidence: {judgement['confidence']}",
        )

    # -- internals ---------------------------------------------------------

    def _render_prompt(
        self,
        candidate_output: str,
        expected: dict[str, Any],
        context: dict[str, Any],
    ) -> str:
        if self._prompt_template is None:
            # Loaded once, lazily, so construction never touches disk (the
            # registry instantiates every evaluator at import time).
            self._prompt_template = Path(self._prompt_path).read_text(encoding="utf-8")
        return self._prompt_template.format(
            question=context.get("question", ""),
            expected_themes_or_facts=_expected_text(expected),
            candidate_output=candidate_output,
            rubric_dimension_definition=context.get("dimension_description", ""),
        )

    def _invoke_and_parse(self, prompt: str, run_id: str) -> dict[str, Any] | None:
        """Invoke the judge; on parse failure retry once with a stricter prompt.

        Returns the validated judgement dict, or None after two failures.
        Token usage from every call (including the failed first one) counts
        against the run budget.
        """
        for attempt in range(2):
            text = prompt if attempt == 0 else prompt + _STRICT_RETRY_SUFFIX
            response = self._binding.invoke(
                self._judge_candidate, text, self._judge_candidate.max_tokens
            )
            self._charge(run_id, response)
            parsed = _parse_judgement(response.content)
            if parsed is not None:
                return parsed
        return None

    def _charge(self, run_id: str, response: BindingResponse) -> None:
        self._tokens_by_run[run_id] = (
            self._tokens_by_run.get(run_id, 0) + response.usage.total_tokens
        )

    def _maybe_sample(
        self,
        judgement: dict[str, Any],
        candidate_output: str,
        context: dict[str, Any],
        cfg: dict[str, Any],
    ) -> None:
        rate = float(cfg.get("sample_rate", DEFAULT_SAMPLE_RATE))
        if rate <= 0 or self._rng.random() >= rate:
            return

        product_id = context.get("product_id", DEFAULT_PRODUCT_ID)
        # products_root is overridable so tests (and any non-default layout)
        # don't write into the real `products/` tree.
        root = Path(cfg.get("products_root", "products"))
        queue = root / product_id / "judge_samples.jsonl"
        queue.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "sample_id": uuid.uuid4().hex,
            "run_id": context.get("run_id", ""),
            "dimension_id": context["dimension_id"],
            "candidate_id": context.get("candidate_id", ""),
            "candidate_output": candidate_output,
            "judge_score": judgement["score"],
            "judge_reasoning": judgement["reasoning"],
            "judge_confidence": judgement["confidence"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with queue.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")


_VALID_CONFIDENCE = {"low", "medium", "high"}


def _parse_judgement(text: str) -> dict[str, Any] | None:
    """Parse and validate the judge's JSON. Returns None on any failure.

    Validates the full contract — JSON-decodable, all three keys present,
    score numeric and in [0.0, 1.0], confidence in the allowed set — so a
    structurally-valid-but-out-of-contract response triggers the retry path
    rather than producing a garbage score.
    """
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    if not {"score", "reasoning", "confidence"} <= data.keys():
        return None
    score = data["score"]
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        return None
    if not (0.0 <= float(score) <= 1.0):
        return None
    if data["confidence"] not in _VALID_CONFIDENCE:
        return None
    if not isinstance(data["reasoning"], str):
        return None
    return data


def _expected_text(expected: dict[str, Any]) -> str:
    """Flatten the `expected` dict into the prompt's themes/facts slot.

    The dataset's `expected` shape for an inferential dimension carries the
    reference themes or facts; we render whichever key is present, falling
    back to a JSON dump so the judge always sees the full reference.
    """
    for key in ("themes", "facts", "expected_themes_or_facts"):
        if key in expected:
            value = expected[key]
            if isinstance(value, list):
                return "; ".join(str(v) for v in value)
            return str(value)
    return json.dumps(expected) if expected else ""
