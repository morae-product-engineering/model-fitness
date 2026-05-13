// lifted from ui/prototype/scoreboard.jsx:99-116 (four-cell grid) and
// :128-159 (PortfolioSlot). Four cells per tier — Primary / Fallback /
// Under evaluation / Rejected — rendering the audit-Option-C summary above
// the candidate table.
//
// Mapping note: the prototype keys role/status off per-tier MMFP_RUNS rows
// (`role: 'primary' | 'fallback'`, `status: 'eval' | 'rejected'`). Production
// carries portfolio state on the Candidate itself via CandidateStatus
// (`approved_primary` / `approved_fallback` / `under_evaluation` / `rejected`),
// so the slot lookup filters by status rather than role.

import { Candidate, TierId, Trends } from "@/lib/scoreboard";
import Delta from "./primitives/Delta";

interface PortfolioSummaryProps {
  tierId: TierId;
  candidates: Candidate[];
  trends?: Trends;
}

export default function PortfolioSummary({
  tierId,
  candidates,
  trends,
}: PortfolioSummaryProps) {
  const primary = candidates.find((c) => c.status === "approved_primary");
  const fallback = candidates.find((c) => c.status === "approved_fallback");
  const evals = candidates.filter((c) => c.status === "under_evaluation");
  const rejected = candidates.filter((c) => c.status === "rejected");

  return (
    <div
      data-testid={`portfolio-summary-${tierId}`}
      className="grid border-t border-neutral-11"
      style={{ gridTemplateColumns: "1.4fr 1fr 1fr 1fr" }}
    >
      <PortfolioSlot
        tierId={tierId}
        kind="primary"
        label="Primary"
        candidate={primary}
        trends={trends}
      />
      <PortfolioSlot
        tierId={tierId}
        kind="fallback"
        label="Fallback"
        candidate={fallback}
        trends={trends}
        sep
      />
      <CountCell
        tierId={tierId}
        kind="under-evaluation"
        label="Under evaluation"
        count={evals.length}
        detail={renderEvalDetail(evals)}
      />
      <CountCell
        tierId={tierId}
        kind="rejected"
        label="Rejected"
        count={rejected.length}
        detail={rejected.length > 0 ? `${rejected.length} declined for this tier` : "—"}
        dim
      />
    </div>
  );
}

// — Primary / Fallback cell — lifted from PortfolioSlot in
// ui/prototype/scoreboard.jsx:128-159. The prototype renders a Spark inside
// the slot; trend-strip polish is owned by MLI-264, so the score delta is
// included here (cheap, uses already-fetched trends data) but the inline
// sparkline is deferred to that ticket.
function PortfolioSlot({
  tierId,
  kind,
  label,
  candidate,
  trends,
  sep,
}: {
  tierId: TierId;
  kind: "primary" | "fallback";
  label: string;
  candidate?: Candidate;
  trends?: Trends;
  sep?: boolean;
}) {
  const testid = `portfolio-cell-${kind}-${tierId}`;
  if (!candidate) {
    return (
      <div
        data-testid={testid}
        className="px-5 py-4"
        style={{ borderLeft: sep ? "1px solid var(--neutral-11)" : "none" }}
      >
        <div className="text-[11px] font-semibold uppercase tracking-wide text-neutral-6">
          {label}
        </div>
        <div className="text-sm text-neutral-7 mt-2">— none —</div>
      </div>
    );
  }
  const delta = computeScoreDelta(candidate.candidate_id, trends);
  return (
    <div
      data-testid={testid}
      className="px-5 py-4"
      style={{ borderLeft: sep ? "1px solid var(--neutral-11)" : "none" }}
    >
      <div className="flex items-center justify-between">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-neutral-6">
          {label}
        </div>
      </div>
      <div className="text-[17px] font-semibold text-neutral-1 mt-1.5">
        {candidate.display_name}
      </div>
      <div className="text-xs text-neutral-6 mt-0.5 font-mono">
        {candidate.deployment}
      </div>
      <div className="flex items-center gap-2.5 mt-2">
        <span
          data-testid={`portfolio-cell-${kind}-score`}
          className="font-mono font-semibold text-neutral-1"
          style={{ fontSize: 22, letterSpacing: "-0.02em" }}
        >
          {candidate.weighted_score.toFixed(1)}
        </span>
        <Delta value={delta} />
      </div>
    </div>
  );
}

// — Under evaluation / Rejected cell — lifted from ui/prototype/scoreboard.jsx
// :102-115. Big count + a short detail string. The prototype shows the top
// rejection reason; production Candidate has no rejection_reason field, so the
// rejected detail string falls back to a count summary (see closing-comment
// finding).
function CountCell({
  tierId,
  kind,
  label,
  count,
  detail,
  dim,
}: {
  tierId: TierId;
  kind: "under-evaluation" | "rejected";
  label: string;
  count: number;
  detail: string;
  dim?: boolean;
}) {
  return (
    <div
      data-testid={`portfolio-cell-${kind}-${tierId}`}
      className="px-5 py-4"
      style={{ borderLeft: "1px solid var(--neutral-11)" }}
    >
      <div className="text-[11px] font-semibold uppercase tracking-wide text-neutral-6">
        {label}
      </div>
      <div
        data-testid={`portfolio-cell-${kind}-count`}
        className={`font-semibold mt-1.5 ${dim ? "text-neutral-4" : "text-neutral-1"}`}
        style={{ fontSize: 28, letterSpacing: "-0.01em" }}
      >
        {count}
      </div>
      <div className="text-xs text-neutral-6 mt-0.5">{detail}</div>
    </div>
  );
}

// Top 2 deployments inline, plus "+N" overflow — mirrors the prototype's
// `evals.slice(0, 2).map(r => r.cand.name)` rendering.
function renderEvalDetail(evals: Candidate[]): string {
  if (evals.length === 0) return "—";
  const named = evals.slice(0, 2).map((c) => c.display_name);
  const overflow = evals.length > 2 ? `, +${evals.length - 2}` : "";
  return named.join(", ") + overflow;
}

// Pull the candidate's last two trend points and return latest - previous.
// `null` when trends are unavailable for the candidate or fewer than two
// points exist; Delta renders an em-dash in that case.
function computeScoreDelta(
  candidateId: string,
  trends: Trends | undefined,
): number | null {
  if (!trends) return null;
  const series = trends.candidates.find((c) => c.candidate_id === candidateId);
  if (!series || series.points.length < 2) return null;
  const points = series.points;
  return points[points.length - 1].weighted_score - points[points.length - 2].weighted_score;
}
