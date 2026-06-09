# Slice 3 deployment audit (MLI-261)

**Status:** evidence-gathering, not corrective work.
**Author:** Claude (MLI-261), 2026-05-12.
**Subject:** deployed dev (`ca-mmfp-ui-dev` / `ca-mmfp-api-dev`) versus the design references that exist in this repository.

This audit exists because the Slice 3 close-out reflection surfaced a gap nobody had looked at deployed dev until after the slice was declared structurally complete. The CORS error blocking candidate-detail is fixed in this PR; everything else in this document is description, not change. The intent is to let the decision about corrective-work shape (reopen Slice 3 vs. roll into Slice 4) be made on evidence.

## 1. Design references that exist in this repo

A walk of `docs/ui/` and `ui/` end-to-end. Each entry tagged with whether Slice 3 sub-task prose (MLI-181 through MLI-188) referenced it.

### `docs/ui/` — design surface in the docs tree

| File | Type | Referenced by Slice 3 tickets? |
|---|---|---|
| `docs/ui/scoreboard.png` | High-fidelity mockup of the full Scoreboard page | **No** |
| `docs/ui/editor.png` | High-fidelity mockup of the Rubric Editor page | **No** (out of slice scope) |
| `docs/ui/curator.png` | High-fidelity mockup of the Curator page | **No** (out of slice scope) |
| `docs/ui/history.png` | High-fidelity mockup of the History view | **No** |
| `docs/ui/promote.png` | High-fidelity mockup of the promotion modal | **No** |
| `docs/ui/prototype-print.html` | Print/PDF rendering of the full prototype | **No** |

**`docs/ui/scoreboard.png` is the load-bearing reference for Slice 3 and it is not cited in any Slice 3 ticket.** It is the single highest-fidelity description of what the deployed Scoreboard should look like and contains the entire chrome, portfolio summary, drift banner, and per-row trend strip that the deployed page lacks.

### `ui/prototype/` — runnable React prototype

| File | Purpose | Referenced by Slice 3 tickets? |
|---|---|---|
| `ui/prototype/README.md` | Explicit guidance: "Visual style from .jsx files; component primitives from `primitives.jsx`; page structure from `shell.jsx` + per-page .jsx files. Discrepancies indicate either deliberate evolution (document it) or regression (fix it)." | **No** |
| `ui/prototype/scoreboard.jsx` | Scoreboard page including TierCard, PortfolioSlot, Scorecard, DriftBanner, density/colour toggles | Yes — MLI-185/186/187 |
| `ui/prototype/shell.jsx` | App-shell header (Morae logo, product switcher, env badge, run id, rubric version), tabbed navigation | **No** |
| `ui/prototype/primitives.jsx` | Design-system primitives: `Btn` variants, `Chip` tones, `Panel`, `SectionHeader`, `TierPill`, `TierRule`, `Spark`, `Modal`, icons | **No** |
| `ui/prototype/data.jsx` | Canonical fixture data referenced by other prototype files | Implicit |
| `ui/prototype/editor.jsx` | Rubric Editor page (out of Slice 3 scope) | **No** |
| `ui/prototype/curator.jsx` | Curator page (out of Slice 3 scope) | **No** |
| `ui/prototype/history.jsx` | History panel | **No** |
| `ui/prototype/tweaks-panel.jsx` | Live design-adjustment tool (dev-only) | **No** |
| `ui/prototype/index.html` | Babel-in-browser entry point | n/a |
| `ui/prototype/assets/` | `morae-logo.svg`, `colors_and_type.css`, etc. | Partial — colour tokens reused; logo/typography not |

**`ui/prototype/README.md` is explicit:** the production UI is expected to lift visual style, primitives, and page structure from the prototype, and discrepancies should be documented as deliberate evolution or fixed as regression. Slice 3 tickets did neither. The READMEs sentence about `shell.jsx` providing page structure is the most material citation Slice 3 missed.

## 2. Deployed state (what's actually on `ca-mmfp-ui-dev` today)

Walkthrough recorded in a real browser (Playwright/Chromium) against a local stack that mirrors deployed (same Container Apps, just running on `localhost`). Same components, same fetch wiring, same API.

What renders on `/scoreboard?product=mli`:

- **No app shell.** No header. No Morae logo. No env badge. No tab navigation. No product switcher. The page begins with a bare `Model Fitness · MLI` eyebrow and an `<h1>Scoreboard</h1>`.
- **Three tier cards** stacked vertically. Each card has a tier title, subtitle, candidate count, a wide dimension table, and one trend strip at the bottom.
- **No portfolio summary.** The prototype's per-tier Primary / Fallback / Under evaluation / Rejected summary is absent. The deployed table shows every candidate row instead of summarising the portfolio decision.
- **No drift banner.**
- **One trend strip per tier**, not per candidate row as in the prototype. The trend strip is a self-rolled SVG sparkline with hover tooltips.
- **Candidate-detail drill-down opens** as a right-side modal showing per-dimension breakdown (after the CORS fix in this PR; was broken before).
- **No console errors** observed during the golden-path flow (only the React DevTools dev-mode info notice).

## 3. Specific divergences (deployed vs. `docs/ui/scoreboard.png` + `ui/prototype/`)

Each item links to the architectural-input on MLI-180 that contributed to the gap, where one is traceable.

| Divergence | Deployed | Prototype | Trail contribution |
|---|---|---|---|
| **App-shell chrome** | absent | Full header with logo, product switcher, env badge, rubric/run chips; tabs across the top | No Slice 3 ticket scoped the shell. `ui/prototype/shell.jsx` was never referenced. Not a single architectural decision — a scope omission. |
| **Portfolio summary per tier** | absent (table-only) | Primary slot, Fallback slot, Under evaluation count, Rejected count | No Slice 3 ticket scoped it. The closest cite on MLI-180 is the MLI-185 trail entry ("TierCard owns ranking; children trust their input") which scoped TierCard to render a ranked table rather than a portfolio decision view. |
| **Per-row trend mini-strips** | one per tier | one per candidate row | MLI-186 trail entry on MLI-180 explicitly scoped TrendStrip to a tier-level multi-line chart, then captured the "self-rolled SVG over recharts" decision. The per-row sparkline framing was never on the table. |
| **Trend visual flatness** | self-rolled SVG, ~180 LoC, no axes | Same self-rolled visual style in prototype | MLI-186 trail: *"Self-rolled SVG over recharts as standing choice; revisit when real chart complexity arrives."* The deployed strip works exactly as that decision specified; the visual bareness is a consequence of staying inside what 180 lines of SVG can express. |
| **Trend data appears flat** | Three back-dated runs, identical rubric, real engine output | Prototype shows realistic movement | `scripts/seed_dev_runs.py` header is explicit: *"Varies run timing only (back-dated created_at/started_at/completed_at), not rubric weights."* MLI-183 chose this to avoid committing seed-only edits to the tracked `rubric.yaml`. The flat-looking strip is the visible consequence — for `gpt-4o` on tier_3 the three runs scored 100 / 70 / 90, which produces a real but small visual signal at 56 px tall. |
| **Drift signals** | absent | Yellow banner with "N active drift signals from production" | No Slice 3 ticket scoped drift. Drift is a downstream concept (online evaluators) that the platform doesn't produce yet; the prototype's banner is aspirational. Documenting as out-of-scope, not gap. |
| **Status terminology** | `approved_primary` / `approved_fallback` / `under_evaluation` / `rejected` | `primary` / `fallback` / `eval` / `rejected` | The deployed naming matches `mmfp/models/matrix_run.py`. Cosmetic divergence only. |
| **Family terminology** | `chat` / `reasoning` | `frontier` / `fine-tune` / `custom` | Real divergence: the deployed slate has 2 families; the prototype models a 3-family world. MLI-185 trail entry chose the FamilyDot palette (`bg-orange` reasoning / `bg-neutral-5` chat) as the standing palette. Prototype's `frontier` colour (blue) is unused in the deployed app. |
| **Density and colour toggles** | absent | `density` (compact/comfortable), `colorOn` (chromatic vs. greyscale tier rules) | Not scoped. |
| **Page-level summary** (totals, started-at, average evals, USD cost, duration, refusals) | only run id + rubric + started-at | full KPI row at top of page | Not scoped. The deployed minimal triple is from MLI-184's endpoint-shape decision; the wider KPIs would require new aggregations. |
| **Export PDF, Disable URL, time-range toggle** | absent | present in prototype | Not scoped. |
| **CORS** | broken on deployed dev until this PR | n/a (prototype is one-origin) | The deployment-shape gap that triggered this audit. No Slice 3 ticket addressed cross-origin browser fetches because before MLI-187 there were none — all fetches were server-side. |

## 4. Architectural-input trail entries that contributed

Two MLI-180 trail entries shaped what shipped most visibly, and one decision lives in code rather than on the trail.

1. **MLI-186 "self-rolled SVG over recharts" (MLI-180 comment, 2026-05-12 21:43)** —
   > "Treat as a deliberate 'stay' rather than an accident — if Slice 4 or 6 add real chart complexity, recharts becomes the obvious adopt; the swap is mechanical at this size."
   This is the standing decision. The trend strip's visual bareness is a faithful realisation. The decision is sound on its own terms — the contribution to the gap is that it left the strip looking aspirational where the prototype implies "a real chart belongs here." The decision tagged its own revisit condition; the audit observes the condition may have arrived sooner than expected because the strip is the most visible new surface in Slice 3.

2. **MLI-183 "seed varies run timing only, not rubric weights" (decision lives in `scripts/seed_dev_runs.py:13-18`, not on the MLI-180 trail explicitly)** —
   > "Varies run timing only (back-dated created_at/started_at/completed_at), not rubric weights. Varying weights would commit seed-only edits to the tracked rubric.yaml; a flat trend over a stable rubric is enough for trend-strip visualisation."
   This decision is correct on its own terms (it preserves the canonical rubric) but it contributes directly to the deployed trend looking flat. The MLI-180 close-out comment cites this as "Seed-as-canonical with `baseline-matrix.yml` disabled. Re-enable triggers named on the trail" but does not name the timing-vs-weights tradeoff. **The decision is not stated as architectural input on MLI-180; it's in the seeder header.** Worth surfacing back onto the trail if Slice 4 wants to address it.

3. **MLI-185 "TierCard owns ranking; children trust their input" (MLI-180 comment, 2026-05-12 21:22)** —
   The trail entry scoped TierCard to a ranked table. Combined with no separate ticket for the portfolio summary, this is why the deployed tier card shows every row rather than the prototype's "Primary / Fallback / Under evaluation / Rejected" four-cell summary. Architecturally fine; the scope decision is what produced the user-visible gap.

The broader pattern: **none of the Slice 3 tickets referenced `docs/ui/scoreboard.png` or `ui/prototype/shell.jsx`.** Slice 3 tickets that referenced the prototype referenced `ui/prototype/scoreboard.jsx` alone, which is the page body — not the shell, not the design system, not the high-fidelity mockup of what the page should look like. This is the load-bearing finding of the audit.

## 5. Recommended corrective tickets (options, not commitments)

Framed as choices for Wayne; estimates are rough.

**Option A — surgical, ship-what's-there.** Don't reopen Slice 3. Carry the gap as known limitations into Slice 4 and prioritise inside that slice's scope. Cost: minimum. Risk: deployed dev keeps looking unfinished as it is shown to stakeholders.

**Option B — app-shell-only follow-up ticket.** One Sonnet-tier ticket: implement the header (Morae logo, env badge, rubric/run chips) and a single Scoreboard tab. No portfolio summary, no per-row trends. Hits the most jarring "looks like a debug page" gap with the smallest possible scope. Cost: small. Risk: low — chrome is conventionally additive.

**Option C — portfolio summary in tier cards.** One ticket to add the Primary / Fallback / Under evaluation / Rejected four-cell summary above the candidate table. Requires the slate to actually declare primary/fallback (the deployed status enum supports it; whether the seeded data does is a check). Cost: small–medium. Risk: depends on whether the seed grants approved-primary statuses anywhere.

**Option D — trend strip upgrade (recharts swap or visual polish).** The MLI-186 decision pre-named recharts as the swap target if chart complexity grows. A ticket to add y-axis labels, run-date ticks, and a legend would lift the perceived fidelity without changing the data shape. Cost: medium. Risk: low if scoped tightly; recharts adoption is a separate ADR question.

**Option E — seed-data realism.** Either:
  (a) widen the timing-only seed to seed more diverse historical scores (e.g. multiple real runs against different deployment names that genuinely scored differently), or
  (b) accept the flatness as a consequence of "stable rubric, real engine output" and document it on the page itself (e.g. tooltip explaining what produced these three points).
  Cost: (a) medium–large, (b) trivial. Risk: (a) re-opens the seeder design discussion, (b) does not.

**Option F — full reopen of Slice 3.** Scope an additional sub-task batch (MLI-262 … MLI-26x) that reads `docs/ui/scoreboard.png` and `ui/prototype/shell.jsx` as the canonical references and ships the app shell + portfolio summary + per-row trend strips. Cost: large. Risk: blurs the slice boundary; better expressed as Slice 4 if the work warrants it.

The most defensible minimum is B + C (chrome + portfolio summary). Anything that touches trend visualisation or seed data is a separate, optional decision.

## 6. Process finding

The most material finding is not in the divergence table — it's that the load-bearing design reference (`docs/ui/scoreboard.png` plus `ui/prototype/shell.jsx`) was never opened during Slice 3. Slice 3 tickets that did reference the prototype referenced `ui/prototype/scoreboard.jsx` (the page body) and treated it as the whole design. The prototype's own README is explicit about what to lift from where; the tickets did not follow that map.

If there is a single ticket-template change worth making for Slice 4, it is: **for every UI sub-task, the brief must explicitly cite the design reference files in `docs/ui/` and `ui/prototype/` that the sub-task will lift from, and call out any not-lifted-from references as a deliberate decision.** Discrepancies are then either documented evolutions or surfaced for correction — which is what `ui/prototype/README.md` always asked for.
