// @jira: MLI-181
// Slice 3 acceptance test. Currently expected to fail — trend strip +
// candidate-detail drill-in UI does not yet exist. Will go green once Slice 3 implementation sub-tasks land.
//
// MLI-185: count updated from 2 → 4 for tier_3. Resolved on MLI-180 (2026-05-12):
// option (a) — the test matches the slate, not the other way round. The slate
// (products/mli/candidates.yaml) is canonical; this number is a snapshot of it.
import { test, expect } from '@playwright/test';

test('scoreboard shows ranked candidates with trend data', async ({ page }) => {
  await page.goto(process.env.MMFP_URL + '/scoreboard?product=mli');

  const t3Candidates = page.getByTestId('tier-tier_3-candidate');
  await expect(t3Candidates).toHaveCount(4, { timeout: 10000 });

  const scores = await t3Candidates.locator('[data-testid="candidate-score"]')
    .allTextContents();
  expect(parseFloat(scores[0])).toBeGreaterThanOrEqual(parseFloat(scores[1]));

  await expect(page.getByTestId('tier-tier_3-trend-strip')).toBeVisible();

  await t3Candidates.first().click();
  await expect(page.getByTestId('candidate-detail-dimensions')).toBeVisible();
  await expect(page.getByTestId('dimension-row')).toHaveCount(7);
});
