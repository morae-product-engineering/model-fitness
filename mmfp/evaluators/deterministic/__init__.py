"""Deterministic evaluators — same input always yields the same score.

Concrete classes live in sibling modules and self-register via
`mmfp.evaluators._registry.register`:

    exact_match, json_schema, regex_match           (MLI-170)
    parse_rate, structured_output_reliability,
    context_window_adequacy, confidence_calibration,
    query_correctness                               (MLI-271)
"""
