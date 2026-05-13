// @jira: MLI-263
// Slice 3 portfolio summary (audit Option C). Each TierCard renders the
// Primary / Fallback / Under evaluation / Rejected four-cell summary above
// the candidate table.
//
// The spec asserts presence of all four cells per tier card. It deliberately
// does not assert which candidates land in each slot — the seed slate
// currently marks all candidates `under_evaluation`, so Primary and Fallback
// render as "— none —"; flagged as a finding in the closing comment.

import { test, expect } from '@playwright/test';

const TIERS = ['tier_1', 'tier_2', 'tier_3'] as const;

test('each tier card renders the four-cell portfolio summary', async ({ page }) => {
  await page.goto(process.env.MMFP_URL + '/scoreboard?product=mli');

  for (const tier of TIERS) {
    const summary = page.getByTestId(`portfolio-summary-${tier}`);
    await expect(summary).toBeVisible();

    for (const kind of ['primary', 'fallback', 'under-evaluation', 'rejected']) {
      await expect(page.getByTestId(`portfolio-cell-${kind}-${tier}`)).toBeVisible();
    }
  }
});
