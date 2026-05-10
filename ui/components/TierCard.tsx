// Server component — renders one tier panel with its candidate scorecard.
// Props are the parsed types from ui/lib/scoreboard.ts; no parseFloat here.

import { Candidate, TierId, TierMeta } from "@/lib/scoreboard";
import Scorecard from "./Scorecard";

interface TierCardProps {
  tierId: TierId;
  meta: TierMeta;
  candidates: Candidate[];
}

export default function TierCard({ tierId, meta, candidates }: TierCardProps) {
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
            {candidates.length} candidate{candidates.length !== 1 ? "s" : ""}
          </span>
        </div>
      </div>

      {/* Card body */}
      <div>
        {candidates.length === 0 ? (
          <p className="px-5 py-4 text-sm text-neutral-6">
            No scored candidates
          </p>
        ) : (
          <Scorecard tierId={tierId} candidates={candidates} />
        )}
      </div>
    </div>
  );
}
