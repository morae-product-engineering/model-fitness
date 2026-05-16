// Wire-format types (Decimal values arrive as JSON strings), parsed runtime
// types (Decimal values converted to number), and the single parse boundary.
// Components only see the parsed types; parseFloat is called here, not in JSX.

export type Family = "chat" | "reasoning";
export type Status =
  | "under_evaluation"
  | "approved_primary"
  | "approved_fallback"
  | "rejected";
export type TierId = "tier_1" | "tier_2" | "tier_3";

// Map wire status strings to human-readable labels.
export const STATUS_LABELS: Record<Status, string> = {
  under_evaluation: "Under evaluation",
  approved_primary: "Approved · Primary",
  approved_fallback: "Approved · Fallback",
  rejected: "Rejected",
};

// Tier metadata — titles, subtitles, and optional notes hardcoded per
// architectural decision (6). The API does not return tier names.
export interface TierMeta {
  title: string;
  subtitle: string;
  note?: string;
}

export const TIERS: Record<TierId, TierMeta> = {
  tier_1: {
    title: "Classification & Routing",
    subtitle:
      "Classify legal text or route requests to the right downstream skill",
  },
  tier_2: {
    title: "Structured Generation",
    subtitle:
      "Generate JSON conforming to a schema with format-compliant field values",
  },
  tier_3: {
    title: "Synthesis",
    subtitle:
      "Synthesise a structured legal answer with citations and recommendations",
    note: "v0.1 — deterministic stand-ins for LLM judge (Slice 6)",
  },
};

// ---------------------------------------------------------------------------
// Wire-format types — match the API JSON exactly (Decimals are strings).
// ---------------------------------------------------------------------------

export interface WireCandidate {
  candidate_id: string;
  display_name: string;
  family: Family;
  deployment: string;
  status: Status;
  weighted_score: string;
  per_dimension: Record<string, string>;
}

export interface WireTier {
  tier_id: TierId;
  candidates: WireCandidate[];
}

export interface WireScoreboard {
  product: string;
  run_id: string;
  rubric_version: string;
  started_at: string;
  completed_at: string | null;
  tiers: WireTier[];
}

// ---------------------------------------------------------------------------
// Parsed runtime types — Decimals converted to number.
// ---------------------------------------------------------------------------

export interface Candidate {
  candidate_id: string;
  display_name: string;
  family: Family;
  deployment: string;
  status: Status;
  weighted_score: number;
  per_dimension: Record<string, number>;
}

export interface Tier {
  tier_id: TierId;
  candidates: Candidate[];
}

export interface Scoreboard {
  product: string;
  run_id: string;
  rubric_version: string;
  started_at: string;
  completed_at: string | null;
  tiers: Tier[];
}

// ---------------------------------------------------------------------------
// Parse boundary — call once at the server component boundary.
// ---------------------------------------------------------------------------

export function parseScoreboard(raw: WireScoreboard): Scoreboard {
  return {
    ...raw,
    tiers: raw.tiers.map((wt) => ({
      tier_id: wt.tier_id,
      candidates: wt.candidates.map((wc) => ({
        ...wc,
        weighted_score: parseFloat(wc.weighted_score),
        per_dimension: Object.fromEntries(
          Object.entries(wc.per_dimension).map(([k, v]) => [k, parseFloat(v)])
        ),
      })),
    })),
  };
}

// ---------------------------------------------------------------------------
// Trends wire / parsed types — companion to the trends endpoint (MLI-184).
// ---------------------------------------------------------------------------

export interface WireTrendRun {
  run_id: string;
  rubric_version: string;
  started_at: string;
  completed_at: string | null;
}

export interface WireTrendPoint {
  run_id: string;
  weighted_score: string;
}

export interface WireTrendCandidate {
  candidate_id: string;
  display_name: string;
  family: Family;
  deployment: string;
  status: Status;
  points: WireTrendPoint[];
}

export interface WireTrends {
  product: string;
  tier_id: TierId;
  runs: WireTrendRun[];
  candidates: WireTrendCandidate[];
}

export interface TrendRun {
  run_id: string;
  rubric_version: string;
  started_at: string;
  completed_at: string | null;
}

export interface TrendPoint {
  run_id: string;
  weighted_score: number;
}

export interface TrendCandidate {
  candidate_id: string;
  display_name: string;
  family: Family;
  deployment: string;
  status: Status;
  points: TrendPoint[];
}

export interface Trends {
  product: string;
  tier_id: TierId;
  runs: TrendRun[];
  candidates: TrendCandidate[];
}

export function parseTrends(raw: WireTrends): Trends {
  return {
    ...raw,
    candidates: raw.candidates.map((wc) => ({
      ...wc,
      points: wc.points.map((p) => ({
        run_id: p.run_id,
        weighted_score: parseFloat(p.weighted_score),
      })),
    })),
  };
}

// ---------------------------------------------------------------------------
// Candidate detail wire / parsed types — companion to the candidate-detail
// endpoint (MLI-184).
// ---------------------------------------------------------------------------

export interface WireCandidateTierResult {
  tier_id: TierId;
  weighted_score: string;
  per_dimension: Record<string, string>;
}

export interface WireCandidateLatestRun {
  run_id: string;
  rubric_version: string;
  started_at: string;
  completed_at: string | null;
  per_tier: WireCandidateTierResult[];
}

export interface WireCandidateHistoryEntry {
  run_id: string;
  started_at: string;
  completed_at: string | null;
  per_tier_scores: Record<string, string>;
}

// Rubric inlined in the candidate-detail response (MLI-274). `weight` arrives
// as a Decimal JSON string and is converted to number at the parse boundary.
// `status: "draft"` dimensions are surfaced for de-emphasised rendering; they
// always carry `weight: "0"` per the rubric model's Tier validator.
export type DimensionStatus = "active" | "draft";
export type DimensionMethod =
  | "deterministic"
  | "metric"
  | "llm_judge"
  | "composite"
  | "qualitative";
export type DimensionDirection = "higher_is_better" | "lower_is_better";

export interface WireRubricDimension {
  id: string;
  name: string;
  description: string;
  weight: string;
  status: DimensionStatus;
  method: DimensionMethod;
  direction: DimensionDirection;
}

export interface WireRubricTier {
  tier_id: TierId;
  name: string;
  dimensions: WireRubricDimension[];
}

export interface WireRubric {
  version: string;
  tiers: WireRubricTier[];
}

export interface WireCandidateDetail {
  product: string;
  candidate_id: string;
  display_name: string;
  family: Family;
  deployment: string;
  status: Status;
  tiers: TierId[];
  latest_run: WireCandidateLatestRun | null;
  history: WireCandidateHistoryEntry[];
  rubric: WireRubric;
}

export interface CandidateTierResult {
  tier_id: TierId;
  weighted_score: number;
  per_dimension: Record<string, number>;
}

export interface CandidateLatestRun {
  run_id: string;
  rubric_version: string;
  started_at: string;
  completed_at: string | null;
  per_tier: CandidateTierResult[];
}

export interface CandidateHistoryEntry {
  run_id: string;
  started_at: string;
  completed_at: string | null;
  per_tier_scores: Partial<Record<TierId, number>>;
}

export interface RubricDimension {
  id: string;
  name: string;
  description: string;
  weight: number;
  status: DimensionStatus;
  method: DimensionMethod;
  direction: DimensionDirection;
}

export interface RubricTier {
  tier_id: TierId;
  name: string;
  dimensions: RubricDimension[];
}

export interface Rubric {
  version: string;
  tiers: RubricTier[];
}

export interface CandidateDetail {
  product: string;
  candidate_id: string;
  display_name: string;
  family: Family;
  deployment: string;
  status: Status;
  tiers: TierId[];
  latest_run: CandidateLatestRun | null;
  history: CandidateHistoryEntry[];
  rubric: Rubric;
}

export function parseCandidateDetail(raw: WireCandidateDetail): CandidateDetail {
  return {
    ...raw,
    latest_run: raw.latest_run
      ? {
          ...raw.latest_run,
          per_tier: raw.latest_run.per_tier.map((pt) => ({
            tier_id: pt.tier_id,
            weighted_score: parseFloat(pt.weighted_score),
            per_dimension: Object.fromEntries(
              Object.entries(pt.per_dimension).map(([k, v]) => [k, parseFloat(v)]),
            ),
          })),
        }
      : null,
    history: raw.history.map((h) => ({
      ...h,
      per_tier_scores: Object.fromEntries(
        Object.entries(h.per_tier_scores).map(([k, v]) => [k, parseFloat(v)]),
      ) as Partial<Record<TierId, number>>,
    })),
    rubric: {
      version: raw.rubric.version,
      tiers: raw.rubric.tiers.map((t) => ({
        tier_id: t.tier_id,
        name: t.name,
        dimensions: t.dimensions.map((d) => ({
          ...d,
          weight: parseFloat(d.weight),
        })),
      })),
    },
  };
}
