# Slice 3.5 deployment audit (MLI-267)

**Status:** evidence-gathering, ground-truth snapshot.
**Author:** Claude (post-slice close-out), 2026-05-16.
**Subject:** what Slice 3.5 (MLI-267 — *Align the v0.1 Rubric with its reference and close Slice 3 visual gaps*) actually shipped to `ca-mmfp-ui-dev` / `ca-mmfp-api-dev`, where it lives, and what its facts are.

Companion to [docs/slice-3-deployment-audit.md](slice-3-deployment-audit.md). The two files together compose a ground-truth library: when a new chat window opens months from now to work on Slice 4, 5, or 6, these are the files that say "here's what's true." Same shape, same level of detail.

## 1. What shipped (sub-task by sub-task)

Eight sub-tasks under MLI-267 — MLI-268 through MLI-275. PRs #51 through #58 against `main`. Closing comment per ticket carries the acceptance verification and per-file diff; this section names what each one delivered and where to find it. Don't re-read the closing comments below — link to them from Jira directly.

### MLI-268 (PR [#51](https://github.com/morae-product-engineering/model-fitness/pull/51)) — acceptance tests, red

Transcribed both parent-Task acceptance tests verbatim into the right files and wired them into existing CI matrices via path conventions (no workflow edits). [mmfp/tests/test_rubric_alignment.py](../mmfp/tests/test_rubric_alignment.py) carries module-level `pytestmark = pytest.mark.slice_acceptance` so the standard `Unit Tests (pytest)` job excludes it and the separate `Slice Acceptance Tests (pytest)` job runs it with `continue-on-error: true`. [tests/e2e/slice-3p5-editor-and-scoreboard.spec.ts](../tests/e2e/slice-3p5-editor-and-scoreboard.spec.ts) follows the established Playwright shape; module-level deferred imports inside the test body (not module top-level) so `pytest` can collect the file cleanly. Both fail red on `main` until the rest of the slice lands. Closing comment id 31803 on MLI-268.

### MLI-269 (PR [#52](https://github.com/morae-product-engineering/model-fitness/pull/52)) — Dimension.status + active-weight normalisation

The schema change every other sub-task in the slice depends on. Adds `Dimension.status: Literal["active", "draft"]` (default `"active"`, so existing rubrics load unchanged) at [mmfp/models/rubric.py:86-93](../mmfp/models/rubric.py#L86-L93), the `Tier.active_dimensions()` / `Tier.draft_dimensions()` partition helpers at [mmfp/models/rubric.py:148-154](../mmfp/models/rubric.py#L148-L154), and rewrites the Tier validator at [mmfp/models/rubric.py:156-188](../mmfp/models/rubric.py#L156-L188) to (a) sum only `active` weights into the `(0, 100]` bound, (b) reject zero-active tiers, and (c) **forbid non-zero weights on draft dimensions** per the MLI-267 architectural-input. `MatrixRun.scores_for_tier(tier_id, tier=None)` at [mmfp/models/matrix_run.py](../mmfp/models/matrix_run.py) gained an optional `Tier` argument that, when present, triggers rubric-weighted aggregation normalised by the per-tier active-weight total — so Tier 3's 20% active coverage still produces 0–100 scores. Matrix engine coverage validation and per-cell dispatch iterate `tier.active_dimensions()`. Recommended Opus tier ("Architect/Senior"). Closing comment id 31805.

### MLI-270 (PR [#53](https://github.com/morae-product-engineering/model-fitness/pull/53)) — Metric evaluator family

First implementation of the Metric evaluator method family. `LatencyP95Evaluator` and `CostPerCallEvaluator` live under [mmfp/evaluators/metric/](../mmfp/evaluators/metric/) with shared `_helpers.py` (`normalise_lower_better` plus typed context extraction). Both are single-class config-driven: `cost_per_call` takes optional `per_calls` (default 1, Tier 1 sets 1000) so the same class absorbs `$/1000` and `$/call` framings without sibling classes. Reference values (`reference_p95_ms` for latency, `reference_usd` for cost) live on `Dimension.evaluator_config: dict | None` — declared formally in MLI-272 but the pattern is set here. 28 unit tests across the two evaluators plus a registry resolution test. Recommended Opus. Closing comment id 31807.

### MLI-271 (PR [#54](https://github.com/morae-product-engineering/model-fitness/pull/54)) — deterministic evaluators batch 2

Heaviest sub-task of the slice. Five new deterministic evaluators under [mmfp/evaluators/deterministic/](../mmfp/evaluators/deterministic/): `parse_rate`, `structured_output_reliability`, `context_window_adequacy`, `confidence_calibration` (continuous Brier-derived score), and `query_correctness` (loads a hermetic SQLite golden DB into `:memory:` under a SELECT-only authorizer per evaluation). `_helpers.py` extended with `continuous_score` and `format_jsonschema_error`. New `products/mli/datasets/golden_dbs/query_correctness_v0.sql` (5 matters, 10 documents — legal-domain schema) plus a README documenting the harness contract and the SQLite-dialect constraint. 67 new unit tests across the five evaluators + a deterministic-registry test. Recommended Opus. Closing comment id 31809.

### MLI-272 (PR [#55](https://github.com/morae-product-engineering/model-fitness/pull/55)) — align rubric YAML, datasets, Slice 2/3 baselines

The integration sub-task that turns the new schema + new evaluator families into a runnable rubric. Owns the engine-side plumbing no other sub-task did:

- `Dimension.evaluator_config: dict[str, Any] | None` formally landed at [mmfp/models/rubric.py:112-124](../mmfp/models/rubric.py#L112-L124).
- `Candidate.context_window: int` (required, no default) at [mmfp/models/candidate.py:99-103](../mmfp/models/candidate.py#L99-L103).
- `MatrixEngine._evaluate_traced` populates a per-dispatch `eval_context` dict that threads `evaluator_config`, `latency_ms`, `candidate_context_window`, and a defensive `cost_usd = Decimal("0")` placeholder at [mmfp/engine/matrix.py:559-587](../mmfp/engine/matrix.py#L559-L587). The `cost_usd = 0` placeholder is load-bearing context — the binding doesn't emit cost today, so `cost_per_call` returns `min(reference/0, 1) = 1.0` for every candidate, flattening cost discrimination until a cost sensor lands.

[products/mli/rubric.yaml](../products/mli/rubric.yaml) rewritten to the v0.1 reference shape (catalogue in §6). [products/mli/candidates.yaml](../products/mli/candidates.yaml) gained `context_window` on every candidate. [products/mli/datasets/tier_1.jsonl](../products/mli/datasets/tier_1.jsonl) rewritten so prompts elicit `{"label", "confidence"}` JSON (one binding call scored across all five Tier-1 active dimensions per MLI-258). [products/mli/datasets/tier_2.jsonl](../products/mli/datasets/tier_2.jsonl) rewritten as raw-SQL prompts with `expected.rows` against the MLI-271 golden DB. Tier 3 dataset unchanged. Recommended Sonnet. Closing comment id 31810.

### MLI-273 (PR [#56](https://github.com/morae-product-engineering/model-fitness/pull/56)) — rubric write endpoint

New API surface `PUT /api/products/{product}/rubric` at [mmfp/api/rubric_write.py](../mmfp/api/rubric_write.py). Validates payload through `Rubric.model_validate` (so every invariant 3.5.2 and 3.5.5 established holds in the persisted YAML), auto-bumps the minor version (`^v\d+\.\d+$`, server-owned), writes YAML to disk, commits via git. **The git commit is the audit log:** actor → author, timestamp → committer date, version delta + note → message. No separate `status_change` table. Steward identity arrives via a trusted `X-Steward-Identity` HTTP header with fallback `PLACEHOLDER_STEWARD = "Unknown Steward <steward@unknown.local>"` exported from the module so tests pin the exact string. 422 on validation failure (structured detail); 409 on `expected_version` mismatch carrying `current_version` for the UI to refetch. Recommended Opus. Closing comment id 31812.

### MLI-274 (PR [#57](https://github.com/morae-product-engineering/model-fitness/pull/57)) — rubric-weight-aware CandidateDetail

Replaced the bar visualisation in `CandidateDetail` with a four-column rubric-weight-aware breakdown (Dimension / Weight / Score / Weight × Score contribution). Endpoint at [mmfp/api/candidate_detail.py](../mmfp/api/candidate_detail.py) extended to inline the rubric (active + draft dimensions per tier) and its version in the same round-trip; the trimmed `RubricView` projection at [mmfp/api/candidate_detail.py:113-126](../mmfp/api/candidate_detail.py#L113-L126) drops `evaluator`, `evaluator_config`, judge config, gates, and thresholds (which the UI does not consume). `rubric.version` is the field the Slice 4 Editor will pass back as `expected_version` to the rubric-write endpoint, so inlining here also seeds that handshake. Drafts visible but de-emphasised with "Draft — activates in Slice 6" label. New `dim-weight-<id>` testids each render the weight formatted as a percentage. UI parser extended at [ui/lib/scoreboard.ts](../ui/lib/scoreboard.ts) to convert `weight` from Decimal string → number at the MLI-175 boundary. Recommended Sonnet. Closing comment id 31814.

### MLI-275 (PR [#58](https://github.com/morae-product-engineering/model-fitness/pull/58)) — Scoreboard visual pass

Holistic visual pass on the Scoreboard against `docs/ui/scoreboard.png`. Adds: Vendor column + per-row Vendor badges via [ui/lib/vendor.ts](../ui/lib/vendor.ts) (prefix table, frontend-only — no backend field); a Trend column with a per-row candidate sparkline driven by the same trends payload TrendStrip already consumes; a left-edge tier accent rule and a compact TX pill in TierCard header (T1 yellow / T2 orange / T3 warm-red); vendor badge and candidate sparkline in CandidateDetail header too; conditional `base_model` line in CandidateDetail (UI only — no v0.1 candidate carries one yet). Absorbs MLI-188's "Visual fidelity partial" follow-up. Makes the parent Slice 3.5 Playwright spec fully green. Recommended Sonnet. Closing comment id 31816.

## 2. Prototype catalogue update

No new prototype files. The catalogue from §1 of [docs/slice-3-deployment-audit.md](slice-3-deployment-audit.md) is still complete.

One naming-orientation note for the next agent: **the source for Slice 4's Editor is [ui/prototype/editor.jsx](../ui/prototype/editor.jsx)**, not `workbench.jsx`. There is no `workbench.jsx`; the prototype's editor file is named `editor.jsx`. The MLI-274 closing comment is explicit that `editor.jsx` is the design reference Slice 4 should lift from.

The MLI-275 closing comment also documents that the prototype's `vendor` mock data at [ui/prototype/data.jsx:60-69](../ui/prototype/data.jsx) is the source for the human-readable vendor labels — the spellings in `ui/lib/vendor.ts` are deliberately kept in sync. The `ui/prototype/README.md` discrepancies-are-deliberate-or-regression rule applies.

## 3. Engine-side changes

The schema and engine plumbing that crossed sub-task boundaries:

- **`Dimension.status: Literal["active", "draft"]`** (default `"active"`) at [mmfp/models/rubric.py:86-93](../mmfp/models/rubric.py#L86-L93). Existing rubrics load unchanged.
- **`Dimension.evaluator_config: dict[str, Any] | None`** at [mmfp/models/rubric.py:112-124](../mmfp/models/rubric.py#L112-L124). Free-form per-evaluator config; each evaluator validates its own shape. Used today for `reference_p95_ms` (latency), `reference_usd` + `per_calls` (cost), `golden_db_path` (query_correctness), `required_tokens` (context_window_adequacy).
- **`Tier.active_dimensions()` / `Tier.draft_dimensions()`** at [mmfp/models/rubric.py:148-154](../mmfp/models/rubric.py#L148-L154). Single source of truth for the partition; the engine and the loader both call them rather than re-filtering.
- **Active-weight validation** at [mmfp/models/rubric.py:156-188](../mmfp/models/rubric.py#L156-L188). Active weights sum to `(0, 100]`; zero-active tiers rejected; non-zero draft weights rejected.
- **Active-weight normalisation in aggregation** at [mmfp/models/matrix_run.py](../mmfp/models/matrix_run.py) — `scores_for_tier(tier_id, tier=None)` normalises by the per-tier active-weight total so sparse-active tiers (e.g. Tier 3's 20% coverage) still produce 0–100 weighted scores.
- **`Candidate.context_window: int`** at [mmfp/models/candidate.py:99-103](../mmfp/models/candidate.py#L99-L103). Required per-candidate (no default); sourced from the upstream model's published spec rather than inferred from deployment name.
- **Engine context wiring** at [mmfp/engine/matrix.py:559-610](../mmfp/engine/matrix.py#L559-L610). The new `_evaluate_traced` populates `eval_context` with `evaluator_config`, `latency_ms`, `candidate_context_window`, and `cost_usd = Decimal("0")` before each evaluator dispatch, then wraps the call in a LangSmith `traceable` with run/tier/dimension/candidate/example/evaluator metadata and tags. Coverage validation and per-cell dispatch iterate `tier.active_dimensions()` — drafts are never reached.

The `cost_usd = 0` placeholder is the load-bearing engine-level acknowledgement that cost discrimination is currently flat (see §8).

## 4. API surface additions

Two new endpoints, plus one shape addition to an existing endpoint:

- **`PUT /api/products/{product}/rubric`** (MLI-273) at [mmfp/api/rubric_write.py](../mmfp/api/rubric_write.py). Single steward path for rubric edits. Mounts under the existing API root; `PUT` added to the CORS `allow_methods` list in `main.py`. Request body shape and the steward-identity / 409 handshake are documented in the module docstring. 9 router-level tests against a real tmp git repo at [mmfp/api/tests/test_rubric_write.py](../mmfp/api/tests/test_rubric_write.py).

- **`GET /api/products/{product}/candidates/{deployment}`** (existing endpoint from MLI-184, extended by MLI-274) now inlines `rubric: RubricView` in the response. `RubricView` is **narrower than `Rubric`** — it drops `evaluator`, `evaluator_config`, judge config, gates, and thresholds; preserves declaration order so the modal renders active and draft dimensions in YAML order. The projection helper `_rubric_view(rubric)` lives at [mmfp/api/candidate_detail.py:163-195](../mmfp/api/candidate_detail.py#L163-L195). Loader dependency is `get_rubric_loader()` at [mmfp/api/candidate_detail.py:142-160](../mmfp/api/candidate_detail.py#L142-L160), sharing `MMFP_PRODUCTS_DIR` resolution with `scoreboard.py` and `rubric_write.py`.

- The rubric-write endpoint and the candidate-detail rubric-inlining are coupled: `rubric.version` from the detail response is the same value the Slice 4 Editor will pass back as `expected_version` to the write endpoint. Inlining here means the Editor never needs a separate `GET /rubric` to seed its concurrency handshake.

## 5. UI changes

New surfaces and refinements; all under [ui/](../ui/):

- **Scorecard** at [ui/components/Scorecard.tsx](../ui/components/Scorecard.tsx) — adds a Vendor column (`data-testid="vendor-badge"`, neutral pill, em-dash for unknown prefix) and a Trend column (`data-testid="candidate-sparkline"`, 60×20 SVG) per row. `trends` prop threaded from `TierCard` lets each row resolve its own series from the per-tier `trends.candidates[]` payload; the parsing reverses points to oldest-left so the row reads left-to-right consistent with `TrendStrip`. Reasoning-family candidates' sparklines render in `--orange`; chat-family in `--neutral-5`.
- **Vendor inference** at [ui/lib/vendor.ts](../ui/lib/vendor.ts) — prefix table mapping `gpt-`, `o4-` → OpenAI; `llama-` → Meta; `mistral-` → Mistral; `kimi-` → Moonshot; `phi-` → Microsoft; `claude-`/`opus-`/`sonnet-`/`haiku-` → Anthropic; `gemini-` → Google. Case-insensitive; unknown prefix returns `null` → UI shows em-dash. Frontend-only; backend has no `vendor` field.
- **CandidateDetail** at [ui/components/CandidateDetail.tsx](../ui/components/CandidateDetail.tsx) — replaces the bar visualisation with a four-column rubric-weight-aware table iterating the inlined rubric (not the per_dimension dict). `DimensionRow` renders active dimensions at full opacity and draft dimensions de-emphasised with a "Draft — activates in Slice 6" label. Per-row `data-testid="dimension-row"`; per-weight `data-testid="dim-weight-<id>"` showing the formatted percentage. Header carries the vendor badge and a candidate-level sparkline of tier-history weighted scores; conditional `base_model` line below the deployment ID when the wire field is present.
- **TierCard** at [ui/components/TierCard.tsx](../ui/components/TierCard.tsx) — left-edge accent rule (`data-testid="tier-accent-<tier>"`) and a compact TX pill (`tier-pill-<tier>`) in the header. Tier 1 pill uses neutral-1 ink (yellow accent + white text fails contrast); Tier 2 and Tier 3 keep white ink. Threads `trends` prop to `Scorecard` so per-row sparklines share the page-level fetch.
- **Wire/parsed type extensions** at [ui/lib/scoreboard.ts](../ui/lib/scoreboard.ts) — adds optional `base_model?: string | null` on the candidate-detail types (parse boundary normalises `undefined → null`) and new `WireRubric` / `Rubric` types with `weight` converted from Decimal string to number at the parse boundary (MLI-175 pattern).

## 6. Rubric YAML state

The v0.1 reference-aligned rubric that landed in MLI-272 lives at [products/mli/rubric.yaml](../products/mli/rubric.yaml). `schema_version: v1`, `version: v0.1`.

### Tier 1 — Classification & Routing (`single_turn`, 5 active, 0 draft, 100% active)

| Dimension | Weight | Status | Method | Direction | Evaluator |
|---|---:|---|---|---|---|
| `classification_accuracy` | 35 | active | deterministic | higher_is_better | `regex_match` |
| `structured_output_parse_rate` | 25 | active | deterministic | higher_is_better | `json_schema` |
| `latency_p95` | 20 | active | metric | lower_is_better | `latency_p95` (ref 2000ms) |
| `cost_per_1000_classifications` | 15 | active | metric | lower_is_better | `cost_per_call` (ref $0.005, per 1000) |
| `confidence_calibration` | 5 | active | deterministic | higher_is_better | `confidence_calibration` |

### Tier 2 — Structured Generation & Tool Use (`multi_turn`, 5 active, 2 draft, 80% active)

| Dimension | Weight | Status | Method | Direction | Evaluator |
|---|---:|---|---|---|---|
| `query_correctness` | 30 | active | deterministic | higher_is_better | `query_correctness` (golden DB) |
| `structured_output_reliability` | 20 | active | deterministic | higher_is_better | `structured_output_reliability` |
| `tool_use_fidelity` | 0 | draft | composite | higher_is_better | `tool_use_fidelity` |
| `cost_per_completed_query` | 15 | active | metric | lower_is_better | `cost_per_call` (ref $0.02, per 1) |
| `latency_p95` | 10 | active | metric | lower_is_better | `latency_p95` (ref 5000ms) |
| `context_window_adequacy` | 5 | active | deterministic | higher_is_better | `context_window_adequacy` (req 8000) |
| `fine_tuneability_signal` | 0 | draft | qualitative | higher_is_better | `fine_tuneability_signal` |

### Tier 3 — Synthesis & Client-Facing Reasoning (`multi_turn`, 2 active, 5 draft, 20% active)

| Dimension | Weight | Status | Method | Direction | Evaluator |
|---|---:|---|---|---|---|
| `synthesis_quality` | 0 | draft | llm_judge | higher_is_better | `llm_judge_synthesis_quality` |
| `factual_faithfulness` | 0 | draft | llm_judge | higher_is_better | `llm_judge_factual_faithfulness` |
| `multi_turn_trajectory_coherence` | 0 | draft | composite | higher_is_better | `multi_turn_trajectory_coherence` |
| `tool_use_fidelity` | 0 | draft | composite | higher_is_better | `tool_use_fidelity` |
| `latency_p95` | 10 | active | metric | lower_is_better | `latency_p95` (ref 10000ms) |
| `cost_per_completed_interaction` | 10 | active | metric | lower_is_better | `cost_per_call` (ref $0.05, per 1) |
| `ethical_wall_safety` | 0 | draft | composite | higher_is_better | `ethical_wall_safety` |

`mode: multi_turn` on Tier 2 and Tier 3 is documentary in v0.1 — the matrix engine treats `mode` as metadata; the binding ABC is still sync / single-prompt. The five gates (`gate.compliance.soc2`, `gate.residency.azure_hostable`, `gate.retention.zero_option`, `gate.licence.commercial_use`, `gate.tool_use.supported`) are unchanged. The `judge:` block carries `claude-sonnet-4-5` / `provider: anthropic` / `version_pin: "2025-10-01"` — preserved unchanged from the prior rubric; the **Anthropic vs Azure AI Foundry decision is open** and called out as a Slice 6 architectural-input in the MLI-208 architectural-reality comment (see §11).

Active-weight sums: Tier 1 = 100, Tier 2 = 80, Tier 3 = 20. The matrix engine normalises against the per-tier active total (§3) so Tier 3 still produces 0–100 scores from its sparse coverage.

## 7. Datasets and golden DBs

[products/mli/datasets/](../products/mli/datasets/) layout after MLI-272:

- `tier_1.jsonl` — 10 examples, rewritten in MLI-272. Prompts elicit `{"label": "<value>", "confidence": <0..1>}` JSON so the engine's one-binding-call-per-example architecture (MLI-258) supports all five active Tier-1 evaluators on the same response. `regex_match` on `classification_accuracy` matches the expected label inside the JSON envelope — a v0.1 expedient; the reference method is "exact match" and a label-extracting evaluator will land in Slice 6.
- `tier_2.jsonl` — 10 examples, rewritten in MLI-272. Prompts elicit raw SQL (no markdown fences). `expected.rows` carries the executed-against-golden-DB ground truth; `expected.schemas` carries a tool-call schema kept for future structured-output evaluation. Schema: `matters(id, client, practice, opened_on)` joined to `documents(id, matter_id, kind, pages)` — small legal-domain shape.
- `tier_3.jsonl` — 5 examples, **unchanged** from before Slice 3.5.
- `golden_dbs/query_correctness_v0.sql` — new. Text-script form (not committed `.sqlite` binary) so diffs are reviewable in PRs. 5 matters, 10 documents. Loaded into SQLite `:memory:` per evaluation under a SELECT-only authorizer; sub-millisecond load cost at this scale.
- `golden_dbs/README.md` — new. Documents the harness contract and the SQLite dialect constraint (candidate SQL written for ANSI-only or Postgres-only syntax may fail here even when "correct" against a different target). Path is wired from the rubric YAML's `evaluator_config.golden_db_path`.

## 8. Known fidelity gaps

Tracked in [products/mli/KNOWN_GAPS.md](../products/mli/KNOWN_GAPS.md) and reproduced here as the audit ground-truth.

**Three uniform / non-discriminating dimensions:**

- **`cost_per_call` (Tier 1 / Tier 2 / Tier 3)** — the Azure Foundry binding does not emit `cost_usd` today. The engine populates `context["cost_usd"] = Decimal("0")` defensively so the evaluator doesn't crash, but `min(reference_usd / 0, 1) = 1.0` for every candidate. Result: every candidate scores 100 on every cost dimension; the dimension participates in the weighted aggregate without discriminating. Closes when a cost sensor or pricing-table lookup lands on `BindingResponse` (architectural shape open: sensor vs binding-extension vs Foundry usage API).
- **`structured_output_reliability` (Tier 2)** — `status: active` per the v0.1 reference, but the Tier 2 prompts elicit raw SQL (so `query_correctness` can execute it). Raw SQL is not a JSON tool-call array, so the JSON-decode path fails for every candidate → uniform 0. Closes when the binding grows multi-turn / tool-call output, or a sibling Tier-2 dataset adds tool-call-shaped examples scored only by this dimension.
- **`context_window_adequacy` (Tier 2)** — active, `required_tokens: 8000`. Every Tier 2 candidate in the current slate has a context window of at least 128k tokens, so the dimension uniformly passes (100) and doesn't discriminate. Closes when real MLI prompt shapes land (Slice 6 prompt authoring) and the steward sets `required_tokens` from a measured budget rather than a ballpark.

**Deferred evaluator families** (Tier 3 mostly, plus two Tier 2 drafts):

- **LLM-judge family** — `synthesis_quality`, `factual_faithfulness` (both Tier 3). Pending Slice 6 (MLI-219+) for the plugin + calibration tooling. The `judge:` block in `rubric.yaml` is documentary until then; `KNOWN_GAPS.md` tracks the judge-runtime gap.
- **Composite family** — `multi_turn_trajectory_coherence`, `tool_use_fidelity` (Tier 2 + Tier 3), `ethical_wall_safety`. Composite evaluators (right-tool / correct-arguments / call-order / error-recovery type aggregation) don't ship in this slice.
- **Qualitative family** — `fine_tuneability_signal` (Tier 2). Steward-assessed; ships when steward-input UI lands.

**Binding-side gaps:**

- **Multi-turn binding** — `mode: multi_turn` on Tier 2/3 is documentary; the binding ABC is sync / single-prompt today (MLI-258). Multi-turn / tool-call-shaped prompts require binding broadening, and the `structured_output_reliability` gap above is coupled to this.

**Judge-provider decision is open:**

- The `rubric.yaml` `judge.provider` value is `anthropic`; the v0.1 reference document at Confluence 218628525 names Azure AI Foundry. Implications cross-cut data residency (Azure UK South vs Anthropic API), billing, latency, and calibration-set portability. Called out on MLI-208 as a Slice 6 architectural-input. The current value is **preserved as-is** — not endorsed.

**Eligibility-gate alignment** is unchanged from before Slice 3.5. The five gates in `rubric.yaml`'s `gates:` block (`gate.compliance.soc2`, `gate.residency.azure_hostable`, `gate.retention.zero_option`, `gate.licence.commercial_use`, `gate.tool_use.supported`) carry empty or unchanged `applies_to_tiers`. The MLI-199 architectural-reality comment notes that with Tier 1's 5-active dimensions now producing more discriminating composite scores, the `Rubric.thresholds` values (75/70/60 with 3-point tiebreak band) may actually bind for the first time after the next baseline-matrix run — calibration is the open question.

**Online drift detection** — out of scope for Slice 3.5 (and Slice 3). The deployed Scoreboard's drift banner is still absent; drift signals are a downstream concept the platform doesn't produce yet. The prototype's banner remains aspirational. No change from the Slice 3 audit.

**Datasets remain seed-sized** — Tier 1 ~10, Tier 2 ~10, Tier 3 ~5. Enough to show the matrix engine producing evidence; not production-scale. Closes when the Slice 6 Curator (MLI-219+) lands.

## 9. Architectural-input trail (MLI-267)

Six architectural-input comments posted on MLI-267 by Slice 3.5 sub-tasks. Listed chronologically with comment IDs for cross-reference; all authored by Wayne Palmer on 2026-05-16.

- **31804 — Non-zero draft weights (from MLI-269).** *Forbid non-zero draft weights.* Keeps "non-zero weight always contributes" as the single rule; activation is always a re-balance to 100 so documentary value is small; the YAML can't grow a "this 25 doesn't count" footgun. MLI-269 landed the forbid rule; MLI-272 writes `weight: 0` on every draft dimension.
- **31806 — Metric evaluator naming + reference-value config location (from MLI-270).** *Single class per metric, config-driven (`per_calls` scalar on `cost_per_call`, not separate classes); reference value lives on `Dimension.evaluator_config: dict | None` (not closed `Dimension.reference_*` fields, not per-example `expected`).* Closed Dimension fields can't accommodate latency vs cost vs future tokens/sec shapes; reference is per-dimension not per-example. MLI-270 shipped option-1 + option-A; MLI-272 landed the engine context wiring for `evaluator_config` / `latency_ms` / `cost_usd`.
- **31808 — SQL dialect of the `query_correctness` golden DB (from MLI-271).** *SQLite for v0.1; revisit at v0.2.* Zero dependency footprint, the v0.1 dataset doesn't exercise SQLite's permissive edges, the dimension grades capability not engine-fidelity, switching later is a config swap (`evaluator_config['golden_db_path']`) or a sibling evaluator. MLI-271 shipped SQLite + SELECT-only authorizer.
- **31811 — Steward identity placeholder + concurrency posture (from MLI-273).** *Trusted `X-Steward-Identity` HTTP header with placeholder `Unknown Steward <steward@unknown.local>` (exposed as `mmfp.api.rubric_write.PLACEHOLDER_STEWARD`); 409 with `current_version` on `expected_version` mismatch (no server-side merge).* The dev UI populates the header from its auth state (BasicAuth today, Entra SSO later) without an API change; per-field rubric merges have no CRDT-free meaning so deferring merge policy to the editor UI is cheaper than picking the wrong CRDT now. Both shipped in MLI-273; the version-string format (`^v\d+\.\d+$`, server-owned, auto-bumps minor) is settled.
- **31813 — Rubric inclusion shape for candidate-detail (from MLI-274).** *Inline the rubric in the candidate-detail response (not a separate `GET /rubric`).* Payload at v0.1 scale is ~2 KB, one round-trip avoids two loading states, rubric and detail are naturally co-fetched, and `rubric_version` already lives next to `latest_run` so colocation keeps version and definition in one envelope. A standalone `GET /rubric` is cheap to add later when a non-candidate entry point lands. MLI-274 shipped inlined.
- **31815 — Vendor mapping convention (from MLI-275).** *Frontend-only inference from `candidate_id` prefix via `ui/lib/vendor.ts`.* The candidate model has no `vendor` field; a small prefix table covers the v0.1 slate plus future-proofing (`claude-*` / `gemini-*` / `o4-*`); unknown prefix renders an em-dash. Vendor is a display-layer concern (no evaluator reads it, no audit cites it). Promoting to an explicit `Candidate.vendor` field happens the day Slice 4's Editor wants steward-editable labels. Adjacent decision: `base_model?: string | null` added to the UI wire/parse types only; backend serialisation deferred until the first custom-trained candidate ships.

The task brief listed five expected IDs (31804/31806/31808/31811/31813). The sixth — 31815 — was posted from MLI-275 in the same architectural-input shape and is included for completeness.

## 10. Operational follow-ups

Close-out fixes that landed on `main` after the slice's sub-tasks but before this audit was written. None of them are sub-task work; they're operational hygiene worth recording because they touch CI / TestRail and are likely to confuse a future agent who finds the commits unattached to a Jira ticket.

- **Ruff lint fix on MLI-274** — [`462056a`](https://github.com/morae-product-engineering/model-fitness/commit/462056a) (`chore: ruff --fix import order (MLI-274 follow-up)`). MLI-274 (PR #57) merged with a red `Run Ruff` step; this is the safe auto-fix landed directly on `main`. No semantic change to `mmfp/api/candidate_detail.py`.
- **TestRail suite wiring for Slice 03 / 03P5 / 04** — [`7fbd1f5`](https://github.com/morae-product-engineering/model-fitness/commit/7fbd1f5) (`chore: wire TestRail suites for Slice 03, 03P5, 04`). Adds three new `TESTRAIL_SUITE_*` env entries to `.github/workflows/ci.yml` and extends the reporter's slice-derivation regex at [tests/reporters/testrail-reporter.ts:216](../tests/reporters/testrail-reporter.ts#L216) to recognise the interstitial NpM form (`slice-3p5` → `SLICE_03P5`) so it no longer collides with the integer slice (`slice-03` → `SLICE_03`). 61 new reporter-unit tests cover the regex.
- **Slice-03 stale `dimension-row` count assertion** — [`f881330`](https://github.com/morae-product-engineering/model-fitness/commit/f881330) (`chore: update slice-03 dimension-row baseline for MLI-272 rubric growth (2 → 7)`). MLI-272's rubric rewrite grew Tier 2 from 2 to 7 dimensions, breaking the Slice 3 trends spec's hard-coded dimension-row count. Single-line fix in `tests/e2e/slice-03-trends.spec.ts`.
- **Baseline-matrix workflow** — `.github/workflows/baseline-matrix.yml` is enabled via `workflow_dispatch` (manual seed always available) and a scheduled trigger; per-PR runs are deliberately disabled (a) because the workflow is heavy, and (b) per MLI-180 close-out the seeder is "seed-as-canonical with `baseline-matrix.yml` disabled" — re-enable triggers are named on that trail. No change in Slice 3.5; the workflow remains the manually-dispatched path to re-run the deployed dev matrix when seeded data needs refreshing.

## 11. What this means for Slice 4, 5, 6

Three architectural-reality comments were posted on the downstream Slice tickets on 2026-05-16 to capture the new prerequisites. Each is linked from its parent issue's comment thread.

### Slice 4 — MLI-190 (Editor) inherits:

- **The Weights API.** `PUT /api/products/{p}/rubric` ships with the `expected_version` handshake (409 carries `current_version`) and Git-as-audit-trail. The deferred items the Editor must know about: `git push` to origin is **not** wired (the commit is local), deployment plumbing needs a configured git committer identity, and CLI parity (`mmfp rubric set`) is a follow-up.
- **The rubric-weight-aware CandidateDetail surface and the `Dimension.evaluator_config` / status partition.** The Editor lifts the four-column Dimension / Weight / Score / w×s breakdown directly. `Dimension.evaluator_config` is the path for adding new evaluator-specific config without churning the model.
- **A corrected acceptance test.** The 2026-05-15 ranking-flip-unsatisfiable analysis on MLI-190 is **moot** — it was against the MLI-187 retroactive two-dimension Tier 3, which MLI-272 reversed (Tier 3 = 2 active + 5 draft; Tier 1 = 5 active). The Editor's acceptance test must pick two demonstrably-discriminating active dimensions after the next live baseline-matrix run; Tier 1 is the cleanest canvas. See the MLI-190 architectural-reality comment id **31817**.

### Slice 5 — MLI-199 (Promote) inherits:

- **The Git-as-audit-trail precedent.** MLI-273's actor → author / timestamp → committer-date / version delta + note → message pattern is now a viable option (Option C) for promotion rationale storage, alongside the original Option A (rationale on candidate row) and Option B (separate `status_change` table). Trade-off: candidate-status changes are per-row and frequent, vs MLI-273's single-file rubric — Git fits the rubric case more naturally than it fits per-row. The choice is open and surfacing it as the first architectural-input before sub-task drafts is on the Slice-5 plan.
- **Eligibility-gate decisions unchanged.** The three structural decisions Slice 5 must make (global vs per-tier `Candidate.status`, rationale storage shape, eligibility gates) are still open and load-bearing. Slice 3.5 didn't touch them. The `Rubric.thresholds` values (75/70/60, tiebreak 3) may calibrate or bind for the first time once the post-MLI-272 baseline-matrix runs.
- **The `Modal` primitive is still not ported** — MLI-275's visual pass extended CandidateDetail but didn't introduce a generic Modal. Slice 5 still needs to port it from `ui/prototype/primitives.jsx`. See the MLI-199 architectural-reality comment id **31818**.

### Slice 6 — MLI-208 (Datasets) inherits:

- **The draft dimensions to activate.** Tier 3 drafts (`synthesis_quality`, `factual_faithfulness`, `multi_turn_trajectory_coherence`, `tool_use_fidelity`, `ethical_wall_safety`) and Tier 2 drafts (`tool_use_fidelity`, `fine_tuneability_signal`) already exist in the YAML with `status: draft, weight: 0`. **Slice 6's job is to activate them**, not to add new ones. Activation is a structural rubric change (`status` flip + weight reassignment so the active-weight sum returns to 100), coupled to the relevant evaluator family shipping. Whether activation goes through `PUT /api/products/{p}/rubric` or a separate engine-side migration is an open architectural-input for Slice 6.
- **The judge-provider decision is open.** `judge.provider: anthropic` in the YAML vs the v0.1 reference document's Azure AI Foundry — Slice 6 must call this deliberately. The LLM-judge evaluator output schema is also still open.
- **The Slice 3.5 architectural inputs that matter most for Slice 6:** **31804** (draft weights — directly relevant to activation), **31806** (Metric evaluator naming + `evaluator_config` shape — relevant for LLM-judge `evaluator_config`), and **31811** (actor identity + 409 — relevant if activation goes through the rubric-write endpoint). See the MLI-208 architectural-reality comment id **31819**.

The reading order in each comment names this audit as a deliberate part of the briefing for the next chat window. That is the role this file is supposed to play.
