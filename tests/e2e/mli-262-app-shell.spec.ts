// @jira: MLI-262, MLI-196
// Slice 3 app-shell chrome (audit Option B). Asserts the shell components
// are present on the scoreboard route and the Scoreboard tab is marked
// active.
// Editor was made navigable by MLI-195; Curator by MLI-196.
// The disabled set is now just History.

import { test, expect } from '@playwright/test';

test('scoreboard renders the app-shell chrome with Scoreboard active', async ({ page }) => {
  await page.goto(process.env.MMFP_URL + '/scoreboard?product=mli');

  // Header chrome
  await expect(page.getByTestId('app-shell-header')).toBeVisible();
  await expect(page.getByTestId('env-badge')).toBeVisible();
  await expect(page.getByTestId('run-id-chip')).toBeVisible();
  await expect(page.getByTestId('product-chip')).toBeVisible();
  // Rubric version chip moved here from the in-page header (MLI-262).
  await expect(page.getByTestId('rubric-version')).toContainText(/v\d+\.\d+/);

  // Tab nav: all four render, only Scoreboard is active.
  await expect(page.getByTestId('app-shell-tabs')).toBeVisible();
  await expect(page.getByTestId('tab-scoreboard')).toHaveAttribute('data-active', 'true');

  // Editor (MLI-195), Curator (MLI-196), and History are all navigable.
  for (const tab of ['editor', 'curator', 'history']) {
    const el = page.getByTestId(`tab-${tab}`);
    await expect(el).toBeVisible();
    await expect(el).toHaveAttribute('data-active', 'false');
    await expect(el).not.toHaveAttribute('data-disabled', 'true');
  }
});
