// @jira: MLI-168
// Slice 2 acceptance test. Currently expected to fail — tier-card UI does not
// yet exist. Will go green once subtasks 2.4–2.10 land.
import { test, expect } from '@playwright/test';

test('scoreboard shows real scored candidates per tier', { tag: '@slice-acceptance' }, async ({ page }) => {
  await page.goto(process.env.MMFP_URL + '/scoreboard?product=mli');

  await expect(page.getByTestId('tier-card-tier_1')).toBeVisible();
  await expect(page.getByTestId('tier-card-tier_2')).toBeVisible();
  await expect(page.getByTestId('tier-card-tier_3')).toBeVisible();

  for (const tier of ['tier_1', 'tier_2', 'tier_3']) {
    const candidates = page.getByTestId(`tier-${tier}-candidate`);
    await expect(candidates.first()).toBeVisible();
    const score = await candidates.first().getByTestId('candidate-score').textContent();
    expect(parseFloat(score!)).toBeGreaterThan(0);
  }

  await expect(page.getByTestId('rubric-version')).toContainText(/v\d+\.\d+/);
});
