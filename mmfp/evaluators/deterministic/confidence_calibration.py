"""ConfidenceCalibrationEvaluator — inverted Brier alignment per example.

The candidate response is JSON with `label` (string) and `confidence`
(number in [0, 1] — self-reported probability that the label is correct).
The per-example score is `(1 - (confidence - correctness)²) × 100`,
where `correctness ∈ {0, 1}` is whether `label == expected["value"]`.

Aggregation: the engine averages per-example scores across the dataset
when computing the per-dimension mean (see `MatrixRun.scores_for_tier`).
Mean of `1 - brier_component` across N predictions equals
`1 - mean_brier`, i.e. the inverted Brier score on the [0, 1] scale —
mapped onto 0–100 by the per-example × 100 here. No per-dimension Brier
reference is needed; the [0, 100] scale is already the dimension's
score.

Decoding failures (output not JSON, missing keys, confidence out of
range) score 0 — those are exactly the calibration failure modes the
dimension is designed to catch, not configuration errors.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from mmfp.evaluators._registry import register
from mmfp.evaluators.deterministic._helpers import continuous_score
from mmfp.models.matrix_run import EvaluatorScore
from mmfp.plugins.evaluator import EvaluatorPlugin


@register
class ConfidenceCalibrationEvaluator(EvaluatorPlugin):
    name = "confidence_calibration"

    def evaluate(
        self,
        candidate_output: str,
        expected: dict[str, Any],
        context: dict[str, Any],
    ) -> EvaluatorScore:
        if "value" not in expected:
            raise ValueError(
                "ConfidenceCalibration requires expected['value'] (the correct label)"
            )
        target_label = expected["value"]
        if not isinstance(target_label, str):
            raise TypeError(
                "ConfidenceCalibration expects expected['value'] to be a string"
            )
        label_key = expected.get("label_key", "label")
        confidence_key = expected.get("confidence_key", "confidence")

        try:
            decoded = json.loads(candidate_output)
        except json.JSONDecodeError as e:
            return continuous_score(
                context=context,
                evaluator_name=self.name,
                source_field=self.scores_field,
                raw_value={"decode_error": str(e), "output": candidate_output},
                normalized_score=Decimal("0"),
                reason=f"output is not valid JSON: {e.msg}",
            )

        if not isinstance(decoded, dict):
            return continuous_score(
                context=context,
                evaluator_name=self.name,
                source_field=self.scores_field,
                raw_value={"output": decoded, "type": type(decoded).__name__},
                normalized_score=Decimal("0"),
                reason="output must be a JSON object with label + confidence",
            )

        if label_key not in decoded:
            return continuous_score(
                context=context,
                evaluator_name=self.name,
                source_field=self.scores_field,
                raw_value={"output": decoded, "missing": label_key},
                normalized_score=Decimal("0"),
                reason=f"output missing '{label_key}'",
            )
        if confidence_key not in decoded:
            return continuous_score(
                context=context,
                evaluator_name=self.name,
                source_field=self.scores_field,
                raw_value={"output": decoded, "missing": confidence_key},
                normalized_score=Decimal("0"),
                reason=f"output missing '{confidence_key}'",
            )

        label = decoded[label_key]
        confidence_raw = decoded[confidence_key]
        # bool is an int in Python — exclude it explicitly so True doesn't sneak
        # through as confidence=1.
        if isinstance(confidence_raw, bool) or not isinstance(
            confidence_raw, (int, float)
        ):
            return continuous_score(
                context=context,
                evaluator_name=self.name,
                source_field=self.scores_field,
                raw_value={"output": decoded, "confidence": confidence_raw},
                normalized_score=Decimal("0"),
                reason=f"'{confidence_key}' must be a number in [0, 1]",
            )
        confidence = Decimal(str(confidence_raw))
        if confidence < Decimal("0") or confidence > Decimal("1"):
            return continuous_score(
                context=context,
                evaluator_name=self.name,
                source_field=self.scores_field,
                raw_value={"output": decoded, "confidence": float(confidence)},
                normalized_score=Decimal("0"),
                reason=(
                    f"'{confidence_key}' must be in [0, 1]; got {confidence}"
                ),
            )

        correctness = Decimal("1") if label == target_label else Decimal("0")
        brier_component = (confidence - correctness) ** 2
        score = (Decimal("1") - brier_component) * Decimal("100")
        return continuous_score(
            context=context,
            evaluator_name=self.name,
            source_field=self.scores_field,
            raw_value={
                "label": label,
                "expected_label": target_label,
                "correctness": int(correctness),
                "confidence": float(confidence),
                "brier_component": float(brier_component),
            },
            normalized_score=score,
            reason=(
                f"label {'correct' if correctness else 'incorrect'}; "
                f"confidence {confidence}; brier {brier_component}"
            ),
        )
