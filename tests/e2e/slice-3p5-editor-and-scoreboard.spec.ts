// @jira: MLI-268
// Slice 3.5 acceptance test. Goes green when the following sub-tasks land:
//   - MLI-269 (3.5.2): rubric model + matrix engine changes (Python side)
//   - 3.5.7 sub-task: ships `dim-weight-<id>` and `vendor-badge` testids
//     in the scoreboard candidate detail view (rubric weight display)
//   - 3.5.8 sub-task: ships `candidate-sparkline` testid in the candidate
//     detail view (per-candidate trend sparkline)
//
// None of these testids exist on main. The Playwright run will fail at the
// first `getByTestId` call because the element won't be on the page.
// That is the expected failure mode — do not loosen the selectors, do not
// add a skip, do not invent the testids.
//
// What each testid contracts:
//   dim-weight-classification_accuracy — a visible element showing the
//     weight (35%) for the `classification_accuracy` dimension for the
//     selected candidate in tier_1. Proves the rubric weight round-trips
//     from YAML → scoring engine → UI.
//   vendor-badge — a badge element identifying the model vendor (e.g.
//     "Azure OpenAI", "Anthropic") in the candidate detail panel.
//   candidate-sparkline — a sparkline / mini trend chart for the selected
//     candidate, rendered inside the detail panel.
import { test, expect } from '@playwright/test';

test('weight save round-trips and candidate detail renders rubric weights', { tag: '@slice-acceptance' }, async ({ page }) => {
  await page.goto(process.env.MMFP_URL + '/scoreboard?product=mli');
  await page.getByTestId('tier-tier_1-candidate').first().click();
  await expect(page.getByTestId('dim-weight-classification_accuracy')).toContainText('35%');
  await expect(page.getByTestId('vendor-badge').first()).toBeVisible();
  await expect(page.getByTestId('candidate-sparkline').first()).toBeVisible();
});
