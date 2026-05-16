"""ContextWindowAdequacyEvaluator — does the candidate's window fit the dimension's typical query.

Pass/fail by design: a candidate either has enough context window for the
dimension's representative input (tool schemas + system prompt + typical
user query + reserved output budget) or it doesn't. Marginal headroom is
not a softer pass — if the candidate's window is below the dimension's
required budget, no graceful degradation is available at runtime.

Context contract:
    context['candidate_context_window']        int > 0  (tokens)
        Source for this is candidate metadata. The Candidate model
        doesn't carry it today (MLI-166 captured `max_tokens` only —
        per-call output budget, not the total window). The engine
        wiring lands when MLI-272 adds the field; until then 3.5.5
        will surface this gap. Reading from context (not from
        evaluator_config) keeps the dimension config candidate-agnostic.

    context['evaluator_config']['required_tokens']  int > 0
        The dimension's representative input + reserved output budget,
        expressed as a single number. Stewards keep the breakdown
        (schema vs query vs reserved output) in YAML comments — the
        evaluator only needs the sum.

`candidate_output` and `expected` are ignored — this evaluator scores
the candidate envelope against the dimension's requirement, not any
per-example payload.
"""

from __future__ import annotations

from typing import Any

from mmfp.evaluators._registry import register
from mmfp.evaluators.deterministic._helpers import make_score
from mmfp.evaluators.metric._helpers import require_config, require_positive_int
from mmfp.models.matrix_run import EvaluatorScore
from mmfp.plugins.evaluator import EvaluatorPlugin


@register
class ContextWindowAdequacyEvaluator(EvaluatorPlugin):
    name = "context_window_adequacy"

    def evaluate(
        self,
        candidate_output: str,
        expected: dict[str, Any],
        context: dict[str, Any],
    ) -> EvaluatorScore:
        if "candidate_context_window" not in context:
            raise ValueError(
                "context_window_adequacy requires "
                "context['candidate_context_window'] (populated by the engine "
                "from candidate metadata)"
            )
        window = require_positive_int(
            context["candidate_context_window"], name="candidate_context_window"
        )

        cfg = require_config(context)
        if "required_tokens" not in cfg:
            raise ValueError(
                "evaluator 'context_window_adequacy' requires "
                "evaluator_config['required_tokens'] (dimension's representative "
                "schema + query + reserved-output budget, in tokens)"
            )
        required = require_positive_int(cfg["required_tokens"], name="required_tokens")

        passed = window >= required
        if passed:
            reason = (
                f"window {window} tokens ≥ required {required} "
                f"({window - required} headroom)"
            )
        else:
            reason = (
                f"window {window} tokens < required {required} "
                f"(short by {required - window})"
            )
        return make_score(
            context=context,
            evaluator_name=self.name,
            source_field=self.scores_field,
            raw_value={
                "candidate_context_window": window,
                "required_tokens": required,
                "headroom_tokens": window - required,
            },
            passed=passed,
            reason=reason,
        )
