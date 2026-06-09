// History page — unified chronological feed of rubric saves and candidate
// status changes (AC3 of the production-decision slice).
// Server component: fetches both event streams at render time, merges them,
// and passes the sorted result to the pure HistoryFeed renderer.
// ASSUMES: NEXT_PUBLIC_API_URL is set; falls back to 127.0.0.1:8000 for local dev.

import AppShell from "@/components/AppShell";
import { resolveEnvLabel } from "@/lib/env";
import { AuditEntry, RubricAuditRecord } from "@/lib/promotion";

function apiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
}

// ---------------------------------------------------------------------------
// Wire types shared by both event sources
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Fetches — best-effort, degrade to empty on any failure
// ---------------------------------------------------------------------------

async function fetchStatusChanges(
  base: string,
  product: string,
): Promise<AuditEntry[]> {
  try {
    const res = await fetch(
      `${base}/api/products/${encodeURIComponent(product)}/audit-log?limit=50`,
      { cache: "no-store" },
    );
    if (!res.ok) return [];
    const data = await res.json();
    return (data.entries ?? []) as AuditEntry[];
  } catch {
    return [];
  }
}

async function fetchRubricSaves(
  base: string,
  product: string,
): Promise<RubricAuditRecord[]> {
  try {
    const res = await fetch(
      `${base}/api/products/${encodeURIComponent(product)}/rubric-audit?limit=50`,
      { cache: "no-store" },
    );
    if (!res.ok) return [];
    const data = await res.json();
    return (data.entries ?? []) as RubricAuditRecord[];
  } catch {
    return [];
  }
}

async function fetchCurrentRubricVersion(
  base: string,
  product: string,
): Promise<string> {
  try {
    const res = await fetch(
      `${base}/api/products/${encodeURIComponent(product)}/rubric`,
      { cache: "no-store" },
    );
    if (!res.ok) return "—";
    const data = await res.json();
    return data.version ?? "—";
  } catch {
    return "—";
  }
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

interface HistoryPageProps {
  searchParams: Promise<{ product?: string }>;
}

export default async function HistoryPage({ searchParams }: HistoryPageProps) {
  const { product = "mli" } = await searchParams;
  const base = apiBaseUrl();

  const [statusChanges, rubricSaves, rubricVersion] = await Promise.all([
    fetchStatusChanges(base, product),
    fetchRubricSaves(base, product),
    fetchCurrentRubricVersion(base, product),
  ]);

  // Merge into a single event list and sort newest-first.
  const events: HistoryEvent[] = [
    ...statusChanges.map(
      (e): StatusEvent => ({ kind: "status_change", timestamp: e.timestamp, entry: e }),
    ),
    ...rubricSaves.map(
      (e): RubricEvent => ({ kind: "rubric_save", timestamp: e.timestamp, entry: e }),
    ),
  ].sort((a, b) => {
    const ta = new Date(a.timestamp).getTime();
    const tb = new Date(b.timestamp).getTime();
    return tb - ta; // newest first
  });

  return (
    <AppShell
      env={resolveEnvLabel()}
      rubricVersion={rubricVersion}
      product={{ id: product, name: product.toUpperCase() }}
      activeTab="history"
    >
      <div className="max-w-2xl mx-auto px-5 py-8">
        <h1 className="text-sm font-semibold text-neutral-1 mb-1">History</h1>
        <p className="text-xs text-neutral-6 mb-6">
          Rubric saves and candidate status changes, newest first.
        </p>
        {events.length === 0 ? (
          <p className="text-xs text-neutral-6 italic">
            No history yet — promote a candidate or save the rubric to see
            events here.
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            {events.map((ev, i) =>
              ev.kind === "status_change" ? (
                <StatusChangeCard key={ev.entry.id ?? i} entry={ev.entry} />
              ) : (
                <RubricSaveCard
                  key={`${ev.entry.timestamp}-${ev.entry.new_version}`}
                  entry={ev.entry}
                />
              ),
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
}

// ---------------------------------------------------------------------------
// Event card components
// ---------------------------------------------------------------------------

const ACTION_LABELS: Record<string, string> = {
  promote_primary: "Promoted to Primary",
  promote_fallback: "Set as Fallback",
  reject: "Rejected",
  revert: "Reverted",
};

const TIER_LABELS: Record<string, string> = {
  tier_1: "T1 · Classification & Routing",
  tier_2: "T2 · Structured Generation",
  tier_3: "T3 · Synthesis",
};

function fmtDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function StatusChangeCard({ entry }: { entry: AuditEntry }) {
  const label = ACTION_LABELS[entry.action] ?? entry.action;
  const isReject = entry.action === "reject";
  const pillCls = isReject
    ? "bg-light-red text-warm-red"
    : "bg-light-green text-green";

  return (
    <div
      data-testid="history-status-change"
      className="border border-neutral-11 rounded-lg p-3.5 bg-white text-xs"
    >
      <div className="flex items-center gap-2 mb-2">
        <span
          className={`inline-block text-[10px] font-semibold rounded px-1.5 py-0.5 ${pillCls}`}
        >
          {label}
        </span>
        <span className="font-mono text-neutral-6 text-[10px]">
          {fmtDate(entry.timestamp)}
        </span>
      </div>
      <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[11px] mb-2">
        <span className="text-neutral-6">Candidate</span>
        <span className="font-mono text-neutral-2">{entry.candidate_deployment}</span>
        <span className="text-neutral-6">Tier</span>
        <span className="text-neutral-3">{TIER_LABELS[entry.tier_id] ?? entry.tier_id}</span>
        <span className="text-neutral-6">Rubric</span>
        <span className="font-mono text-neutral-5">{entry.rubric_version_at_time}</span>
      </div>
      <p className="text-neutral-2 leading-snug">"{entry.rationale}"</p>
      <p className="text-neutral-6 mt-1.5 font-mono text-[10px]">{entry.actor}</p>
    </div>
  );
}

function RubricSaveCard({ entry }: { entry: RubricAuditRecord }) {
  return (
    <div
      data-testid="history-rubric-save"
      className="border border-neutral-11 rounded-lg p-3.5 bg-white text-xs"
    >
      <div className="flex items-center gap-2 mb-2">
        <span className="inline-block text-[10px] font-semibold rounded px-1.5 py-0.5 bg-neutral-12 text-neutral-4">
          Rubric saved
        </span>
        <span className="font-mono text-neutral-6 text-[10px]">
          {fmtDate(entry.timestamp)}
        </span>
      </div>
      <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[11px] mb-2">
        <span className="text-neutral-6">Version</span>
        <span className="font-mono text-neutral-2">
          {entry.previous_version} → {entry.new_version}
        </span>
      </div>
      {entry.note && (
        <p className="text-neutral-2 leading-snug">"{entry.note}"</p>
      )}
      <p className="text-neutral-6 mt-1.5 font-mono text-[10px]">{entry.steward}</p>
    </div>
  );
}
