// Server component — renders one tier panel with its candidate scorecard.
// Props are the parsed types from ui/lib/scoreboard.ts; no parseFloat here.
//
// MLI-275 — adds a left-edge tier accent rule and a compact TX pill in the
// header (T1=yellow, T2=orange, T3=warm-red), lifted from
// ui/prototype/primitives.jsx:82-108 (TierPill / TierRule) and
// ui/prototype/data.jsx:38-50 (tier.accent palette).

import { Candidate, TierId, TierMeta, Trends } from "@/lib/scoreboard";
import PortfolioSummary from "./PortfolioSummary";
import Scorecard from "./Scorecard";
import TrendStrip from "./TrendStrip";

const TIER_ACCENT: Record<TierId, { code: string; color: string }> = {
  tier_1: { code: "T1", color: "var(--yellow)" },
  tier_2: { code: "T2", color: "var(--orange)" },
  tier_3: { code: "T3", color: "var(--warm-red)" },
};

interface TierCardProps {
  tierId: TierId;
  meta: TierMeta;
  candidates: Candidate[];
  trends?: Trends;
  // Threaded to the Scorecard so a row click can open the candidate-detail
  // modal (MLI-187). When omitted, rows render without drill-down — handy
  // for unit tests that exercise the table alone.
  product?: string;
  apiBaseUrl?: string;
}

export default function TierCard({
  tierId,
  meta,
  candidates,
  trends,
  product,
  apiBaseUrl,
}: TierCardProps) {
  // Defensive: the scoreboard endpoint already sorts by weighted_score desc
  // (mmfp/models/matrix_run.py:186), but TierCard owns its render order so a
  // future caller passing an arbitrary Candidate[] still gets a ranked view.
  // Stable across equal scores — Array.prototype.sort is stable since ES2019.
  const ranked = [...candidates].sort(
    (a, b) => b.weighted_score - a.weighted_score
  );

  const accent = TIER_ACCENT[tierId];

  return (
    <div
      data-testid={`tier-card-${tierId}`}
      className="bg-white border border-neutral-11 rounded-lg overflow-hidden shadow-sm flex"
    >
      {/* Tier accent rule — left-edge colour strip from the prototype. */}
      <div
        data-testid={`tier-accent-${tierId}`}
        aria-hidden="true"
        className="w-1 flex-shrink-0"
        style={{ background: accent.color }}
      />
      <div className="flex-1 min-w-0">
      {/* Card header */}
      <div className="px-5 py-4 border-b border-neutral-11">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex items-start gap-3">
            <span
              data-testid={`tier-pill-${tierId}`}
              className="inline-flex items-center justify-center text-[11px] font-bold tracking-wide rounded px-1.5 py-0.5 font-mono text-white flex-shrink-0 mt-0.5"
              style={{
                background: accent.color,
                // T1 is yellow which lacks contrast against white text; flip to
                // neutral-1 ink for T1 only.
                color: tierId === "tier_1" ? "var(--neutral-1)" : "#fff",
              }}
            >
              {accent.code}
            </span>
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-neutral-1">
                {meta.title}
              </h2>
              <p className="text-xs text-neutral-6 mt-0.5">{meta.subtitle}</p>
              {meta.note && (
                <p className="text-xs text-neutral-6 mt-1 italic">{meta.note}</p>
              )}
            </div>
          </div>
          <span className="flex-shrink-0 text-xs text-neutral-6 font-mono whitespace-nowrap">
            {ranked.length} candidate{ranked.length !== 1 ? "s" : ""}
          </span>
        </div>
      </div>

      {/* Portfolio summary — Primary / Fallback / Under evaluation / Rejected
          four-cell row above the candidate table (MLI-263, audit Option C). */}
      {ranked.length > 0 && (
        <PortfolioSummary
          tierId={tierId}
          candidates={ranked}
          trends={trends}
        />
      )}

      {/* Card body */}
      <div>
        {ranked.length === 0 ? (
          <p className="px-5 py-4 text-sm text-neutral-6">
            No scored candidates
          </p>
        ) : (
          <Scorecard
            tierId={tierId}
            candidates={ranked}
            trends={trends}
            product={product}
            apiBaseUrl={apiBaseUrl}
          />
        )}
      </div>

      {/* Trend strip — only when trends are available for this tier. The
          page may omit `trends` if the trends endpoint failed; the scorecard
          still renders without it. */}
      {trends && (
        <TrendStrip
          tierId={tierId}
          runs={trends.runs}
          candidates={rankTrendCandidates(ranked, trends.candidates)}
        />
      )}
      </div>
    </div>
  );
}

// TierCard owns the ranking contract (MLI-185 trail). Re-project the trends
// candidates into the same order as the ranked scoreboard candidates so the
// TrendStrip renders top-down in score order. Candidates present in the
// scoreboard but missing from trends (no data in the window) are dropped from
// the strip — the trends endpoint already omits them server-side.
function rankTrendCandidates(
  ranked: Candidate[],
  trendCandidates: Trends["candidates"],
): Trends["candidates"] {
  const byId = new Map(trendCandidates.map((c) => [c.candidate_id, c]));
  return ranked.flatMap((c) => {
    const t = byId.get(c.candidate_id);
    return t ? [t] : [];
  });
}
