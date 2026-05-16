"""Registry-level checks for the metric evaluator family.

These mirror the assertions the deterministic family relies on implicitly
(the family loads on package import; names resolve via `get`) but state
them explicitly because metric is the second family to register and the
AC requires loadability from YAML by name.
"""

from __future__ import annotations

from mmfp.evaluators import get, names
from mmfp.evaluators.metric.cost_per_call import CostPerCallEvaluator
from mmfp.evaluators.metric.latency_p95 import LatencyP95Evaluator


def test_latency_p95_registered():
    assert "latency_p95" in names()
    assert get("latency_p95") is LatencyP95Evaluator


def test_cost_per_call_registered():
    assert "cost_per_call" in names()
    assert get("cost_per_call") is CostPerCallEvaluator
