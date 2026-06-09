// @jira: MLI-200
// Slice 5 acceptance test (promotion + audit history). Authored from the
// MLI-199 description's test sketch, reconciled to shipped reality per the
// MLI-200 architectural-reality comment (2026-06-02) and the parent MLI-199
// Slice-5 architectural-reality comment. The reconciliation and the deliberate
// target/selector decisions are recorded in the MLI-200 closing comment.
//
// All testids are implemented (MFP-15). Expected to go GREEN against deployed
// dev once the seeded candidate scores above the primary threshold (75).
// Implementation locations:
//   action-promote-primary   DecisionButtons in CandidateDetail.tsx (hidden
//                            when score < primaryThreshold, default 75)
//   promotion-rationale      DecisionModal.tsx textarea
//   promotion-submit         DecisionModal.tsx confirm button (disabled until
//                            rationale.trim().length >= 5)
//   toast                    CandidateDetail.tsx fixed-bottom pill, auto-
//                            dismissed after 3 s; text: "promoted to primary"
//   history-toggle           AuditHistory in CandidateDetail.tsx — show/hide
//                            toggle, visible when audit entries > 0
//   history-entry            AuditEntryRow testid; text includes action label
//                            "promoted to primary" (lowercase)
//
// Target candidate (verified, not assumed). The MLI-199 sketch drilled into a
// tier_3 candidate scoring >=75. The MLI-200 architectural-reality comment
// flags that as unverified: tier_3 has only two active dimensions and is a
// strict dominance chain. tier_2's rank-1 is also unsafe as a green-time
// target — the Slice 4 durable-save spec (slice-04-editor.spec.ts) toggles
// tier_2's query_correctness/latency_p95 weighting on every run, flipping
// kimi-k2-6 between rank 1 and rank 5. This spec therefore targets the rank-1
// tier_1 candidate: tier_1 is untouched by the Slice 4 toggle, is a strict
// dominance chain (so rank-1 is stable), and every tier_1 candidate clears the
// primary threshold (>=75) against the seed (all 100.0 in the latest seed run;
// composite recomputed via the real scoreboard aggregation). Targeting by rank
// (.first()) rather than a specific candidate id keeps it robust to tie order
// within the eligible set.
//
// Eligibility gate NOT asserted. The MLI-199 sketch filtered candidates by a
// `candidate-score-eligible-primary` testid. That selector presupposes the
// eligibility-gate definition, which is an OPEN MLI-199 architectural decision;
// gating drill-down on it would also red the test at drill-down rather than at
// the absent promotion UI. We drill into the verified-eligible rank-1 tier_1
// row and let the red surface at the promotion action.
//
// Status model NOT asserted. Whether promotion is global (multi-tier) or
// tier-scoped (per-tier Candidate.status) is an OPEN MLI-199 decision. This
// spec asserts only the settled invariants — rationale required (submit
// disabled until filled, enabled after), a toast confirmation, and a
// History-panel entry after promotion. It does not assert a status enum value
// (approved_primary / ...) nor multi-tier vs per-tier behaviour.
import { test, expect } from '@playwright/test';

test('promote candidate writes audit log entry', { tag: '@slice-acceptance' }, async ({ page }) => {
  await page.goto(process.env.MMFP_URL + '/scoreboard?product=mli');

  // Drill into the rank-1 tier_1 candidate — verified eligible for primary
  // (>=75) against the seed; see header. The candidate-detail overlay opens on
  // row click (Slice 4 — `candidate-detail-overlay`).
  await page.getByTestId('tier-tier_1-candidate').first().click();
  await expect(page.getByTestId('candidate-detail-overlay')).toBeVisible();

  // Promote-to-primary action — absent until the Slice 5 actions UI lands;
  // this is the first red driver.
  await page.getByTestId('action-promote-primary').click();

  // Rationale is required: submit stays disabled until the rationale is filled.
  const submit = page.getByTestId('promotion-submit');
  await expect(submit).toBeDisabled();
  await page
    .getByTestId('promotion-rationale')
    .fill('Strongest classification accuracy and lowest latency on the R1 set');
  await expect(submit).toBeEnabled();
  await submit.click();

  // Toast confirms (human-readable display copy).
  await expect(page.getByTestId('toast')).toContainText('promoted to primary');

  // The audit-history panel shows the new entry.
  await page.getByTestId('history-toggle').click();
  await expect(page.getByTestId('history-entry').first()).toContainText(
    'promoted to primary',
  );
});
