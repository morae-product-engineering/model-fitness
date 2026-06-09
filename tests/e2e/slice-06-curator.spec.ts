// @jira: MFP-72
// Slice 6 acceptance test (Curator: dataset management + judge queue review).
// Authored from the MFP-10 slice spec. Deliberately red against the current
// codebase — the Curator page renders only a placeholder stub today.
//
// Goes GREEN when all of these implementation sub-tasks have landed:
//   - MFP-74 (6.3): LLM-judge evaluator — populates the judge sample queue
//   - MFP-75 (6.4): API endpoints for datasets and the judge queue
//   - MFP-76 (6.5): Curator UI page — replaces the stub at /curator
//   - MFP-77 (6.6): Matrix re-run with judge enabled — seeds the queue with entries
//
// First failure driver: the Curator page currently renders only
// `curator-placeholder` ("Coming in Slice 6"). The first assertion below,
// `expect(page.getByTestId('curator-dataset-table')).toBeVisible()`, will fail
// immediately. No import errors; collection succeeds cleanly.
//
// Tier 3 is targeted throughout because synthesis_quality is the only
// LLM-judge dimension in the v0.1 rubric. Judge queue entries (step 3) only
// exist for Tier 3 candidates and only after MFP-77 has executed on the dev
// environment. If MFP-77 has not yet run, step 3 will fail at
// `expect(firstRow).toBeVisible()` rather than at the agree-mark assertion.
//
// testid contract — MFP-76 must implement all of these:
//
//   curator-dataset-table     datasets table on the Datasets tab
//   curator-add-example-btn   "Add example" button
//   curator-add-example-modal modal overlay wrapping the add-example form
//   add-example-input         task prompt textarea (required; submit disabled when empty)
//   add-example-expected      golden answer JSON textarea (required)
//   add-example-submit        submit/validate button inside the modal
//   curator-tab-queue         "Judge sample queue" sub-tab button
//   curator-queue-row         each row in the judge queue list
//   curator-queue-agree       agree button inside a queue row
//   curator-queue-status      status chip inside a queue row
//   toast                     already exists from slice-05

import { test, expect } from '@playwright/test';

test(
  'curator: browse datasets, add example, and mark judge sample',
  { tag: '@slice-acceptance' },
  async ({ page }) => {
    await page.goto(process.env.MMFP_URL + '/curator?product=mli&tier=tier_3');

    // --- 1. Browse golden datasets ---
    // First red driver: curator-placeholder is the only thing rendered today.
    await expect(page.getByTestId('curator-dataset-table')).toBeVisible();

    // --- 2. Add a golden example via schema-validated form ---
    await page.getByTestId('curator-add-example-btn').click();
    await expect(page.getByTestId('curator-add-example-modal')).toBeVisible();

    // Submit is disabled until the required fields are filled (schema validation).
    const submitBtn = page.getByTestId('add-example-submit');
    await expect(submitBtn).toBeDisabled();

    await page
      .getByTestId('add-example-input')
      .fill(
        'Summarise the key obligations for the counterparty in the attached service agreement.',
      );
    await page
      .getByTestId('add-example-expected')
      .fill(
        '{"themes": ["indemnity", "termination"], "summary": "Counterparty must provide 30-day notice."}',
      );

    await expect(submitBtn).toBeEnabled();
    await submitBtn.click();

    // Toast confirms the example was staged.
    await expect(page.getByTestId('toast')).toContainText('example');

    // --- 3. Mark a judge sample; verify the mark persists after reload ---
    // Navigate to the judge sample queue sub-tab.
    await page.getByTestId('curator-tab-queue').click();

    // At least one pending entry must exist — populated by the MFP-77 matrix
    // re-run with the LLM-judge enabled. If MFP-77 has not run, this assertion
    // is the failure point; see header note.
    const firstRow = page.getByTestId('curator-queue-row').first();
    await expect(firstRow).toBeVisible();

    // Mark the first sample as agreed.
    await firstRow.getByTestId('curator-queue-agree').click();
    await expect(page.getByTestId('toast')).toContainText('agree');

    // Reload and confirm the mark persisted (API round-trip, not just local state).
    await page.reload();
    await page.getByTestId('curator-tab-queue').click();
    await expect(
      page.getByTestId('curator-queue-row').first().getByTestId('curator-queue-status'),
    ).toContainText('Agreed');
  },
);
