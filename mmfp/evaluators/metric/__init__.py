"""Metric evaluators — score the response envelope, not the response text.

Latency and cost are properties of the candidate's invocation, not of the
per-example expected payload. The evaluators in this family read
`latency_ms` and `cost_usd` from `context` and normalise them against a
per-evaluator reference value pinned in `context['evaluator_config']` —
the rubric YAML, plumbed by the engine. See the MLI-267 architectural-
input from MLI-270 for the contract.

Concrete classes live in sibling modules (`latency_p95`, `cost_per_call`)
and self-register via `mmfp.evaluators._registry.register`.
"""
