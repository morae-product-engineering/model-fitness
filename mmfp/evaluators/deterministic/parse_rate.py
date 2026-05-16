"""ParseRateEvaluator — schema-validation pass rate across a trajectory.

Close cousin of `json_schema`, but applied to a multi-turn trajectory
rather than a single output. The candidate emits a JSON-encoded array of
per-turn outputs (already-decoded structures, not nested JSON strings);
each turn validates against `expected["schema"]`; the score is the
fraction of turns that validate, on the 0–100 scale.

Continuous score (passed=None); aggregated across examples by the engine's
per-dimension mean, which yields the dimension-level pass rate. A turn-
level failure breakdown is stamped into `raw_value` so a reviewer can see
which turn(s) failed and why without re-running the evaluator.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import jsonschema
from jsonschema.exceptions import SchemaError

from mmfp.evaluators._registry import register
from mmfp.evaluators.deterministic._helpers import (
    continuous_score,
    format_jsonschema_error,
)
from mmfp.models.matrix_run import EvaluatorScore
from mmfp.plugins.evaluator import EvaluatorPlugin


@register
class ParseRateEvaluator(EvaluatorPlugin):
    name = "parse_rate"

    def evaluate(
        self,
        candidate_output: str,
        expected: dict[str, Any],
        context: dict[str, Any],
    ) -> EvaluatorScore:
        if "schema" not in expected:
            raise ValueError("ParseRate requires expected['schema']")
        schema = expected["schema"]
        try:
            jsonschema.Draft202012Validator.check_schema(schema)
        except SchemaError as e:
            raise ValueError(
                f"expected['schema'] is not a valid JSON Schema: {e.message}"
            ) from e

        try:
            trajectory = json.loads(candidate_output)
        except json.JSONDecodeError as e:
            return continuous_score(
                context=context,
                evaluator_name=self.name,
                source_field=self.scores_field,
                raw_value={"decode_error": str(e), "output": candidate_output},
                normalized_score=Decimal("0"),
                reason=f"trajectory is not valid JSON: {e.msg}",
            )

        if not isinstance(trajectory, list):
            return continuous_score(
                context=context,
                evaluator_name=self.name,
                source_field=self.scores_field,
                raw_value={"output": trajectory, "type": type(trajectory).__name__},
                normalized_score=Decimal("0"),
                reason="trajectory must be a JSON array of per-turn outputs",
            )
        if len(trajectory) == 0:
            raise ValueError(
                "ParseRate requires a non-empty trajectory; dataset bug if this fires"
            )

        validator = jsonschema.Draft202012Validator(schema)
        turns: list[dict[str, Any]] = []
        passed_count = 0
        for i, turn in enumerate(trajectory):
            errors = sorted(
                validator.iter_errors(turn),
                key=lambda err: tuple(str(p) for p in err.absolute_path),
            )
            if not errors:
                passed_count += 1
                turns.append({"turn": i, "passed": True})
            else:
                turns.append(
                    {
                        "turn": i,
                        "passed": False,
                        "errors": [format_jsonschema_error(e) for e in errors],
                    }
                )

        total = len(trajectory)
        rate = Decimal(passed_count) * Decimal("100") / Decimal(total)
        return continuous_score(
            context=context,
            evaluator_name=self.name,
            source_field=self.scores_field,
            raw_value={
                "turns": turns,
                "passed_count": passed_count,
                "total": total,
            },
            normalized_score=rate,
            reason=f"{passed_count}/{total} turns valid",
        )
