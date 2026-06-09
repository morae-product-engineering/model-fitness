"use client";

// Candidate detail drill-down (MLI-187, weight-aware breakdown MLI-274).
// Side modal opened from a scoreboard row; fetches the candidate-detail
// endpoint (MLI-184) on mount and renders the per-dimension breakdown for
// the tier the row was clicked in.
//
// MLI-274 replaced the bar placeholder with a rubric-weight-aware view:
//   * Each row shows the dimension name, weight (data-testid="dim-weight-<id>"),
//     normalised score, and weight × score contribution to the tier composite.
//   * Active dimensions (rubric.dimension.status === "active") contribute to
//     the composite; the engine normalises against the active-weight total
//     (per MLI-269) so the contribution shown is `(weight * score) / 100` —
//     summing the contributions reproduces the composite the API returns.
//   * Draft dimensions (status === "draft") are surfaced visually de-emphasised
//     with a "Draft — activates in Slice 6" label. They carry `weight: 0`
//     server-side and do not contribute to the composite. Showing them keeps
//     a portfolio viewer aware they exist in the rubric and aren't simply
//     missing — distinct from a score of zero on an active dimension.
//
// Posture inherited from MLI-186: best-effort fetch, fail to a placeholder
// rather than blocking the surrounding page. The scoreboard remains usable
// when the detail endpoint is unavailable.
//
// `latest_run: null` with `history: []` is a real 200 state (unscored slate
// candidates such as phi-4-mini-instruct that the dev seed skips, see
// mmfp/api/candidate_detail.py:14). The empty state still renders the rubric
// dimensions so a portfolio viewer can see the rubric shape against a
// not-yet-scored candidate.

import { useEffect, useMemo, useRef, useState } from "react";
import {
  CandidateDetail as CandidateDetailType,
  Family,
  RubricDimension,
  Status,
  TierId,
  WireCandidateDetail,
  parseCandidateDetail,
} from "@/lib/scoreboard";
import {
  AuditEntry,
  DecisionKind,
  PendingDecision,
  fetchAuditLog,
} from "@/lib/promotion";
import { inferVendor } from "@/lib/vendor";
import DecisionModal from "./DecisionModal";
import Btn from "./primitives/Btn";
import Spark from "./primitives/Spark";

interface CandidateDetailProps {
  product: string;
  deployment: string;
  displayName: string;
  family: Family;
  // Optional — when provided the header renders a vendor badge derived from
  // the slate id (MLI-275). Older callers that don't thread it through still
  // get the rest of the modal. The fetched payload also carries
  // `candidate_id`, but the prop lets us render the badge during loading.
  candidateId?: string;
  tierId: TierId;
  apiBaseUrl: string;
  onClose: () => void;
  // Called after a decision is committed so the parent can refresh scoreboard data.
  onStatusChange?: () => void;
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
  candidateId,
  tierId,
  apiBaseUrl,
  onClose,
  onStatusChange,
}: CandidateDetailProps) {
  const [state, setState] = useState<FetchState>({ kind: "loading" });
  const [auditEntries, setAuditEntries] = useState<AuditEntry[]>([]);
  const [pendingDecision, setPendingDecision] = useState<PendingDecision | null>(null);
  // Incrementing this triggers a re-fetch of both detail and audit log after a decision.
  const [refreshKey, setRefreshKey] = useState(0);
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
  }, [product, deployment, apiBaseUrl, refreshKey]);

  useEffect(() => {
    fetchAuditLog(apiBaseUrl, product, deployment).then(setAuditEntries);
  }, [apiBaseUrl, product, deployment, refreshKey]);

  // Escape key dismisses; focus the panel on open so the key handler binds.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    panelRef.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  function handleDecision(kind: DecisionKind) {
    setPendingDecision({ kind, displayName, deployment, tierId });
  }

  function handleDecisionSuccess() {
    setRefreshKey((k) => k + 1);
    onStatusChange?.();
  }

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
          candidateId={
            state.kind === "loaded" ? state.detail.candidate_id : candidateId
          }
          onClose={onClose}
        />
        <div className="flex-1 overflow-y-auto p-5">
          {state.kind === "loading" && <LoadingBody />}
          {state.kind === "error" && <ErrorBody message={state.message} />}
          {state.kind === "loaded" && (
            <LoadedBody
              detail={state.detail}
              tierId={tierId}
              auditEntries={auditEntries}
              onDecision={handleDecision}
            />
          )}
        </div>
      </div>

      {pendingDecision && (
        <DecisionModal
          action={pendingDecision}
          product={product}
          apiBaseUrl={apiBaseUrl}
          onClose={() => setPendingDecision(null)}
          onSuccess={handleDecisionSuccess}
        />
      )}
    </div>
  );
}

function Header({
  displayName,
  deployment,
  family,
  candidateId,
  onClose,
}: {
  displayName: string;
  deployment: string;
  family: Family;
  candidateId: string | undefined;
  onClose: () => void;
}) {
  const dotCls = family === "reasoning" ? "bg-orange" : "bg-neutral-5";
  const vendor = candidateId ? inferVendor(candidateId) : null;
  return (
    <div className="px-5 py-4 border-b border-neutral-11 flex items-start justify-between gap-4">
      <div className="min-w-0">
        <h2 className="text-sm font-semibold text-neutral-1 flex items-center gap-2 flex-wrap">
          <span
            aria-hidden="true"
            className={`inline-block w-1.5 h-1.5 rounded-full ${dotCls}`}
          />
          <span className="truncate">{displayName}</span>
          {candidateId && (
            <span
              data-testid="vendor-badge"
              data-vendor={vendor ?? "unknown"}
              title={vendor ? `Vendor: ${vendor}` : "Vendor unknown"}
              className="inline-block text-[10px] font-semibold uppercase tracking-wide bg-neutral-12 text-neutral-3 rounded px-1.5 py-0.5"
            >
              {vendor ?? "—"}
            </span>
          )}
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
  auditEntries,
  onDecision,
}: {
  detail: CandidateDetailType;
  tierId: TierId;
  auditEntries: AuditEntry[];
  onDecision: (kind: DecisionKind) => void;
}) {
  const rubricTier = useMemo(
    () => detail.rubric.tiers.find((t) => t.tier_id === tierId) ?? null,
    [detail.rubric, tierId],
  );
  const tierResult =
    detail.latest_run?.per_tier.find((pt) => pt.tier_id === tierId) ?? null;

  // The rubric is the source of truth for which dimensions to render; the
  // run only supplies the scores. If the rubric has no entry for this tier
  // we have nothing to draw — defensive, shouldn't happen in practice.
  if (!rubricTier) {
    return (
      <p
        data-testid="candidate-detail-empty"
        className="text-sm text-neutral-5"
      >
        No rubric configuration for this tier.
      </p>
    );
  }

  const perDimension = tierResult?.per_dimension ?? {};
  const hasRun = detail.latest_run !== null && tierResult !== null;

  // History sparkline series for this tier. `history` arrives newest-first;
  // reverse so the line reads oldest-to-newest left-to-right, matching the
  // TrendStrip convention (MLI-186). Entries without a score for this tier
  // drop out — Spark renders an empty SVG when fewer than two points remain.
  const sparkSeries = [...detail.history]
    .reverse()
    .map((h) => h.per_tier_scores[tierId])
    .filter((v): v is number => typeof v === "number");
  const sparkStroke =
    detail.family === "reasoning" ? "var(--orange)" : "var(--neutral-5)";

  return (
    <>
      {hasRun && detail.latest_run ? (
        <RunStamp
          completedAt={detail.latest_run.completed_at}
          startedAt={detail.latest_run.started_at}
          rubricVersion={detail.latest_run.rubric_version}
        />
      ) : (
        <UnscoredStamp rubricVersion={detail.rubric.version} />
      )}
      {detail.base_model && (
        <p
          data-testid="candidate-detail-base-model"
          className="text-xs text-neutral-6 mt-1"
        >
          Base model:{" "}
          <span className="text-neutral-3 font-mono">{detail.base_model}</span>
        </p>
      )}
      <div className="mt-3 flex items-center justify-between gap-3">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-neutral-6">
          Tier history
        </span>
        <span
          data-testid="candidate-sparkline"
          aria-label={`Score history for ${detail.display_name}`}
        >
          <Spark data={sparkSeries} stroke={sparkStroke} w={120} h={28} />
        </span>
      </div>
      <h3 className="text-xs font-semibold text-neutral-6 uppercase tracking-wide mb-2 mt-4">
        Per-dimension breakdown
      </h3>
      <DimensionTableHeader />
      <div data-testid="candidate-detail-dimensions" className="flex flex-col">
        {rubricTier.dimensions.map((dim) => (
          <DimensionRow
            key={dim.id}
            dimension={dim}
            score={perDimension[dim.id]}
          />
        ))}
      </div>
      <div className="mt-4 pt-3 border-t border-neutral-12 text-xs text-neutral-6 flex items-center justify-between">
        <span>Tier composite</span>
        <span
          data-testid="candidate-detail-composite"
          className="font-mono font-semibold text-neutral-1"
        >
          {hasRun && tierResult
            ? tierResult.weighted_score.toFixed(1)
            : "—"}
        </span>
      </div>

      <DecisionButtons
        status={detail.status}
        onDecision={onDecision}
      />

      <AuditHistory entries={auditEntries} />
    </>
  );
}

function UnscoredStamp({ rubricVersion }: { rubricVersion: string }) {
  return (
    <p className="text-xs text-neutral-6" data-testid="candidate-detail-empty">
      No scoring data yet for this candidate.
      {" · rubric "}
      <span className="text-neutral-3 font-mono">{rubricVersion}</span>
    </p>
  );
}

function DimensionTableHeader() {
  return (
    <div className="grid grid-cols-[1fr_3.5rem_3.5rem_3.5rem] gap-2 text-[10px] uppercase tracking-wide text-neutral-6 font-semibold pb-1 border-b border-neutral-12">
      <span>Dimension</span>
      <span className="text-right">Weight</span>
      <span className="text-right">Score</span>
      <span className="text-right">w × s</span>
    </div>
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

function DimensionRow({
  dimension,
  score,
}: {
  dimension: RubricDimension;
  score: number | undefined;
}) {
  const isDraft = dimension.status === "draft";
  const hasScore = typeof score === "number" && Number.isFinite(score);
  // Active dimensions: contribution to the (active-weight-normalised) tier
  // composite is (weight * score) / 100. The engine normalises by the active
  // weight total (MLI-269), so contributions sum to the displayed composite.
  // Drafts carry weight 0 server-side, so contribution is 0 regardless.
  const contribution =
    !isDraft && hasScore ? (dimension.weight * score!) / 100 : null;

  // Weight format: integer-style for tidy display (35%); the rubric never
  // declares fractional weights at v0.1 but we render whatever the API
  // returned via parseFloat — toLocaleString without minimumFractionDigits
  // collapses "35.0" to "35".
  const weightLabel = `${dimension.weight}%`;

  const rowTone = isDraft ? "text-neutral-6" : "text-neutral-3";
  const valueTone = isDraft
    ? "text-neutral-6 font-normal"
    : "text-neutral-1 font-semibold";

  return (
    <div
      data-testid="dimension-row"
      data-dimension-id={dimension.id}
      data-dimension-status={dimension.status}
      className={`grid grid-cols-[1fr_3.5rem_3.5rem_3.5rem] items-baseline gap-2 text-xs py-1.5 border-b border-neutral-12 last:border-b-0 ${rowTone}`}
    >
      <span className="min-w-0">
        <span className="truncate block" title={dimension.description}>
          {dimension.name}
        </span>
        {isDraft && (
          <span
            data-testid="dimension-draft-label"
            className="text-[10px] text-neutral-6 italic block mt-0.5"
          >
            Draft — activates in Slice 6
          </span>
        )}
      </span>
      <span
        data-testid={`dim-weight-${dimension.id}`}
        className={`font-mono text-right ${valueTone}`}
      >
        {weightLabel}
      </span>
      <span className={`font-mono text-right ${valueTone}`}>
        {isDraft ? "—" : hasScore ? score!.toFixed(1) : "—"}
      </span>
      <span className={`font-mono text-right ${valueTone}`}>
        {contribution !== null ? contribution.toFixed(1) : "—"}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Decision buttons — shown in the loaded state. Which buttons render depends
// on current status; rejected candidates have no available actions (no reinstate
// endpoint exists yet).
// ---------------------------------------------------------------------------

const ACTION_LABELS: Record<string, string> = {
  promote_primary: "Promoted to Primary",
  promote_fallback: "Set as Fallback",
  reject: "Rejected",
  revert: "Reverted",
};

function DecisionButtons({
  status,
  onDecision,
}: {
  status: Status;
  onDecision: (kind: DecisionKind) => void;
}) {
  if (status === "rejected") {
    return (
      <div className="mt-5 pt-4 border-t border-neutral-12">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-neutral-6 mb-2">
          Decisions
        </p>
        <p className="text-xs text-neutral-6 italic">
          Candidate is rejected — no actions available.
        </p>
      </div>
    );
  }

  return (
    <div
      data-testid="decision-buttons"
      className="mt-5 pt-4 border-t border-neutral-12"
    >
      <p className="text-[11px] font-semibold uppercase tracking-wide text-neutral-6 mb-2">
        Decisions
      </p>
      <div className="flex flex-col gap-1.5">
        {status !== "approved_primary" && (
          <Btn
            variant="default"
            size="sm"
            data-testid="btn-promote-primary"
            onClick={() => onDecision("promote_primary")}
          >
            Promote to Primary
          </Btn>
        )}
        {status !== "approved_fallback" && (
          <Btn
            variant="outline"
            size="sm"
            data-testid="btn-promote-fallback"
            onClick={() => onDecision("promote_fallback")}
          >
            Set as Fallback
          </Btn>
        )}
        <Btn
          variant="ghost"
          size="sm"
          data-testid="btn-reject"
          style={{ color: "var(--warm-red)" }}
          onClick={() => onDecision("reject")}
        >
          Reject
        </Btn>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Audit history — shows the last 10 decisions for this candidate in the
// drawer. Empty when no decisions have been made yet.
// ---------------------------------------------------------------------------

function AuditHistory({ entries }: { entries: AuditEntry[] }) {
  if (entries.length === 0) return null;

  return (
    <div
      data-testid="audit-history"
      className="mt-5 pt-4 border-t border-neutral-12"
    >
      <p className="text-[11px] font-semibold uppercase tracking-wide text-neutral-6 mb-2">
        Decision history
      </p>
      <div className="flex flex-col gap-2">
        {entries.map((e) => (
          <AuditEntryRow key={e.id} entry={e} />
        ))}
      </div>
    </div>
  );
}

function AuditEntryRow({ entry }: { entry: AuditEntry }) {
  const label = ACTION_LABELS[entry.action] ?? entry.action;
  const isReject = entry.action === "reject";
  const pillCls = isReject
    ? "bg-light-red text-warm-red"
    : "bg-light-green text-green";

  const d = new Date(entry.timestamp);
  const dateLabel = Number.isNaN(d.getTime())
    ? entry.timestamp
    : d.toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });

  return (
    <div className="text-xs border border-neutral-12 rounded-md p-2.5">
      <div className="flex items-center gap-2 mb-1">
        <span
          className={`inline-block text-[10px] font-semibold rounded px-1.5 py-0.5 ${pillCls}`}
        >
          {label}
        </span>
        <span className="font-mono text-neutral-6 text-[10px]">{dateLabel}</span>
      </div>
      <p className="text-neutral-3 leading-snug">&ldquo;{entry.rationale}&rdquo;</p>
      <p className="text-neutral-6 mt-1 font-mono text-[10px]">{entry.actor}</p>
    </div>
  );
}
