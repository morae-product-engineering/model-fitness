"""StructuredOutputReliabilityEvaluator — tool-call argument parse rate.

Sibling to `parse_rate`, but scored over an array of tool-call objects
rather than a flat trajectory. Each call carries `name` and `arguments`
(JSON-encoded per the OpenAI tool-call convention); reliability counts
the fraction of calls whose `arguments` (a) parse as JSON and (b)
validate against the named tool's schema.

Failure granularity matters here: an evaluator that just emits "70%
passed" without telling the reviewer *why* the 30% failed makes the
dimension hard to act on. `raw_value` records, per call, whether it
failed on missing-name, unknown-tool, args-not-JSON, or schema-mismatch.

Continuous score (passed=None); engine averages across examples to yield
the dimension-level reliability.
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
class StructuredOutputReliabilityEvaluator(EvaluatorPlugin):
    name = "structured_output_reliability"

    def evaluate(
        self,
        candidate_output: str,
        expected: dict[str, Any],
        context: dict[str, Any],
    ) -> EvaluatorScore:
        if "schemas" not in expected:
            raise ValueError(
                "StructuredOutputReliability requires expected['schemas'] "
                "(dict of tool_name -> JSON Schema for its arguments)"
            )
        schemas = expected["schemas"]
        if not isinstance(schemas, dict) or not schemas:
            raise ValueError(
                "expected['schemas'] must be a non-empty dict of tool_name -> schema"
            )
        validators: dict[str, jsonschema.Draft202012Validator] = {}
        for tool_name, schema in schemas.items():
            try:
                jsonschema.Draft202012Validator.check_schema(schema)
            except SchemaError as e:
                raise ValueError(
                    f"schemas['{tool_name}'] is not a valid JSON Schema: {e.message}"
                ) from e
            validators[tool_name] = jsonschema.Draft202012Validator(schema)

        try:
            calls = json.loads(candidate_output)
        except json.JSONDecodeError as e:
            return continuous_score(
                context=context,
                evaluator_name=self.name,
                source_field=self.scores_field,
                raw_value={"decode_error": str(e), "output": candidate_output},
                normalized_score=Decimal("0"),
                reason=f"tool-call array is not valid JSON: {e.msg}",
            )

        if not isinstance(calls, list):
            return continuous_score(
                context=context,
                evaluator_name=self.name,
                source_field=self.scores_field,
                raw_value={"output": calls, "type": type(calls).__name__},
                normalized_score=Decimal("0"),
                reason="tool-call payload must be a JSON array",
            )
        if len(calls) == 0:
            raise ValueError(
                "StructuredOutputReliability requires a non-empty call array; "
                "dataset bug if this fires"
            )

        results: list[dict[str, Any]] = []
        passed_count = 0
        for i, call in enumerate(calls):
            outcome = _score_call(call, validators)
            outcome["index"] = i
            results.append(outcome)
            if outcome["passed"]:
                passed_count += 1

        total = len(calls)
        rate = Decimal(passed_count) * Decimal("100") / Decimal(total)
        return continuous_score(
            context=context,
            evaluator_name=self.name,
            source_field=self.scores_field,
            raw_value={
                "calls": results,
                "passed_count": passed_count,
                "total": total,
            },
            normalized_score=rate,
            reason=f"{passed_count}/{total} tool calls reliable",
        )


def _score_call(
    call: Any, validators: dict[str, jsonschema.Draft202012Validator]
) -> dict[str, Any]:
    """Classify one tool-call object; returns a result dict with `passed` flag.

    Failure shapes are kept distinct so the rubric reviewer sees *why* the
    call failed (unknown tool vs malformed args vs schema-mismatch) — those
    point at different fixes upstream.
    """
    if not isinstance(call, dict):
        return {"passed": False, "failure": "call_not_an_object"}
    name = call.get("name")
    if not isinstance(name, str) or not name:
        return {"passed": False, "failure": "missing_or_empty_name"}
    if name not in validators:
        return {
            "passed": False,
            "failure": "unknown_tool",
            "name": name,
            "known_tools": sorted(validators),
        }
    if "arguments" not in call:
        return {"passed": False, "failure": "missing_arguments", "name": name}

    raw_args = call["arguments"]
    if isinstance(raw_args, str):
        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError as e:
            return {
                "passed": False,
                "failure": "arguments_not_json",
                "name": name,
                "decode_error": str(e),
            }
    else:
        # Some providers emit `arguments` already-decoded; accept both shapes.
        args = raw_args

    errors = sorted(
        validators[name].iter_errors(args),
        key=lambda err: tuple(str(p) for p in err.absolute_path),
    )
    if errors:
        return {
            "passed": False,
            "failure": "schema_mismatch",
            "name": name,
            "errors": [format_jsonschema_error(e) for e in errors],
        }
    return {"passed": True, "name": name}
