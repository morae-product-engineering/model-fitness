# @jira: MLI-168 (test) / MLI-169 (relocated from platform/tests/, retargeted
#         to mmfp.engine.matrix) / MLI-258 (engine signature took
#         `dimension_evaluators=` and the strict `repository=`/`product=`
#         pair) / MLI-173 (fixtures now load real YAML/JSONL into Pydantic
#         models; this test threads the new kwargs) / MLI-178 (moved hard
#         gate from ci.yml to baseline-matrix.yml so the test runs against
#         real Foundry without paying per-PR cost).
#
# Slice 2 acceptance test. Gated green in CI by `.github/workflows/
# baseline-matrix.yml` — that workflow already authenticates to Foundry
# (it runs the same matrix as the seed CLI), so adding a pytest step there
# reuses the credentials. ci.yml's `slice-acceptance-tests` job still
# excludes Foundry creds and keeps the soft-fail pattern for Slice 3+
# acceptance tests; this test runs but errors-out there harmlessly.
#
# Locally goes green when `FOUNDRY_ACCOUNT_KEY` and the matching endpoint
# env vars are present. The `slice_acceptance` marker keeps it out of the
# standard unit-test job (`-m "not slice_acceptance"`).
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
