# @jira: MLI-268 (test) / MLI-267 (parent slice: Slice 3.5 — Align v0.1
#         Rubric with its reference and close Slice 3 visual gaps)
"""Slice 3.5 acceptance test — rubric alignment and per-tier discrimination.

This test is **deliberately red** against current main and will remain so
until MLI-269 lands (rubric model + matrix engine changes + rubric YAML
alignment).

Expected failure mode on main:
  AttributeError — either `Rubric.load` (class method does not yet exist
  on the Rubric model) or `Tier.active_dimensions` (instance method ships
  in the 3.5.2 sub-task, not yet present). The exact symbol Python resolves
  first depends on runtime state; either AttributeError is acceptable. The
  test must NOT fail with an ordinary assertion error on degenerate data —
  if you see an AssertionError, transcription has gone wrong.

Goes green when:
  - MLI-269 (rubric model adds Rubric.load + Tier.active_dimensions, matrix
    engine exposes the new run() signature, rubric YAML realigned to the
    v0.1 reference document) lands and is merged to main.

Do not soften the assertion, add a skip, or add a TODO to make it pass.
The whole point of this sub-task (MLI-268) is to record the acceptance
criterion in executable form before the implementation exists.
"""

import pytest

from mmfp.engine.matrix import MatrixEngine
from mmfp.models.rubric import Rubric

pytestmark = pytest.mark.slice_acceptance


def test_matrix_run_discriminates_per_tier():
    """At least one active dimension per tier produces distinct scores across candidates."""
    run = MatrixEngine(Rubric.load('products/mli/rubric.yaml')).run()
    for tier in run.rubric.tiers:
        per_dim = {
            d.id: {run.score(c, tier, d).normalized_score for c in run.candidates_in(tier)}
            for d in tier.active_dimensions()
        }
        assert any(len(s) > 1 for s in per_dim.values()), \
            f'{tier.id}: no active dimension discriminates between candidates'
