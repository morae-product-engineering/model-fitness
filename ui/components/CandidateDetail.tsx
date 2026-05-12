"use client";

// Candidate detail drill-down (MLI-187). Side modal opened from a scoreboard
// row; fetches the candidate-detail endpoint (MLI-184) on mount and renders
// the per-dimension breakdown for the tier the row was clicked in.
//
// Posture inherited from MLI-186: best-effort fetch, fail to a placeholder
// rather than blocking the surrounding page. The scoreboard remains usable
// when the detail endpoint is unavailable.
//
// `latest_run: null` with `history: []` is a real 200 state (unscored slate
// candidates such as phi-4-mini-instruct that the dev seed skips, see
// mmfp/api/candidate_detail.py:14). The empty state is handled here rather
// than treated as an error.
//
// The detail panel labels the run with its `completed_at` ("as of …") rather
// than "latest" globally — the API walks back to the most recent run that
// contains *this* candidate, which may be older than the product's latest
// scoreboard run.

import { useEffect, useRef, useState } from "react";
import {
  CandidateDetail as CandidateDetailType,
  Family,
  TierId,
  WireCandidateDetail,
  parseCandidateDetail,
} from "@/lib/scoreboard";

interface CandidateDetailProps {
  product: string;
  deployment: string;
  displayName: string;
  family: Family;
  tierId: TierId;
  apiBaseUrl: string;
  onClose: () => void;
}

type FetchState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "loaded"; detail: CandidateDetailType };

export default function CandidateDetail({
  product,
  deployment,
  displayName,
  family,
  tierId,
  apiBaseUrl,
  onClose,
}: CandidateDetailProps) {
  const [state, setState] = useState<FetchState>({ kind: "loading" });
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });

    (async () => {
      try {
        const url = `${apiBaseUrl}/api/products/${encodeURIComponent(
          product,
        )}/candidates/${encodeURIComponent(deployment)}`;
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) {
          if (!cancelled) {
            setState({
              kind: "error",
              message: `Detail unavailable (${res.status})`,
            });
          }
          return;
        }
        const wire: WireCandidateDetail = await res.json();
        if (!cancelled) {
          setState({ kind: "loaded", detail: parseCandidateDetail(wire) });
        }
      } catch (err) {
        if (cancelled) return;
        const msg = err instanceof Error ? err.message : "network error";
        setState({ kind: "error", message: `Detail unavailable (${msg})` });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [product, deployment, apiBaseUrl]);

  // Escape key dismisses; focus the panel on open so the key handler binds.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    panelRef.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      data-testid="candidate-detail-overlay"
      role="dialog"
      aria-modal="true"
      aria-label={`Candidate detail — ${displayName}`}
      className="fixed inset-0 z-40 bg-neutral-1/30 flex items-stretch justify-end"
      onClick={(e) => {
        // Click-outside dismissal — only when the backdrop itself is clicked.
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        className="w-full max-w-md bg-white shadow-lg border-l border-neutral-11 flex flex-col outline-none"
      >
        <Header
          displayName={displayName}
          deployment={deployment}
          family={family}
          onClose={onClose}
        />
        <div className="flex-1 overflow-y-auto p-5">
          {state.kind === "loading" && <LoadingBody />}
          {state.kind === "error" && <ErrorBody message={state.message} />}
          {state.kind === "loaded" && (
            <LoadedBody detail={state.detail} tierId={tierId} />
          )}
        </div>
      </div>
    </div>
  );
}

function Header({
  displayName,
  deployment,
  family,
  onClose,
}: {
  displayName: string;
  deployment: string;
  family: Family;
  onClose: () => void;
}) {
  const dotCls = family === "reasoning" ? "bg-orange" : "bg-neutral-5";
  return (
    <div className="px-5 py-4 border-b border-neutral-11 flex items-start justify-between gap-4">
      <div className="min-w-0">
        <h2 className="text-sm font-semibold text-neutral-1 flex items-center gap-2">
          <span
            aria-hidden="true"
            className={`inline-block w-1.5 h-1.5 rounded-full ${dotCls}`}
          />
          {displayName}
        </h2>
        <p className="text-xs text-neutral-6 font-mono mt-0.5">{deployment}</p>
      </div>
      <button
        type="button"
        data-testid="candidate-detail-close"
        onClick={onClose}
        aria-label="Close candidate detail"
        className="text-neutral-5 hover:text-neutral-1 text-lg leading-none px-1"
      >
        ×
      </button>
    </div>
  );
}

function LoadingBody() {
  return (
    <p
      data-testid="candidate-detail-loading"
      className="text-sm text-neutral-6 italic"
    >
      Loading detail…
    </p>
  );
}

function ErrorBody({ message }: { message: string }) {
  return (
    <p
      data-testid="candidate-detail-error"
      className="text-sm text-neutral-5"
    >
      {message}
    </p>
  );
}

function LoadedBody({
  detail,
  tierId,
}: {
  detail: CandidateDetailType;
  tierId: TierId;
}) {
  const tierResult =
    detail.latest_run?.per_tier.find((pt) => pt.tier_id === tierId) ?? null;

  if (!detail.latest_run || !tierResult) {
    return (
      <p
        data-testid="candidate-detail-empty"
        className="text-sm text-neutral-5"
      >
        No scoring data yet for this candidate.
      </p>
    );
  }

  // Dimension order: stable on the API key order. Decimal keys arrive in
  // insertion order, which matches the rubric for the tier.
  const dimensions = Object.entries(tierResult.per_dimension);

  return (
    <>
      <RunStamp
        completedAt={detail.latest_run.completed_at}
        startedAt={detail.latest_run.started_at}
        rubricVersion={detail.latest_run.rubric_version}
      />
      <h3 className="text-xs font-semibold text-neutral-6 uppercase tracking-wide mb-2 mt-4">
        Per-dimension breakdown
      </h3>
      <div data-testid="candidate-detail-dimensions" className="flex flex-col gap-1.5">
        {dimensions.map(([dim, score]) => (
          <DimensionRow key={dim} dimension={dim} score={score} />
        ))}
      </div>
      <div className="mt-4 pt-3 border-t border-neutral-12 text-xs text-neutral-6 flex items-center justify-between">
        <span>Tier total</span>
        <span className="font-mono font-semibold text-neutral-1">
          {tierResult.weighted_score.toFixed(1)}
        </span>
      </div>
    </>
  );
}

function RunStamp({
  completedAt,
  startedAt,
  rubricVersion,
}: {
  completedAt: string | null;
  startedAt: string;
  rubricVersion: string;
}) {
  const iso = completedAt ?? startedAt;
  const d = new Date(iso);
  const label = Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  return (
    <p className="text-xs text-neutral-6">
      as of <span className="text-neutral-3">{label}</span>
      {" · rubric "}
      <span className="text-neutral-3 font-mono">{rubricVersion}</span>
    </p>
  );
}

function DimensionRow({ dimension, score }: { dimension: string; score: number }) {
  const clamped = Math.max(0, Math.min(100, score));
  return (
    <div
      data-testid="dimension-row"
      className="grid grid-cols-[1.4fr_3rem_1fr] items-center gap-3 text-xs"
    >
      <span className="text-neutral-3 truncate" title={dimension}>
        {dimension}
      </span>
      <span className="font-mono text-right font-semibold text-neutral-1">
        {score.toFixed(1)}
      </span>
      <div className="h-1.5 bg-neutral-12 rounded overflow-hidden">
        <div
          className="h-full bg-neutral-4"
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  );
}
