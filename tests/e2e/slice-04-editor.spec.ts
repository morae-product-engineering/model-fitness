// @jira: MLI-191
// Slice 4 acceptance test (Editor). Transcribed from the MLI-190 description,
// reconciled to repo + rubric reality per the MLI-190 architectural-reality
// comment (2026-05-16) and the MLI-360 pre-impl comment (2026-06-02). The
// reconciliation and the deliberate decision to ship this e2e as Slice 4's
// sole red acceptance test are recorded in the MLI-191 closing comment.
//
// Goes GREEN when the Slice 4 implementation sub-tasks land:
//   - MLI-195 (4.5): the Editor page at /editor?product=mli — the
//     rubric-version readout, per-dimension weight inputs, save note,
//     save button, and the "Rubric saved" toast.
//   - MLI-193 (4.3) + MLI-192 (4.2): the impact-preview endpoint and the
//     re-score-existing-runs engine behind impact-preview-<tier> and
//     ranking-change-row.
//   - The save path itself (PUT /api/products/{product}/rubric) already
//     shipped in Slice 3.5 (MLI-273); the Editor consumes it as its save call.
//
// Status: GREEN. Slice 4 landed (MLI-195 Editor UI, MLI-192/MLI-193 re-score +
// impact-preview); MLI-197 verified this spec against deployed dev. Do NOT
// loosen the selectors, add a skip, or soften the rank-change assertion.
//
// Dimension choice (re-pinned in MLI-197 — supersedes the tier_3 choice the
// MLI-190 architectural-reality comment of 2026-05-16 recommended). That comment
// expected Tier 1 to have "real spread"; the LIVE dev matrix data falsifies it.
// Querying the deployed preview-impact endpoint showed Tier 1 AND Tier 3 are
// strict dominance chains — one candidate beats the next on EVERY active dim — so
// for any non-negative weights the ranking is invariant and no re-weight can ever
// flip a rank (the tier_3 edit this spec originally shipped could not go green).
// Tier 2 is the only tier with a crossing candidate: `kimi-k2-6` has worse
// `latency_p95` (78.7) but better `query_correctness` (90) than the other four
// (100 / 10). Re-weighting query_correctness 30→5 and latency_p95 10→35 (active
// sum stays 80, valid per mmfp/models/rubric.py Tier validator; drafts untouched)
// drops kimi from rank 1→5 and lifts the other four — verified live on the
// preview-impact endpoint before this was committed. See the MLI-197 closing
// comment for the full dominance-chain analysis.
import { test, expect } from '@playwright/test';

test('editor: change weight, preview impact, save commits to git', { tag: '@slice-acceptance' }, async ({ page }) => {
  await page.goto(process.env.MMFP_URL + '/editor?product=mli');

  const versionBefore = await page.getByTestId('rubric-version').textContent();

  await page.getByTestId('weight-input-tier_2.query_correctness').fill('5');
  await page.getByTestId('weight-input-tier_2.latency_p95').fill('35');

  await expect(page.getByTestId('impact-preview-tier_2')).toBeVisible();
  await expect(page.getByTestId('ranking-change-row').first()).toBeVisible();

  await page.getByTestId('save-note').fill('Testing impact preview');
  await page.getByTestId('save-button').click();

  await expect(page.getByTestId('toast')).toContainText('Rubric saved');
  const versionAfter = await page.getByTestId('rubric-version').textContent();
  expect(versionAfter).not.toBe(versionBefore);
});
