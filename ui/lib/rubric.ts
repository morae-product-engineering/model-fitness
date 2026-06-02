// Types and helpers for the rubric read/write/preview endpoints consumed by
// the Editor (MLI-195). Wire types match the API JSON exactly; parsed types
// convert Decimal strings to numbers at the parse boundary.
//
// RawRubric keeps the full rubric dict verbatim — the Editor posts this dict
// straight back to preview-impact and PUT without re-serialising field-by-field
// (which would drop evaluator_config, gates, judge, etc.).
//
// TierId is imported from ./scoreboard to avoid redefining it here.

import type { TierId } from "./scoreboard";
export type { TierId };

// ---------------------------------------------------------------------------
// Raw rubric types — match the GET /api/products/{product}/rubric response.
// Extra-fields index signature ([k: string]: unknown) preserves any
// rubric fields the type doesn't explicitly name so they survive round-trips.
// ---------------------------------------------------------------------------

export interface RawDimension {
  id: string;
  name: string;
  description: string;
  weight: string | number;
  status: "active" | "draft";
  direction: "higher_is_better" | "lower_is_better";
  method: string;
  evaluator: string;
  evaluator_config?: Record<string, unknown> | null;
  [k: string]: unknown;
}

export interface RawTier {
  id: TierId;
  name: string;
  dimensions: RawDimension[];
  [k: string]: unknown;
}

export interface RawRubric {
  version: string;
  schema_version: string;
  tiers: RawTier[];
  [k: string]: unknown;
}

export interface RubricReadResponse {
  product: string;
  version: string;
  rubric: RawRubric;
}

// ---------------------------------------------------------------------------
// Preview wire / parsed types — match POST /api/products/{product}/rubric/preview-impact
// response models exactly (mmfp/api/rubric_preview.py).
// Decimal values arrive as JSON strings in the wire format.
// ---------------------------------------------------------------------------

export interface WirePreviewCandidateDelta {
  candidate: string;
  score_before: string; // Decimal as string
  score_after: string; // Decimal as string
  rank_before: number;
  rank_after: number;
  coverage_complete: boolean;
}

export interface WirePreviewTier {
  tier_id: TierId;
  candidates: WirePreviewCandidateDelta[];
  normalization_stale_dimensions: string[];
}

export interface WirePreviewResponse {
  product: string;
  run_id: string | null;
  current_version: string;
  candidate_version: string;
  has_run: boolean;
  tiers: WirePreviewTier[];
}

// Parsed types — score_before / score_after converted to number.
export interface PreviewCandidateDelta {
  candidate: string;
  score_before: number;
  score_after: number;
  rank_before: number;
  rank_after: number;
  coverage_complete: boolean;
}

export interface PreviewTier {
  tier_id: TierId;
  candidates: PreviewCandidateDelta[];
  normalization_stale_dimensions: string[];
}

export interface PreviewResponse {
  product: string;
  run_id: string | null;
  current_version: string;
  candidate_version: string;
  has_run: boolean;
  tiers: PreviewTier[];
}

export function parsePreview(raw: WirePreviewResponse): PreviewResponse {
  return {
    ...raw,
    tiers: raw.tiers.map((wt) => ({
      ...wt,
      candidates: wt.candidates.map((wc) => ({
        ...wc,
        score_before: parseFloat(wc.score_before),
        score_after: parseFloat(wc.score_after),
      })),
    })),
  };
}

// ---------------------------------------------------------------------------
// Save types — match PUT /api/products/{product}/rubric request / response
// shapes (mmfp/api/rubric_write.py).
// ---------------------------------------------------------------------------

export interface RubricSaveRequest {
  rubric: RawRubric;
  expected_version: string;
  note?: string;
}

export interface RubricSaveResponse {
  previous_version: string;
  new_version: string;
  // MLI-365: the audit trail moved off git to a durable store; this is the
  // storage name of the immutable audit record (was `commit_sha`).
  audit_ref: string;
}

export interface RubricSaveConflict {
  error: "version_conflict";
  current_version: string;
  expected_version: string;
}

export interface RubricSaveValidationError {
  detail: Array<{ loc: (string | number)[]; msg: string; type: string }>;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Read a dimension's weight as a number regardless of whether the API
 * returned it as a string (Decimal) or a numeric value.
 */
export function dimWeightNumber(dim: RawDimension): number {
  return Number(dim.weight);
}

/**
 * Deep-clone ``base`` and override weights from the ``weights`` map.
 *
 * ``weights`` is keyed as ``"${tier.id}.${dim.id}"`` (e.g.
 * ``"tier_3.latency_p95"``).  Only active dimensions that appear in the map
 * are updated; draft dimensions and unedited dimensions retain their base
 * value.  Every other field (evaluator_config, gates, judge, etc.) is
 * preserved exactly, which is the contract the PUT endpoint requires.
 */
export function buildCandidateRubric(
  base: RawRubric,
  weights: Record<string, number>,
): RawRubric {
  // JSON round-trip deep-clone: safe for the rubric shape (no Date or
  // non-serialisable values) and avoids a structuredClone polyfill dependency.
  const cloned: RawRubric = JSON.parse(JSON.stringify(base));
  for (const tier of cloned.tiers) {
    for (const dim of tier.dimensions) {
      const key = `${tier.id}.${dim.id}`;
      if (Object.prototype.hasOwnProperty.call(weights, key)) {
        dim.weight = weights[key]!;
      }
    }
  }
  return cloned;
}
