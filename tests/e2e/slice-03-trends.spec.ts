// @jira: MLI-181
// Slice 3 acceptance test. Goes green with MLI-187 (drill-down) — the trend
// strip (MLI-186) and ranked candidates (MLI-185) already land it on
// everything but the dimension drill-in.
//
// MLI-185: tier_3 candidate count 2 → 4. Resolved on MLI-180 (2026-05-12):
// option (a) — the test matches the slate, not the other way round. The slate
// (products/mli/candidates.yaml) is canonical; this number is a snapshot of it.
//
// MLI-187: tier_3 dimension count 7 → 2, same pattern — the rubric
// (products/mli/rubric.yaml) is canonical and declares 2 deterministic
// dimensions for tier_3 in v0.1 (citation_presence, structural_completeness).
// The LLM-judge dimensions land with Slice 6 (MLI-219+); revise upward when
// the rubric grows.
import { test, expect } from '@playwright/test';

test('scoreboard shows ranked candidates with trend data', { tag: '@slice-acceptance' }, async ({ page }) => {
  await page.goto(process.env.MMFP_URL + '/scoreboard?product=mli');

  const t3Candidates = page.getByTestId('tier-tier_3-candidate');
  await expect(t3Candidates).toHaveCount(4, { timeout: 10000 });

  const scores = await t3Candidates.locator('[data-testid="candidate-score"]')
    .allTextContents();
  expect(parseFloat(scores[0])).toBeGreaterThanOrEqual(parseFloat(scores[1]));

  await expect(page.getByTestId('tier-tier_3-trend-strip')).toBeVisible();

  await t3Candidates.first().click();
  await expect(page.getByTestId('candidate-detail-dimensions')).toBeVisible();
  // MLI-272: tier_3 rubric grew 2 → 7 (2 active + 5 draft dimensions).
  await expect(page.getByTestId('dimension-row')).toHaveCount(7);
});
