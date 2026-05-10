# @jira: MLI-168 (test) / MLI-169 (relocated from platform/tests/, retargeted to mmfp.engine.matrix)
# Slice 2 acceptance test. Currently expected to fail with ModuleNotFoundError
# — mmfp.engine.matrix does not yet exist. Will go green once subtasks 2.5–2.7
# land the plugin interfaces and engine (MLI-172). The import is deferred into
# the test body so the file collects cleanly under the `slice_acceptance`
# marker; without that, `-m "not slice_acceptance"` cannot deselect the test
# (collection runs before marker filtering).
import pytest

pytestmark = pytest.mark.slice_acceptance


def test_matrix_run_produces_scored_candidates(real_rubric, real_dataset, real_candidates):
    from mmfp.engine.matrix import MatrixEngine
    run = MatrixEngine().run(rubric=real_rubric, datasets=real_dataset,
                             candidates=real_candidates)
    assert run.rubric_version == real_rubric.version
    for tier_id in ['tier_1', 'tier_2', 'tier_3']:
        tier_scores = run.scores_for_tier(tier_id)
        assert len(tier_scores) >= 1
        for s in tier_scores:
            assert 0 <= s.weighted_score <= 100
