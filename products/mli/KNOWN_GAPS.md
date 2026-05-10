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

The rubric carries a `judge:` block (`claude-sonnet-4-5`) but the matrix
engine does not invoke an LLM judge in v0.1 — Tier 3 dimensions
(`citation_presence`, `structural_completeness`) use `regex_match` and
`json_schema` as deterministic stand-ins.

* **Why not now:** The LLM-judge plugin and calibration tooling are Slice 6
  scope (MLI-219+). Pinning the judge model in the rubric now keeps the
  contract stable so Slice 6 only adds the implementation, not the
  configuration shape.
* **Revisit trigger:** Slice 6 ships the judge plugin; the
  `products/mli/datasets/judge_calibration.jsonl` file is populated; Tier 3
  dimensions move from `method: deterministic` (the active behaviour) to
  `method: llm_judge` and rebind their evaluator references.
* **Owner:** TBD with Slice 6 lead.

## Tier 2 single-evaluator-per-dimension

Two dimensions in Tier 2 (`schema_validity`, `format_compliance`) instead of
the three originally sketched. Multiple dimensions sharing the same
evaluator would all read the same `expected` slot per example and produce
identical scores — a v0.1 limitation, not a long-term design choice.

* **Revisit trigger:** Per-dimension expected payloads land (likely with
  the LLM judge in Slice 6) — at that point Tier 2 can broaden to include
  `field_accuracy` or other dimensions without scoring duplication.

## Datasets are seed-sized only

Tier 1 ~10, Tier 2 ~10, Tier 3 ~5. Enough to show the matrix engine
producing evidence; nowhere near a production-scale evaluation set.

* **Revisit trigger:** Slice 6 introduces the Curator (MLI-219+), which is
  where MLI's golden datasets grow under controlled labelling.
