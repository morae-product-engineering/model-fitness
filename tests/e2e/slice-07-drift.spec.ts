// @jira: MFP-92 (Slice 7 acceptance test — drift detection)
//
// Slice 7 acceptance test (UI side). Deliberately RED until the Slice 7
// implementation sub-tasks (MFP-93+) land. It describes drift detection
// end-to-end from the *viewer's* vantage point: a promoted candidate whose
// live sample diverges from its baseline produces an active drift signal that
// surfaces (a) as a count on the Scoreboard drift banner and (b) as a row with
// severity + candidate detail in a dedicated Monitor view.
//
// WHAT THIS TESTS
//   The drift signal flows sensor -> store/API -> UI. This spec only touches
//   the UI end of that flow; the sensor side is pinned by the pytest sibling
//   (mmfp/sensors/tests/test_drift_sensor.py). Together they bracket the slice.
//
// WHY IT'S RED RIGHT NOW
//   None of the Slice 7 UI surface exists yet:
//     - no `drift-banner` testid on the scoreboard
//     - no `/monitor` route at all
//     - no drift-signal store or API endpoint feeding either surface
//     - no DriftSensor producing the signals in the first place
//   FIRST RED DRIVER: the `drift-banner` testid is absent on the scoreboard,
//   so the first `expect(...).toBeVisible()` below fails. That is the intended
//   state — it reds because "Slice 7 isn't built yet", not because of a stale
//   selector against shipped UI.
//
// SEEDED, NOT LIVE
//   This asserts against a SEEDED drift signal (exactly one active signal for
//   the promoted tier_1 candidate), wired by the Slice 7 seed the same way the
//   scoreboard seed wires baseline runs. It does NOT exercise live production
//   telemetry — that's a later concern and would make the test non-deterministic.
//
// WHAT IS NOT ASSERTED (open decisions deferred to MFP-93+)
//   - Sensor internals / how the signal was computed (pinned in pytest, not here).
//   - Severity thresholds (what delta maps to low/medium/high) — the pytest
//     sibling pins the >=20-point => "high" mapping; here we only assert the
//     rendered severity text is present, not the threshold math.
//   - Whether the banner count is per-tier or portfolio-wide — we seed exactly
//     one signal so "1 active drift signal" holds under either model.
//   - The exact Monitor route shape beyond `/monitor?product=mli` and the
//     dismiss/acknowledge lifecycle of a signal (not part of this slice's
//     acceptance).
//
// TESTID CONTRACT ESTABLISHED FOR SLICE 7 IMPLEMENTERS (these are the names
// MFP-93+ must emit; chosen here so the contract is pinned before build):
//   Scoreboard:
//     drift-banner            container, visible iff >= 1 active signal
//     drift-signal-count      element whose text contains the active count
//     drift-monitor-link      link/button navigating to the Monitor view
//   Monitor view (/monitor?product=mli):
//     drift-signal-row        one per active signal (repeated)
//     drift-signal-candidate  candidate_id within a row
//     drift-signal-severity   severity indicator within a row ("high" etc.)
import { test, expect } from '@playwright/test';

// The promoted tier_1 candidate the Slice 7 seed raises a drift signal for.
// Matches the pytest baseline fixture so both halves of the slice agree.
const SEEDED_DRIFT_CANDIDATE = 'kimi-k2-6';

test(
  'scoreboard drift banner shows the active signal count',
  { tag: '@slice-acceptance' },
  async ({ page }) => {
    await page.goto(process.env.MMFP_URL + '/scoreboard?product=mli');

    // The banner is visible because the seed has exactly one active signal.
    // Absent today — this is the first red driver for the whole slice.
    const banner = page.getByTestId('drift-banner');
    await expect(banner).toBeVisible();

    // The count surfaces the number of active signals. One seeded signal.
    await expect(page.getByTestId('drift-signal-count')).toContainText('1');
    await expect(banner).toContainText('active drift signal');

    // A way through to the detail view must be present.
    await expect(page.getByTestId('drift-monitor-link')).toBeVisible();
  },
);

test(
  'monitor view shows the drift signal with candidate and severity',
  { tag: '@slice-acceptance' },
  async ({ page }) => {
    await page.goto(process.env.MMFP_URL + '/monitor?product=mli');

    // At least one signal row renders — the seeded tier_1 drift signal.
    const row = page.getByTestId('drift-signal-row').first();
    await expect(row).toBeVisible();

    // The row identifies the candidate the signal concerns...
    await expect(row.getByTestId('drift-signal-candidate')).toContainText(
      SEEDED_DRIFT_CANDIDATE,
    );

    // ...and surfaces a severity indicator. The seeded signal is a ~30-point
    // drop, which the sensor classifies "high" (see the pytest sibling).
    await expect(row.getByTestId('drift-signal-severity')).toContainText('high');
  },
);
