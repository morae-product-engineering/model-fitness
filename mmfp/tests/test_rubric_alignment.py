# @jira: MLI-268 (test) / MLI-267 (parent slice: Slice 3.5 — Align v0.1
#         Rubric with its reference and close Slice 3 visual gaps) /
#         MLI-360 (reconciled the test's plumbing to the shipped rubric/
#         engine API after MLI-269 shipped a different surface than this
#         test sketched; discrimination assertion preserved verbatim).
"""Slice 3.5 acceptance test — rubric alignment and per-tier discrimination.

Asserts that at least one **active** dimension per tier produces distinct
normalised scores across candidates — i.e. the rubric, as actually weighted,
discriminates between models rather than scoring them uniformly.

Construction mirrors the Slice 2 acceptance test ``test_matrix_run.py``: real
``products/mli/`` configuration loaded via the conftest fixtures and driven
through the real ``MatrixEngine().run(...)`` signature. Like that test it is
gated green in CI by ``baseline-matrix.yml`` (which authenticates to Foundry);
the ``slice_acceptance`` marker keeps it out of the standard unit-test job.

Why is this red?
  - Missing Foundry creds locally → the binding errors per cell, the run still
    completes, and the assertion reflects whatever scored.
  - An ``AssertionError`` is a real finding: a tier whose active dimensions all
    score uniformly. Per the 2026-06-02 baseline run every tier has at least
    one discriminating active dimension, so the assertion is expected to PASS.
    Do not soften, skip, or ``TODO`` the assertion, and do not edit the rubric
    to induce discrimination — surface a red as a finding (MLI-360 / MLI-190
    (a)-discipline).
"""

import pytest

pytestmark = pytest.mark.slice_acceptance


def test_matrix_run_discriminates_per_tier(
    real_rubric, real_dataset, real_candidates, real_dimension_evaluators
):
    """At least one active dimension per tier produces distinct scores across candidates."""
    from mmfp.engine.matrix import MatrixEngine

    run = MatrixEngine().run(
        rubric=real_rubric,
        datasets=real_dataset,
        candidates=real_candidates,
        dimension_evaluators=real_dimension_evaluators,
    )
    for tier in real_rubric.tiers:
        cards = run.scores_for_tier(tier.id, tier)
        per_dim = {
            d.id: {
                card.per_dimension[d.id]
                for card in cards
                if d.id in card.per_dimension
            }
            for d in tier.active_dimensions()
        }
        assert any(len(s) > 1 for s in per_dim.values()), \
            f'{tier.id}: no active dimension discriminates between candidates'
