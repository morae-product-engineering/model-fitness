"use client";

// Collapsible history panel for the Scoreboard (MFP-16).
// Merges audit-log status changes with rubric-save records into a single
// chronological feed. Uses two existing API endpoints:
//   GET /api/products/{product}/audit-log      — status changes (MFP-14)
//   GET /api/products/{product}/rubric-audit   — rubric saves (Slice 4)
// Note: the task spec named the rubric source /rubric/history, but that
// endpoint does not exist; /rubric-audit serves the same data. Flagged for
// human review.

import { useState, useEffect } from "react";
import { AuditEntry, RubricAuditRecord } from "@/lib/promotion";

type StatusEvent = {
  kind: "status_change";
  timestamp: string;
  entry: AuditEntry;
};

type RubricEvent = {
  kind: "rubric_save";
  timestamp: string;
  entry: RubricAuditRecord;
};

export type HistoryEvent = StatusEvent | RubricEvent;

const PAGE_SIZE = 20;

const ACTION_LABELS: Record<string, string> = {
  promote_primary: "Promoted to Primary",
  promote_fallback: "Set as Fallback",
  reject: "Rejected",
  revert: "Reverted",
};

function fmtDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
}

// ---------------------------------------------------------------------------
// Individual entry renderers
// ---------------------------------------------------------------------------

function StatusEntry({ entry }: { entry: AuditEntry }) {
  const label = ACTION_LABELS[entry.action] ?? entry.action;
  const isReject = entry.action === "reject";
  const pillCls = isReject
    ? "bg-light-red text-warm-red"
    : "bg-light-green text-green";
  return (
    <div
      data-testid="history-entry"
      className="text-xs border border-neutral-11 rounded-md p-3 bg-white"
    >
      <div className="flex items-center gap-2 mb-1.5 flex-wrap">
        <span
          className={`inline-block text-[10px] font-semibold rounded px-1.5 py-0.5 ${pillCls}`}
        >
          {label}
        </span>
        <span className="font-mono text-neutral-6 text-[10px]">
          {fmtDate(entry.timestamp)}
        </span>
        <span className="font-mono text-neutral-5 text-[10px] truncate">
          {entry.candidate_deployment}
        </span>
      </div>
      <p className="text-neutral-3 leading-snug truncate">
        &ldquo;{entry.rationale}&rdquo;
      </p>
      <p className="text-neutral-6 mt-1 font-mono text-[10px]">{entry.actor}</p>
    </div>
  );
}

function RubricEntry({ entry }: { entry: RubricAuditRecord }) {
  return (
    <div
      data-testid="history-entry"
      className="text-xs border border-neutral-11 rounded-md p-3 bg-white"
    >
      <div className="flex items-center gap-2 mb-1.5 flex-wrap">
        <span className="inline-block text-[10px] font-semibold rounded px-1.5 py-0.5 bg-neutral-12 text-neutral-4">
          Rubric saved
        </span>
        <span className="font-mono text-neutral-6 text-[10px]">
          {fmtDate(entry.timestamp)}
        </span>
        <span className="font-mono text-neutral-5 text-[10px]">
          {entry.previous_version} → {entry.new_version}
        </span>
      </div>
      {entry.note && (
        <p className="text-neutral-3 leading-snug truncate">
          &ldquo;{entry.note}&rdquo;
        </p>
      )}
      <p className="text-neutral-6 mt-1 font-mono text-[10px]">{entry.steward}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Panel
// ---------------------------------------------------------------------------

interface HistoryPanelProps {
  product: string;
  apiBaseUrl: string;
}

export default function HistoryPanel({ product, apiBaseUrl }: HistoryPanelProps) {
  const [open, setOpen] = useState(false);
  const [events, setEvents] = useState<HistoryEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetch(
        `${apiBaseUrl}/api/products/${encodeURIComponent(product)}/audit-log?limit=50`,
        { cache: "no-store" },
      )
        .then((r) => (r.ok ? r.json() : { entries: [] }))
        .then((d) => (d.entries ?? []) as AuditEntry[])
        .catch(() => [] as AuditEntry[]),
      fetch(
        `${apiBaseUrl}/api/products/${encodeURIComponent(product)}/rubric-audit?limit=50`,
        { cache: "no-store" },
      )
        .then((r) => (r.ok ? r.json() : { entries: [] }))
        .then((d) => (d.entries ?? []) as RubricAuditRecord[])
        .catch(() => [] as RubricAuditRecord[]),
    ]).then(([statusChanges, rubricSaves]) => {
      const merged: HistoryEvent[] = [
        ...statusChanges.map(
          (e): StatusEvent => ({ kind: "status_change", timestamp: e.timestamp, entry: e }),
        ),
        ...rubricSaves.map(
          (e): RubricEvent => ({ kind: "rubric_save", timestamp: e.timestamp, entry: e }),
        ),
      ].sort(
        (a, b) =>
          new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
      );
      setEvents(merged);
      setLoading(false);
    });
  }, [product, apiBaseUrl]);

  const visible = events.slice(0, visibleCount);
  const hasMore = visibleCount < events.length;

  return (
    <div
      data-testid="history-panel"
      className="bg-white border border-neutral-11 rounded-lg shadow-sm overflow-hidden"
    >
      <div className="px-5 py-4 flex items-center justify-between border-b border-neutral-11">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-neutral-1">
            Recent History
          </h2>
          {!loading && events.length > 0 && (
            <span className="text-xs text-neutral-6 font-mono">
              ({events.length})
            </span>
          )}
        </div>
        {!loading && events.length > 0 && (
          <button
            type="button"
            data-testid="history-toggle"
            onClick={() => setOpen((v) => !v)}
            className="text-xs text-neutral-6 hover:text-neutral-3 underline"
          >
            {open ? "Hide" : "Show"}
          </button>
        )}
      </div>

      {loading && (
        <p className="px-5 py-4 text-xs text-neutral-6 italic">Loading…</p>
      )}

      {!loading && events.length === 0 && (
        <p
          data-testid="history-empty"
          className="px-5 py-4 text-xs text-neutral-6 italic"
        >
          No history yet.
        </p>
      )}

      {!loading && open && events.length > 0 && (
        <div className="px-5 py-4 flex flex-col gap-2">
          {visible.map((ev, i) =>
            ev.kind === "status_change" ? (
              <StatusEntry
                key={`${ev.entry.id ?? i}-status`}
                entry={ev.entry}
              />
            ) : (
              <RubricEntry
                key={`${ev.entry.timestamp}-${ev.entry.new_version}`}
                entry={ev.entry}
              />
            ),
          )}
          {hasMore && (
            <button
              type="button"
              data-testid="history-load-more"
              onClick={() => setVisibleCount((c) => c + PAGE_SIZE)}
              className="mt-1 text-xs text-neutral-6 hover:text-neutral-3 underline self-start"
            >
              Load more
            </button>
          )}
        </div>
      )}
    </div>
  );
}
