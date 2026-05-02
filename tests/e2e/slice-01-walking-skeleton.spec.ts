// @jira: MLI-153
import { test, expect } from '@playwright/test';

test('walking skeleton: scorecard page displays hardcoded score', async ({ page }) => {
  await page.goto(process.env.MMFP_URL + '/scoreboard');
  await expect(page.getByTestId('skeleton-score')).toContainText('42');
  await expect(page.getByTestId('skeleton-source')).toContainText('hardcoded MatrixRun');
});
