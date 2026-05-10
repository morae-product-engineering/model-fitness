# @jira: MLI-168 (test) / MLI-169 (relocated from platform/tests/, retargeted to mmfp.engine.matrix)
# Slice 2 acceptance test. Currently expected to fail at collection with
# ModuleNotFoundError — mmfp.engine.matrix does not yet exist. Will go green
# once subtasks 2.5–2.7 land the plugin interfaces and engine (MLI-172).
from mmfp.engine.matrix import MatrixEngine


def test_matrix_run_produces_scored_candidates(real_rubric, real_dataset, real_candidates):
    run = MatrixEngine().run(rubric=real_rubric, datasets=real_dataset,
                             candidates=real_candidates)
    assert run.rubric_version == real_rubric.version
    for tier_id in ['tier_1', 'tier_2', 'tier_3']:
        tier_scores = run.scores_for_tier(tier_id)
        assert len(tier_scores) >= 1
        for s in tier_scores:
            assert 0 <= s.weighted_score <= 100
