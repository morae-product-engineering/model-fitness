// @jira: MLI-153
// Superseded by tests/e2e/slice-02-real-scoring.spec.ts (MLI-168).
// The walking-skeleton page was replaced by the real scoreboard wiring in
// MLI-175; the hardcoded `42` and `hardcoded MatrixRun` strings no longer
// render. Keeping the file as test.skip rather than deleting so the @jira
// breadcrumb back to MLI-153 stays visible during the slice 2 review.
import { test, expect } from '@playwright/test';

test.skip('walking skeleton: scorecard page displays hardcoded score', async ({ page }) => {
  await page.goto(process.env.MMFP_URL + '/scoreboard');
  await expect(page.getByTestId('skeleton-score')).toContainText('42');
  await expect(page.getByTestId('skeleton-source')).toContainText('hardcoded MatrixRun');
});
