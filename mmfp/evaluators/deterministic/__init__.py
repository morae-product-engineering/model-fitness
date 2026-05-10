"""Deterministic evaluators — same input always yields the same score.

Concrete classes live in sibling modules (`exact_match`, `json_schema`,
`regex_match`) and self-register via `mmfp.evaluators._registry.register`.
"""
