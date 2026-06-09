"""Inferential evaluators — score via an LLM judge rather than a rule.

Unlike the deterministic family, these call a model under the hood, so their
output is non-deterministic in value (the rubric design tolerates this for
inferential dimensions — see MFP-74 / MLI-211). The judge model is itself a
candidate and is invoked through the same `BindingPlugin` contract as any
other model; the evaluator never talks to a provider directly.
"""
