"""JSON Schema validator evaluator.

`expected["schema"]` is a JSON Schema (Draft 2020-12) the candidate output
must validate against after JSON-decoding. Two failure modes:
  - candidate output isn't valid JSON
  - candidate output is valid JSON but doesn't match the schema
Both yield score 0; `raw_value` carries the decode error or the validation
errors so a human can see why.
"""

from __future__ import annotations

import json
from typing import Any

import jsonschema
from jsonschema.exceptions import SchemaError, ValidationError

from mmfp.evaluators._registry import register
from mmfp.evaluators.deterministic._helpers import make_score
from mmfp.models.matrix_run import EvaluatorScore
from mmfp.plugins.evaluator import EvaluatorPlugin


@register
class JsonSchemaEvaluator(EvaluatorPlugin):
    name = "json_schema"

    def evaluate(
        self,
        candidate_output: str,
        expected: dict[str, Any],
        context: dict[str, Any],
    ) -> EvaluatorScore:
        if "schema" not in expected:
            raise ValueError("JsonSchema requires expected['schema']")
        schema = expected["schema"]
        try:
            jsonschema.Draft202012Validator.check_schema(schema)
        except SchemaError as e:
            raise ValueError(
                f"expected['schema'] is not a valid JSON Schema: {e.message}"
            ) from e

        try:
            decoded = json.loads(candidate_output)
        except json.JSONDecodeError as e:
            return make_score(
                context=context,
                evaluator_name=self.name,
                source_field=self.scores_field,
                raw_value={"decode_error": str(e), "output": candidate_output},
                passed=False,
                reason=f"output is not valid JSON: {e.msg}",
            )

        validator = jsonschema.Draft202012Validator(schema)
        errors = sorted(
            validator.iter_errors(decoded),
            key=lambda err: tuple(str(p) for p in err.absolute_path),
        )
        if not errors:
            return make_score(
                context=context,
                evaluator_name=self.name,
                source_field=self.scores_field,
                raw_value=decoded,
                passed=True,
                reason="schema valid",
            )
        first = errors[0]
        return make_score(
            context=context,
            evaluator_name=self.name,
            source_field=self.scores_field,
            raw_value={
                "errors": [_format_error(e) for e in errors],
                "output": decoded,
            },
            passed=False,
            reason=f"schema invalid ({len(errors)} error(s)); first: {first.message}",
        )


def _format_error(err: ValidationError) -> dict[str, Any]:
    return {
        "path": "/".join(str(p) for p in err.absolute_path),
        "message": err.message,
        "validator": err.validator,
    }
