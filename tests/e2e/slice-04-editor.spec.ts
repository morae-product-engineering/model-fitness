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
//     re-score-existing-runs engine behind impact-preview-tier_3 and
//     ranking-change-row.
//   - The save path itself (PUT /api/products/{product}/rubric) already
//     shipped in Slice 3.5 (MLI-273); the Editor consumes it as its save call.
//
// EXPECTED RED FAILURE MODE (on main, until Slice 4 lands): the /editor route
// does not exist — only /scoreboard ships today — so the page renders Next's
// 404 and the first `getByTestId('rubric-version')` times out. That is the
// correct red. Do NOT loosen the selectors, add a skip, or invent the
// testids; the slice's implementation makes this green.
//
// Dimension choice: tier_3's two ACTIVE dimensions are `latency_p95` and
// `cost_per_completed_interaction` (each weight 10; the five inferential dims
// are draft/weight-0 until Slice 6 — see products/mli/KNOWN_GAPS.md). The
// active partition must sum to (0, 100] (mmfp/models/rubric.py Tier validator),
// so 30 + 5 = 35 is valid and re-weights latency to dominate, which should
// flip at least one tier_3 ranking once the preview/re-score path is live. The
// MLI-190 description's `t3.synthesis_quality` is a DRAFT dimension (weight
// pinned to 0) — editing it to a non-zero weight would fail rubric validation,
// which is why the active dims are substituted here.
import { test, expect } from '@playwright/test';

test('editor: change weight, preview impact, save commits to git', async ({ page }) => {
  await page.goto(process.env.MMFP_URL + '/editor?product=mli');

  const versionBefore = await page.getByTestId('rubric-version').textContent();

  await page.getByTestId('weight-input-tier_3.latency_p95').fill('30');
  await page.getByTestId('weight-input-tier_3.cost_per_completed_interaction').fill('5');

  await expect(page.getByTestId('impact-preview-tier_3')).toBeVisible();
  await expect(page.getByTestId('ranking-change-row').first()).toBeVisible();

  await page.getByTestId('save-note').fill('Testing impact preview');
  await page.getByTestId('save-button').click();

  await expect(page.getByTestId('toast')).toContainText('Rubric saved');
  const versionAfter = await page.getByTestId('rubric-version').textContent();
  expect(versionAfter).not.toBe(versionBefore);
});
