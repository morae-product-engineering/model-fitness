"use client";

// Multi-line sparkline showing how each candidate's weighted score has moved
// across the last N matrix runs for one tier. Sparkline-style — no axes, no
// legend. Hover any data point to see the candidate, the run's completed_at,
// and the score.
//
// Ordering is owned by the parent (TierCard). Lines render in the order of
// `candidates` — no re-sort here (MLI-185 trail).
//
// Line colour follows the FamilyDot palette (MLI-185 trail): orange for
// reasoning, neutral-5 for chat. No new tokens. A real design pass should
// revisit this for Slice 3 as a whole rather than per-sub-task.

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
const HEIGHT = 56;
const PAD_X = 4;
const PAD_Y = 6;
const SCORE_MIN = 0;
const SCORE_MAX = 100;

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
    if (chronoRuns.length === 1) return WIDTH / 2;
    return PAD_X + (i * (WIDTH - 2 * PAD_X)) / (chronoRuns.length - 1);
  };
  const yFor = (score: number) => {
    const clamped = Math.max(SCORE_MIN, Math.min(SCORE_MAX, score));
    const ratio = (clamped - SCORE_MIN) / (SCORE_MAX - SCORE_MIN);
    return HEIGHT - PAD_Y - ratio * (HEIGHT - 2 * PAD_Y);
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

  return (
    <div
      data-testid={testId}
      className="relative px-5 py-3 border-t border-neutral-11"
      aria-describedby={tooltipId}
    >
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        width="100%"
        height={HEIGHT}
        role="img"
        aria-label={`Trend strip for tier ${tierId}`}
        className="block overflow-visible"
      >
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
      </svg>

      {hoveredCandidate && hoveredPoint && hoveredRun && (
        <div
          id={tooltipId}
          role="tooltip"
          data-testid={`tier-${tierId}-trend-tooltip`}
          className="absolute z-10 pointer-events-none bg-neutral-1 text-white text-xs rounded px-2 py-1 shadow-md"
          style={{
            // Position above the hovered point. Coordinates inside the SVG are
            // viewBox units; convert by % of width and add the padding offset.
            left: `calc(${(hoveredPoint.x / WIDTH) * 100}% + 1.25rem)`,
            top: 0,
            transform: "translate(-50%, -4px)",
          }}
        >
          <div className="font-medium">
            {hoveredCandidate.candidate.display_name}
          </div>
          <div className="font-mono text-neutral-11">
            {hoveredPoint.score.toFixed(1)}
            {" · "}
            {formatRunTimestamp(hoveredRun.completed_at, hoveredRun.started_at)}
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
