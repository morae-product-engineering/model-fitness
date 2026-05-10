# @jira: MLI-168 (test) / MLI-169 (relocated from platform/tests/, retargeted
#         to mmfp.engine.matrix) / MLI-258 (engine signature took
#         `dimension_evaluators=` and the strict `repository=`/`product=`
#         pair) / MLI-173 (fixtures now load real YAML/JSONL into Pydantic
#         models; this test threads the new kwargs).
#
# Slice 2 acceptance test. Stays deliberately red in CI until MLI-177 wires
# real Foundry credentials into the unit-test runner — the default
# `azure_foundry` binding makes a live HTTP call the moment a candidate is
# scored. Locally it goes green when `FOUNDRY_ACCOUNT_KEY` and the matching
# endpoint env vars are present. The `slice_acceptance` marker keeps it out
# of the standard unit-test job (`-m "not slice_acceptance"`).
#
# Expected failure modes worth recognising for "why is this red?":
#   - missing API key → binding raises auth/network error → run completes
#     with errored cells, assertion below still passes if at least one
#     cell scored. The current matrix uses 14 candidate × tier pairings
#     across 25 examples, so any successful binding call surfaces here.
#   - missing config files → conftest fixtures FileNotFoundError before
#     the test body runs. Fixed by MLI-173.
import pytest

pytestmark = pytest.mark.slice_acceptance


def test_matrix_run_produces_scored_candidates(
    real_rubric, real_dataset, real_candidates, real_dimension_evaluators
):
    from mmfp.engine.matrix import MatrixEngine

    run = MatrixEngine().run(
        rubric=real_rubric,
        datasets=real_dataset,
        candidates=real_candidates,
        dimension_evaluators=real_dimension_evaluators,
    )
    assert run.rubric_version == real_rubric.version
    for tier_id in ["tier_1", "tier_2", "tier_3"]:
        tier_scores = run.scores_for_tier(tier_id)
        assert len(tier_scores) >= 1
        for s in tier_scores:
            assert 0 <= s.weighted_score <= 100
