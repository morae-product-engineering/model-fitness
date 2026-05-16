# MLI rubric / slate — known gaps (v0.1)

Living list of intentional gaps in the MLI configuration. Each gap names the
trigger that would close it. New gaps land here when they're noticed; closed
gaps are removed (the git history holds the record).

## Anthropic family absent from the slate

The 10 dev-account Foundry deployments do not include any Anthropic Claude
deployment. Tier 3 synthesis in particular would benefit from a Claude-class
model alongside GPT-4o and Kimi-K2.6.

* **Why not now:** Foundry capacity for Anthropic in `mmfp-dev-models` was
  unavailable when the slate was provisioned (MLI-166).
* **Revisit trigger:** Foundry surfaces an Anthropic deployment in the
  region, OR direct Anthropic API procurement is approved and the binding
  plugin grows a second provider.
* **Owner:** Wayne Palmer.

## Gemini family absent from the slate

No Google Gemini deployment for the same Tier 3 reason as Anthropic.

* **Why not now:** Not in the procurement scope at slate provisioning.
* **Revisit trigger:** Vertex AI / Gemini procurement decision; or Foundry
  begins offering a Gemini-equivalent serverless route.
* **Owner:** Wayne Palmer.

## Tier 3 LLM judge not yet running

The rubric carries a `judge:` block (`claude-sonnet-4-5`) and Tier 3's five
inferential / composite dimensions (`synthesis_quality`,
`factual_faithfulness`, `multi_turn_trajectory_coherence`,
`tool_use_fidelity`, `ethical_wall_safety`) are declared with
`status: draft, weight: 0`. The matrix engine doesn't dispatch to draft
dimensions, so Tier 3 v0.1 scoring relies on the two envelope-only active
dimensions (`latency_p95`, `cost_per_completed_interaction`).

* **Why not now:** The LLM-judge plugin and calibration tooling are Slice 6
  scope (MLI-219+). The judge-provider decision (Anthropic API vs Azure AI
  Foundry) is also out of scope for v0.1 and tracked separately — the
  `judge.provider` value in `rubric.yaml` is preserved as-is.
* **Revisit trigger:** Slice 6 ships the LLM-judge evaluator family; the
  draft dimensions flip to `status: active` with their reference weights;
  `products/mli/datasets/judge_calibration.jsonl` is populated.
* **Owner:** TBD with Slice 6 lead.

## `cost_usd` not yet emitted by the binding

The Tier 1, Tier 2 and Tier 3 cost dimensions (`cost_per_1000_classifications`,
`cost_per_completed_query`, `cost_per_completed_interaction`) call the
`cost_per_call` evaluator, which expects `context['cost_usd']`. The Azure
Foundry binding doesn't compute cost from the response envelope today, and
no sensor or pricing-table lookup is in place. The matrix engine populates
`context['cost_usd'] = Decimal("0")` defensively so the evaluator doesn't
crash — but the consequence is that every candidate scores 100 on cost
(`0 <= reference_usd` → `min(reference/cost, 1) = 1.0`), and the cost
dimensions don't discriminate.

* **Why not now:** Adding a cost sensor or extending the binding ABC to
  emit cost is a scope expansion beyond rubric alignment. The architectural
  question (sensor vs binding-extension vs Foundry usage API) hasn't been
  resolved.
* **Revisit trigger:** Separate ticket scoped to cost emission. Likely a
  `cost_usd` field on `BindingResponse` populated from a pricing table
  keyed on `(provider, deployment, prompt_tokens, completion_tokens)`.
* **Owner:** TBD; flag on MLI-267 follow-ups.

## `structured_output_reliability` uniform-fail in Tier 2

The Tier 2 `structured_output_reliability` dimension is `status: active`
per the v0.1 reference, but the dataset's prompts elicit a single raw SQL
statement (so `query_correctness` can execute it). Raw SQL is not a JSON
tool-call array, so the evaluator's JSON-decode step fails for every
candidate and the dimension uniformly scores 0. The score still
participates in the weighted aggregate; the dimension just doesn't
discriminate today.

* **Why not now:** Eliciting multi-turn tool-call trajectories from
  single-prompt-sync candidates requires a multi-turn binding path
  (`mode: multi_turn` is documentary in v0.1 — see the MLI-272 sub-task).
* **Revisit trigger:** The binding plugin gains multi-turn / tool-call
  output support, OR a sibling Tier-2 dataset adds tool-call-shaped
  examples scored only by `structured_output_reliability`.
* **Owner:** TBD with the binding-broadening sub-task.

## `context_window_adequacy` uniform-pass in Tier 2

The Tier 2 `context_window_adequacy` dimension is active with
`required_tokens: 8000`. Every Tier 2 candidate in the current slate has a
context window of at least 128k tokens, so the dimension uniformly passes
(score 100) and doesn't discriminate.

* **Why not now:** A more discriminating threshold (or a per-candidate
  required-tokens override) would need a real measurement of MLI
  schema-aware prompts — not just a stewards' guess.
* **Revisit trigger:** Real MLI prompt-shapes land (Slice 6 prompt
  authoring) — the steward sets `required_tokens` from a measured budget
  rather than a ballpark.
* **Owner:** TBD with Slice 6 prompt-authoring sub-task.

## Datasets are seed-sized only

Tier 1 ~10, Tier 2 ~10, Tier 3 ~5. Enough to show the matrix engine
producing evidence; nowhere near a production-scale evaluation set.

* **Revisit trigger:** Slice 6 introduces the Curator (MLI-219+), which is
  where MLI's golden datasets grow under controlled labelling.
