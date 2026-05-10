"""Regex pattern-match evaluator.

`expected["pattern"]` (str) is compiled and applied to `candidate_output`.
`expected.get("mode", "search")` selects `re.search` (default) or
`re.fullmatch`. `expected.get("flags", [])` is a list of flag names ("I",
"S", "M") combined into a single re flags int. Match groups are stamped
into raw_value so a downstream extraction evaluator can reuse them later.
"""

from __future__ import annotations

import re
from typing import Any

from mmfp.evaluators._registry import register
from mmfp.evaluators.deterministic._helpers import make_score
from mmfp.models.matrix_run import EvaluatorScore
from mmfp.plugins.evaluator import EvaluatorPlugin

_FLAG_NAMES = {
    "I": re.IGNORECASE,
    "IGNORECASE": re.IGNORECASE,
    "M": re.MULTILINE,
    "MULTILINE": re.MULTILINE,
    "S": re.DOTALL,
    "DOTALL": re.DOTALL,
    "X": re.VERBOSE,
    "VERBOSE": re.VERBOSE,
}


@register
class RegexMatchEvaluator(EvaluatorPlugin):
    name = "regex_match"

    def evaluate(
        self,
        candidate_output: str,
        expected: dict[str, Any],
        context: dict[str, Any],
    ) -> EvaluatorScore:
        if "pattern" not in expected:
            raise ValueError("RegexMatch requires expected['pattern']")
        pattern = expected["pattern"]
        if not isinstance(pattern, str):
            raise TypeError("RegexMatch expects expected['pattern'] to be a string")

        mode = expected.get("mode", "search")
        if mode not in ("search", "fullmatch"):
            raise ValueError(
                f"RegexMatch mode must be 'search' or 'fullmatch'; got '{mode}'"
            )

        flags = _build_flags(expected.get("flags", []))
        try:
            compiled = re.compile(pattern, flags)
        except re.error as e:
            raise ValueError(f"RegexMatch could not compile pattern: {e}") from e

        if mode == "fullmatch":
            match = compiled.fullmatch(candidate_output)
        else:
            match = compiled.search(candidate_output)
        passed = match is not None
        if passed:
            assert match is not None  # for type narrowing
            raw = {
                "pattern": pattern,
                "mode": mode,
                "match": match.group(0),
                "groups": list(match.groups()),
                "groupdict": match.groupdict(),
            }
            reason = f"pattern matched ({mode})"
        else:
            raw = {"pattern": pattern, "mode": mode, "output": candidate_output}
            reason = f"pattern did not match ({mode})"

        return make_score(
            context=context,
            evaluator_name=self.name,
            source_field=self.scores_field,
            raw_value=raw,
            passed=passed,
            reason=reason,
        )


def _build_flags(names: list[str]) -> int:
    flags = 0
    for n in names:
        if not isinstance(n, str):
            raise TypeError(f"regex flag must be a string; got {type(n).__name__}")
        key = n.upper()
        if key not in _FLAG_NAMES:
            raise ValueError(
                f"unknown regex flag '{n}'; expected one of: "
                f"{sorted(set(k for k in _FLAG_NAMES if len(k) == 1))} "
                f"(or full names: I, M, S, X)"
            )
        flags |= _FLAG_NAMES[key]
    return flags
