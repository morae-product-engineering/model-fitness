"use client";

// Client component — renders a table of candidates for one tier. Client-side
// because rows are clickable: clicking a row opens the candidate-detail
// drill-down modal (MLI-187). The table itself is otherwise static.
//
// Dimension columns are derived from the first candidate's per_dimension keys
// so the table adapts when the rubric changes (architectural decision 7).
//
// MLI-275 — per-row vendor badge and per-row candidate sparkline. Vendor is
// inferred frontend-side from `candidate_id` (lib/vendor.ts); a missing prefix
// renders the neutral "—" badge. Sparkline data comes from the per-tier
// `trends` payload that the page already fetches for the TrendStrip; if a
// candidate has fewer than two trend points (single run, or no trends data)
// the Spark primitive falls back to an empty SVG.
//
// `product` + `apiBaseUrl` are optional. When omitted (e.g. in component-only
// unit tests for the table itself), rows are still rendered but clicks no-op
// — the drill-down requires both to construct the candidate-detail URL.

import { useState } from "react";
import {
  Candidate,
  Family,
  STATUS_LABELS,
  TierId,
  Trends,
} from "@/lib/scoreboard";
import { inferVendor, Vendor } from "@/lib/vendor";
import CandidateDetail from "./CandidateDetail";
import Spark from "./primitives/Spark";

interface ScorecardProps {
  tierId: TierId;
  candidates: Candidate[];
  // Per-tier trend points keyed by candidate. Threaded from TierCard so each
  // row can render its own sparkline next to the score columns. Optional —
  // page-level fetch failures degrade to a sparkline-free table.
  trends?: Trends;
  product?: string;
  apiBaseUrl?: string;
}

export default function Scorecard({
  tierId,
  candidates,
  trends,
  product,
  apiBaseUrl,
}: ScorecardProps) {
  const [selected, setSelected] = useState<Candidate | null>(null);
  const drillDownEnabled = Boolean(product && apiBaseUrl);
  if (candidates.length === 0) {
    return null;
  }

  // Derive dimension column headers from the first candidate. The API
  // guarantees all candidates in a tier have the same dimensions.
  const dimensionIds = Object.keys(candidates[0].per_dimension);

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr className="bg-neutral-13 border-b border-neutral-11 text-neutral-5 font-semibold uppercase tracking-wide">
            <th className="px-3 py-2 text-center w-8">#</th>
            <th className="px-3 py-2 text-left">Candidate</th>
            <th className="px-3 py-2 text-center">Vendor</th>
            <th className="px-3 py-2 text-center">Family</th>
            <th className="px-3 py-2 text-left">Deployment</th>
            <th className="px-3 py-2 text-center">Status</th>
            <th className="px-3 py-2 text-right">Score</th>
            {dimensionIds.map((dim) => (
              <th key={dim} className="px-3 py-2 text-right font-mono">
                {dim}
              </th>
            ))}
            <th className="px-3 py-2 text-center">Trend</th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((c, i) => {
            const sparkData = sparkSeriesFor(c.candidate_id, trends);
            const sparkStroke =
              c.family === "reasoning" ? "var(--orange)" : "var(--neutral-5)";
            return (
              <tr
                key={c.candidate_id}
                data-testid={`tier-${tierId}-candidate`}
                role={drillDownEnabled ? "button" : undefined}
                tabIndex={drillDownEnabled ? 0 : undefined}
                onClick={
                  drillDownEnabled ? () => setSelected(c) : undefined
                }
                onKeyDown={
                  drillDownEnabled
                    ? (e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          setSelected(c);
                        }
                      }
                    : undefined
                }
                className={`border-b border-neutral-11 last:border-0 ${
                  drillDownEnabled
                    ? "cursor-pointer hover:bg-neutral-13 focus:bg-neutral-13 focus:outline-none"
                    : ""
                }`}
              >
                <td className="px-3 py-2 text-center font-mono text-neutral-6">
                  {i + 1}
                </td>
                <td className="px-3 py-2 font-medium text-neutral-1">
                  {c.display_name}
                  {c.deployment === "(unknown)" && (
                    <span className="ml-2 text-xs text-neutral-6 bg-neutral-12 border border-neutral-11 rounded px-1">
                      (unknown)
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-center">
                  <VendorBadge candidateId={c.candidate_id} />
                </td>
                <td className="px-3 py-2 text-center">
                  <span
                    data-testid={`family-icon-${c.family}`}
                    className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide bg-neutral-12 text-neutral-5 rounded px-1.5 py-0.5"
                  >
                    <FamilyDot family={c.family} />
                    {c.family}
                  </span>
                </td>
                <td className="px-3 py-2 font-mono text-neutral-3 text-xs">
                  {c.deployment}
                </td>
                <td className="px-3 py-2 text-center">
                  <StatusPill status={c.status} />
                </td>
                <td className="px-3 py-2 text-right font-mono font-semibold text-neutral-1">
                  <span data-testid="candidate-score">
                    {c.weighted_score.toFixed(1)}
                  </span>
                </td>
                {dimensionIds.map((dim) => (
                  <td
                    key={dim}
                    className="px-3 py-2 text-right font-mono text-neutral-3"
                  >
                    {c.per_dimension[dim] != null
                      ? c.per_dimension[dim].toFixed(1)
                      : "—"}
                  </td>
                ))}
                <td className="px-3 py-2 text-center">
                  <span
                    data-testid="candidate-sparkline"
                    aria-label={`Trend for ${c.display_name}`}
                    className="inline-flex items-center"
                  >
                    <Spark
                      data={sparkData}
                      stroke={sparkStroke}
                      w={60}
                      h={20}
                    />
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {selected && product && apiBaseUrl && (
        <CandidateDetail
          product={product}
          deployment={selected.deployment}
          displayName={selected.display_name}
          family={selected.family}
          candidateId={selected.candidate_id}
          tierId={tierId}
          apiBaseUrl={apiBaseUrl}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}

// Small coloured dot indicating model family (chat / reasoning). Reasoning
// gets the orange accent so the rarer family is the one that pops; chat uses
// neutral-4. Title attribute provides the label for accessibility.
function FamilyDot({ family }: { family: Family }) {
  const cls =
    family === "reasoning" ? "bg-orange" : "bg-neutral-5";
  const label = family === "reasoning" ? "Reasoning" : "Chat";
  return (
    <span
      title={label}
      aria-label={label}
      className={`inline-block w-1.5 h-1.5 rounded-full ${cls}`}
    />
  );
}

// Vendor badge — derives the vendor label from candidate_id via the lib/vendor
// prefix table. Always renders (even on miss) so the `vendor-badge` testid is
// queryable from any row; an unmatched id shows "—" rather than guessing.
function VendorBadge({ candidateId }: { candidateId: string }) {
  const vendor = inferVendor(candidateId);
  const label: string = vendor ?? "—";
  return (
    <span
      data-testid="vendor-badge"
      data-vendor={vendor ?? "unknown"}
      title={vendor ? `Vendor: ${vendor}` : "Vendor unknown"}
      className="inline-block text-[10px] font-semibold uppercase tracking-wide bg-neutral-12 text-neutral-3 rounded px-1.5 py-0.5"
    >
      {label}
    </span>
  );
}

// Status pill colours are limited to what the neutral+orange palette provides.
// No new colours introduced.
function StatusPill({ status }: { status: Candidate["status"] }) {
  const label = STATUS_LABELS[status];

  const cls =
    status === "approved_primary"
      ? "bg-neutral-1 text-white"
      : status === "approved_fallback"
        ? "bg-neutral-3 text-white"
        : status === "rejected"
          ? "bg-neutral-12 text-neutral-5 line-through"
          : "bg-neutral-12 text-neutral-5";

  return (
    <span
      className={`inline-block text-xs font-medium rounded px-1.5 py-0.5 whitespace-nowrap ${cls}`}
    >
      {label}
    </span>
  );
}

// Pull a candidate's weighted_score series from the per-tier trends payload.
// Returns an empty array when trends are absent or the candidate has no
// points; Spark renders a fixed-size empty SVG in that case.
function sparkSeriesFor(
  candidateId: string,
  trends: Trends | undefined,
): number[] {
  if (!trends) return [];
  const series = trends.candidates.find((c) => c.candidate_id === candidateId);
  if (!series) return [];
  // Trends arrive newest-first; reverse so the sparkline reads left-to-right
  // oldest-to-newest, matching TrendStrip (MLI-186).
  return [...series.points].reverse().map((p) => p.weighted_score);
}

// (Vendor type re-export retained to keep imports from this file colocated.)
export type { Vendor };
