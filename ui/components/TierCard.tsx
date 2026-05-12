// Server component — renders one tier panel with its candidate scorecard.
// Props are the parsed types from ui/lib/scoreboard.ts; no parseFloat here.

import { Candidate, TierId, TierMeta, Trends } from "@/lib/scoreboard";
import Scorecard from "./Scorecard";
import TrendStrip from "./TrendStrip";

interface TierCardProps {
  tierId: TierId;
  meta: TierMeta;
  candidates: Candidate[];
  trends?: Trends;
}

export default function TierCard({ tierId, meta, candidates, trends }: TierCardProps) {
  // Defensive: the scoreboard endpoint already sorts by weighted_score desc
  // (mmfp/models/matrix_run.py:186), but TierCard owns its render order so a
  // future caller passing an arbitrary Candidate[] still gets a ranked view.
  // Stable across equal scores — Array.prototype.sort is stable since ES2019.
  const ranked = [...candidates].sort(
    (a, b) => b.weighted_score - a.weighted_score
  );

  return (
    <div
      data-testid={`tier-card-${tierId}`}
      className="bg-white border border-neutral-11 rounded-lg overflow-hidden shadow-sm"
    >
      {/* Card header */}
      <div className="px-5 py-4 border-b border-neutral-11">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-neutral-1">
              {meta.title}
            </h2>
            <p className="text-xs text-neutral-6 mt-0.5">{meta.subtitle}</p>
            {meta.note && (
              <p className="text-xs text-neutral-6 mt-1 italic">{meta.note}</p>
            )}
          </div>
          <span className="flex-shrink-0 text-xs text-neutral-6 font-mono whitespace-nowrap">
            {ranked.length} candidate{ranked.length !== 1 ? "s" : ""}
          </span>
        </div>
      </div>

      {/* Card body */}
      <div>
        {ranked.length === 0 ? (
          <p className="px-5 py-4 text-sm text-neutral-6">
            No scored candidates
          </p>
        ) : (
          <Scorecard tierId={tierId} candidates={ranked} />
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
