"use client";

// Multi-line sparkline showing how each candidate's weighted score has moved
// across the last N matrix runs for one tier. Now with:
//   - Fixed-range y-axis (0/50/100) with gridlines and labels
//   - X-axis date ticks below the chart area, one per run
//   - Candidate-family legend rendered as HTML above the chart
// Hover any data point to see the candidate, the run date, and the score.
//
// Inline-axis pattern follows ui/prototype/scoreboard.jsx:325-330.
//
// Ordering is owned by the parent (TierCard). Lines render in the order of
// `candidates` — no re-sort here (MLI-185 trail).
//
// Line colour follows the FamilyDot palette (MLI-185 trail): orange for
// reasoning, neutral-5 for chat. No new tokens.

import { useId, useMemo, useState } from "react";
import { Family, TierId, TrendCandidate, TrendRun } from "@/lib/scoreboard";

interface TrendStripProps {
  tierId: TierId;
  runs: TrendRun[];
  candidates: TrendCandidate[];
}

// Family palette — keep in sync with FamilyDot in Scorecard.tsx.
const FAMILY_STROKE: Record<Family, string> = {
  reasoning: "#ff6900", // orange
  chat: "#595959", // neutral-5
};

const WIDTH = 240;
const HEIGHT = 140;
// PAD_X / PAD_Y bound the chart area. Extra bottom padding reserves space for
// x-axis date labels; extra left padding reserves space for y-axis labels.
const PAD_X = 28; // left padding for y-axis labels
const PAD_Y = 8;
const PAD_BOTTOM = 28; // extra bottom space for x-tick labels
const SCORE_MIN = 0;
const SCORE_MAX = 100;

// Chart area bounds (inside the SVG).
const CHART_TOP = PAD_Y;
const CHART_BOTTOM = HEIGHT - PAD_BOTTOM;
const CHART_LEFT = PAD_X;
const CHART_RIGHT = WIDTH - 4;

export default function TrendStrip({ tierId, runs, candidates }: TrendStripProps) {
  const testId = `tier-${tierId}-trend-strip`;
  const tooltipId = useId();
  const [hover, setHover] = useState<{
    candidateIdx: number;
    runIdx: number;
  } | null>(null);

  // API returns runs newest-first. Render time left-to-right oldest-to-newest
  // so the eye reads improvement as up-and-to-the-right.
  const chronoRuns = useMemo(() => [...runs].reverse(), [runs]);

  // Families present in the data — used for the legend.
  const familiesPresent = useMemo(() => {
    const seen = new Set<Family>();
    for (const c of candidates) seen.add(c.family);
    return (["reasoning", "chat"] as Family[]).filter((f) => seen.has(f));
  }, [candidates]);

  if (chronoRuns.length < 2) {
    return (
      <div
        data-testid={testId}
        className="px-5 py-3 text-xs text-neutral-6 italic border-t border-neutral-11"
      >
        Not enough history yet
      </div>
    );
  }

  const xFor = (i: number) => {
    if (chronoRuns.length === 1) return (CHART_LEFT + CHART_RIGHT) / 2;
    return CHART_LEFT + (i * (CHART_RIGHT - CHART_LEFT)) / (chronoRuns.length - 1);
  };
  const yFor = (score: number) => {
    const clamped = Math.max(SCORE_MIN, Math.min(SCORE_MAX, score));
    const ratio = (clamped - SCORE_MIN) / (SCORE_MAX - SCORE_MIN);
    // Fixed range (not min/max-from-data) so the vertical axis is consistent
    // across tiers. A min/max-derived range would re-hide variance by
    // re-stretching to fill — the opposite of what the audit surfaced.
    return CHART_BOTTOM - ratio * (CHART_BOTTOM - CHART_TOP);
  };

  // Index points by run_id so each candidate's series aligns to the canonical
  // run order even if a candidate is missing from earlier runs.
  const runIndex = new Map(chronoRuns.map((r, i) => [r.run_id, i]));

  const series = candidates.map((c) => {
    const segments: { x: number; y: number; runIdx: number; score: number }[] = [];
    for (const p of c.points) {
      const runIdx = runIndex.get(p.run_id);
      if (runIdx == null) continue;
      segments.push({
        x: xFor(runIdx),
        y: yFor(p.weighted_score),
        runIdx,
        score: p.weighted_score,
      });
    }
    segments.sort((a, b) => a.runIdx - b.runIdx);
    return { candidate: c, segments };
  });

  const hoveredCandidate =
    hover != null ? series[hover.candidateIdx] : null;
  const hoveredPoint =
    hoveredCandidate?.segments.find((s) => s.runIdx === hover?.runIdx) ?? null;
  const hoveredRun =
    hover != null ? chronoRuns[hover.runIdx] : null;

  // Snap tooltip alignment to avoid clipping at the left/right edges.
  // <25% of chart width → left-align from the point; >75% → right-align; else centre.
  const tooltipStyle: React.CSSProperties = (() => {
    if (!hoveredPoint) return {};
    const xPct = (hoveredPoint.x / WIDTH) * 100;
    if (xPct < 25) {
      return { top: 0, left: `calc(${xPct}% + 1.25rem)`, transform: "translateY(-4px)" };
    }
    if (xPct > 75) {
      return {
        top: 0,
        right: `calc(${(1 - hoveredPoint.x / WIDTH) * 100}% + 1.25rem)`,
        transform: "translateY(-4px)",
      };
    }
    return { top: 0, left: `calc(${xPct}% + 1.25rem)`, transform: "translate(-50%, -4px)" };
  })();

  // Y-axis reference ticks at fixed scores.
  const Y_TICKS = [0, 50, 100];

  const totalSvgHeight = HEIGHT;

  return (
    <div
      data-testid={testId}
      className="relative px-5 py-3 border-t border-neutral-11"
      aria-describedby={tooltipId}
    >
      {/* Legend — rendered as HTML above the SVG so FamilyDot styling applies */}
      {familiesPresent.length > 0 && (
        <div className="flex justify-end gap-3 mb-1">
          {familiesPresent.map((f) => (
            <span key={f} className="flex items-center gap-1 text-xs text-neutral-6">
              <span
                className="inline-block rounded-full"
                style={{
                  width: 6,
                  height: 6,
                  background: FAMILY_STROKE[f],
                  flexShrink: 0,
                }}
              />
              {f === "reasoning" ? "Reasoning" : "Chat"}
            </span>
          ))}
        </div>
      )}

      <svg
        viewBox={`0 0 ${WIDTH} ${totalSvgHeight}`}
        width="100%"
        height={totalSvgHeight}
        role="img"
        aria-label={`Trend strip for tier ${tierId}`}
        className="block overflow-visible"
      >
        {/* Y-axis gridlines and labels at 0, 50, 100 */}
        {Y_TICKS.map((score) => {
          const y = yFor(score);
          return (
            <g key={`ytick-${score}`}>
              <line
                x1={CHART_LEFT}
                y1={y}
                x2={CHART_RIGHT}
                y2={y}
                stroke="var(--neutral-12)"
                strokeWidth={1}
              />
              <text
                x={CHART_LEFT - 4}
                y={y}
                textAnchor="end"
                dominantBaseline="middle"
                fontSize={10}
                fontFamily="var(--font-mono)"
                fill="var(--neutral-6)"
              >
                {score}
              </text>
            </g>
          );
        })}

        {/* Candidate lines and hit-targets */}
        {series.map(({ candidate, segments }, ci) => {
          if (segments.length === 0) return null;
          const stroke = FAMILY_STROKE[candidate.family];
          const path = segments
            .map((s, i) => `${i === 0 ? "M" : "L"}${s.x.toFixed(2)},${s.y.toFixed(2)}`)
            .join(" ");
          return (
            <g key={candidate.candidate_id}>
              <path
                d={path}
                fill="none"
                stroke={stroke}
                strokeWidth={1.25}
                strokeLinecap="round"
                strokeLinejoin="round"
                opacity={hover && hover.candidateIdx !== ci ? 0.25 : 1}
              />
              {segments.map((s) => (
                <circle
                  key={`${candidate.candidate_id}-${s.runIdx}`}
                  cx={s.x}
                  cy={s.y}
                  r={hover?.candidateIdx === ci && hover.runIdx === s.runIdx ? 3 : 1.75}
                  fill={stroke}
                  opacity={hover && hover.candidateIdx !== ci ? 0.25 : 1}
                />
              ))}
              {/* Larger transparent hit-targets for hover. */}
              {segments.map((s) => (
                <circle
                  key={`hit-${candidate.candidate_id}-${s.runIdx}`}
                  data-testid={`trend-point-${candidate.candidate_id}-${s.runIdx}`}
                  cx={s.x}
                  cy={s.y}
                  r={8}
                  fill="transparent"
                  onMouseEnter={() =>
                    setHover({ candidateIdx: ci, runIdx: s.runIdx })
                  }
                  onMouseLeave={() => setHover(null)}
                />
              ))}
            </g>
          );
        })}

        {/* X-axis date ticks — one per run along the bottom */}
        {chronoRuns.map((r, i) => {
          const x = xFor(i);
          return (
            <g key={`xtick-${r.run_id}`} data-testid="trend-x-tick">
              <line
                x1={x}
                y1={CHART_BOTTOM}
                x2={x}
                y2={CHART_BOTTOM + 4}
                stroke="var(--neutral-6)"
                strokeWidth={1}
              />
              <text
                x={x}
                y={CHART_BOTTOM + 14}
                textAnchor="middle"
                fontSize={10}
                fontFamily="var(--font-mono)"
                fill="var(--neutral-6)"
              >
                {formatRunTimestamp(r.completed_at, r.started_at)}
              </text>
            </g>
          );
        })}
      </svg>

      {hoveredCandidate && hoveredPoint && hoveredRun && (
        <div
          id={tooltipId}
          role="tooltip"
          data-testid={`tier-${tierId}-trend-tooltip`}
          className="absolute z-10 pointer-events-none bg-neutral-1 text-white text-xs rounded px-2 py-1 shadow-md"
          style={tooltipStyle}
        >
          <div className="font-medium">
            {hoveredCandidate.candidate.display_name}
          </div>
          <div className="font-mono text-neutral-11">
            {formatRunTimestamp(hoveredRun.completed_at, hoveredRun.started_at)}
          </div>
          <div className="font-mono text-neutral-11">
            {hoveredPoint.score.toFixed(1)}
          </div>
        </div>
      )}
    </div>
  );
}

// Tooltip framing per MLI-180 trail: use `completed_at` ("when this score was
// produced"). Fall back to `started_at` if the run hasn't completed yet — a
// real state for in-flight runs the trends endpoint includes.
function formatRunTimestamp(
  completedAt: string | null,
  startedAt: string,
): string {
  const iso = completedAt ?? startedAt;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}
