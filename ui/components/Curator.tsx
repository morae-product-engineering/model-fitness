"use client";

// Curator page body (MFP-76). Client component — all data fetching and
// interaction happens here so the page server component stays thin.
//
// Consumes MFP-75 API endpoints:
//   GET  /api/products/{product}/datasets/{tier_id}
//   POST /api/products/{product}/datasets/{tier_id}/examples
//   GET  /api/products/{product}/judge-queue
//   POST /api/products/{product}/judge-queue/{sample_id}/mark

import { useEffect, useRef, useState } from "react";
import Btn from "./primitives/Btn";

// ---------------------------------------------------------------------------
// Wire types (mirrors MFP-75 response models)
// ---------------------------------------------------------------------------

interface DatasetExample {
  id: string;
  input: string | Record<string, unknown>;
  expected: unknown;
  tags: string[];
  metadata: Record<string, unknown>;
}

interface JudgeSample {
  sample_id: string;
  dimension_id: string;
  candidate_id: string;
  judge_score: number;
  judge_reasoning: string;
  judge_confidence: string;
  status: string;
  decision: string | null;
  note: string | null;
}

// ---------------------------------------------------------------------------
// Root component
// ---------------------------------------------------------------------------

interface CuratorProps {
  product: string;
  tierId: string;
  apiBaseUrl: string;
}

type Tab = "datasets" | "queue";

export default function Curator({ product, tierId, apiBaseUrl }: CuratorProps) {
  const [activeTab, setActiveTab] = useState<Tab>("datasets");
  const [examples, setExamples] = useState<DatasetExample[]>([]);
  const [queue, setQueue] = useState<JudgeSample[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    fetch(
      `${apiBaseUrl}/api/products/${encodeURIComponent(product)}/datasets/${encodeURIComponent(tierId)}`,
      { cache: "no-store" },
    )
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => { if (data) setExamples(data.examples ?? []); })
      .catch(() => {});
  }, [apiBaseUrl, product, tierId]);

  useEffect(() => {
    if (activeTab !== "queue") return;
    fetch(
      `${apiBaseUrl}/api/products/${encodeURIComponent(product)}/judge-queue`,
      { cache: "no-store" },
    )
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => { if (data) setQueue(data.samples ?? []); })
      .catch(() => {});
  }, [apiBaseUrl, product, activeTab]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(t);
  }, [toast]);

  async function handleAddExample(input: string, expectedRaw: string) {
    let expected: unknown;
    try { expected = JSON.parse(expectedRaw); } catch { expected = expectedRaw; }

    const body: DatasetExample = {
      id: `ex-${Date.now()}`,
      input,
      expected,
      tags: [],
      metadata: {},
    };

    const res = await fetch(
      `${apiBaseUrl}/api/products/${encodeURIComponent(product)}/datasets/${encodeURIComponent(tierId)}/examples`,
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
    );
    if (res.ok) {
      const created = (await res.json()) as DatasetExample;
      setExamples((prev) => [...prev, created]);
      setToast("example added · staged for review");
    }
    setShowModal(false);
  }

  async function handleMark(sampleId: string, decision: "agree" | "disagree") {
    const res = await fetch(
      `${apiBaseUrl}/api/products/${encodeURIComponent(product)}/judge-queue/${encodeURIComponent(sampleId)}/mark`,
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision }) },
    );
    if (res.ok) {
      setQueue((prev) =>
        prev.map((s) =>
          s.sample_id === sampleId ? { ...s, status: "reviewed", decision } : s,
        ),
      );
      setToast(`agree · queued for steward review`);
    }
  }

  return (
    <div style={{ padding: 24, maxWidth: 1480, margin: "0 auto" }}>
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: "var(--neutral-6)", letterSpacing: 0.4, textTransform: "uppercase" }}>
          Curator · golden datasets & judge calibration
        </div>
        <h1 style={{ margin: "6px 0 4px", fontSize: 26, letterSpacing: "-0.01em" }}>Dataset stewardship</h1>
        <p style={{ margin: 0, fontSize: 13, color: "var(--neutral-6)" }}>
          Add new examples, review LLM-judge sample queue, flag disputed scores.
        </p>
      </div>

      {/* Sub-tabs */}
      <div style={{ display: "flex", gap: 6, borderBottom: "1px solid var(--neutral-11)", marginBottom: 14 }}>
        <SubTab active={activeTab === "datasets"} onClick={() => setActiveTab("datasets")}>
          Golden datasets
        </SubTab>
        <SubTab active={activeTab === "queue"} data-testid="curator-tab-queue" onClick={() => setActiveTab("queue")}>
          Judge sample queue
        </SubTab>
      </div>

      {activeTab === "datasets" && (
        <DatasetTab
          examples={examples}
          onAdd={() => setShowModal(true)}
        />
      )}

      {activeTab === "queue" && (
        <QueueTab queue={queue} onMark={handleMark} />
      )}

      {showModal && (
        <AddExampleModal
          onClose={() => setShowModal(false)}
          onSubmit={handleAddExample}
        />
      )}

      {toast && (
        <div
          data-testid="toast"
          style={{
            position: "fixed", bottom: 24, left: "50%", transform: "translateX(-50%)",
            background: "var(--neutral-1)", color: "#fff", padding: "10px 18px",
            borderRadius: 8, fontSize: 13, fontWeight: 500, zIndex: 200,
            boxShadow: "var(--shadow-md)", whiteSpace: "nowrap",
          }}
        >
          {toast}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-tab button
// ---------------------------------------------------------------------------

function SubTab({
  active,
  onClick,
  children,
  ...rest
}: { active: boolean; onClick: () => void; children: React.ReactNode; [k: string]: unknown }) {
  return (
    <button
      {...rest}
      onClick={onClick}
      style={{
        position: "relative", padding: "10px 14px", background: "transparent",
        border: "none", cursor: "pointer", fontFamily: "inherit",
        fontSize: 13, fontWeight: active ? 600 : 500,
        color: active ? "var(--neutral-1)" : "var(--neutral-6)",
      }}
    >
      {children}
      {active && (
        <span style={{ position: "absolute", left: 14, right: 14, bottom: -1, height: 2, background: "var(--neutral-1)" }} />
      )}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Datasets tab
// ---------------------------------------------------------------------------

function DatasetTab({ examples, onAdd }: { examples: DatasetExample[]; onAdd: () => void }) {
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 10 }}>
        <Btn variant="default" size="sm" data-testid="curator-add-example-btn" onClick={onAdd}>
          Add example
        </Btn>
      </div>
      <table
        data-testid="curator-dataset-table"
        style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, background: "#fff", border: "1px solid var(--neutral-11)", borderRadius: 8 }}
      >
        <thead>
          <tr style={{ background: "var(--neutral-13)", borderBottom: "1px solid var(--neutral-11)" }}>
            <th style={th()}>ID</th>
            <th style={{ ...th(), textAlign: "left" }}>Input</th>
            <th style={th()}>Tags</th>
          </tr>
        </thead>
        <tbody>
          {examples.length === 0 ? (
            <tr>
              <td colSpan={3} style={{ padding: "24px 12px", textAlign: "center", color: "var(--neutral-6)", fontSize: 12 }}>
                No examples yet
              </td>
            </tr>
          ) : (
            examples.map((ex) => (
              <tr key={ex.id} style={{ borderBottom: "1px solid var(--neutral-12)" }}>
                <td style={{ ...td(), fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--neutral-6)" }}>{ex.id}</td>
                <td style={td()}>{typeof ex.input === "string" ? ex.input : JSON.stringify(ex.input)}</td>
                <td style={td()}>{ex.tags.join(", ")}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Queue tab
// ---------------------------------------------------------------------------

function QueueTab({
  queue,
  onMark,
}: {
  queue: JudgeSample[];
  onMark: (id: string, decision: "agree" | "disagree") => void;
}) {
  return (
    <div style={{ background: "#fff", border: "1px solid var(--neutral-11)", borderRadius: 8, overflow: "hidden" }}>
      {queue.length === 0 ? (
        <p style={{ padding: "24px 16px", textAlign: "center", color: "var(--neutral-6)", fontSize: 12, margin: 0 }}>
          No samples in queue
        </p>
      ) : (
        queue.map((sample) => (
          <JudgeRow key={sample.sample_id} sample={sample} onMark={onMark} />
        ))
      )}
    </div>
  );
}

function JudgeRow({
  sample,
  onMark,
}: {
  sample: JudgeSample;
  onMark: (id: string, decision: "agree" | "disagree") => void;
}) {
  const agreed = sample.decision === "agree";
  const disputed = sample.decision === "disagree";
  const statusLabel = agreed ? "Agreed" : disputed ? "Disputed" : "Pending";
  const statusColor = agreed ? "var(--green)" : disputed ? "var(--warm-red)" : "var(--neutral-6)";
  const statusBg = agreed ? "var(--light-green)" : disputed ? "var(--light-red)" : "var(--neutral-12)";

  return (
    <div
      data-testid="curator-queue-row"
      style={{
        display: "grid",
        gridTemplateColumns: "1fr auto auto auto",
        gap: 12, alignItems: "center",
        padding: "12px 16px",
        borderBottom: "1px solid var(--neutral-12)",
      }}
    >
      <div>
        <div style={{ fontSize: 12, fontWeight: 500, color: "var(--neutral-1)" }}>{sample.candidate_id}</div>
        <div style={{ fontSize: 11, color: "var(--neutral-6)", fontFamily: "var(--font-mono)", marginTop: 2 }}>
          {sample.dimension_id} · score {sample.judge_score.toFixed(2)} · {sample.judge_confidence}
        </div>
      </div>
      <span
        data-testid="curator-queue-status"
        style={{
          display: "inline-flex", alignItems: "center", padding: "2px 8px",
          borderRadius: 4, fontSize: 11, fontWeight: 600,
          background: statusBg, color: statusColor,
        }}
      >
        {statusLabel}
      </span>
      <Btn
        variant={agreed ? "default" : "outline"}
        size="sm"
        data-testid="curator-queue-agree"
        onClick={() => onMark(sample.sample_id, "agree")}
      >
        Agree
      </Btn>
      <Btn
        variant={disputed ? "destructive" : "outline"}
        size="sm"
        onClick={() => onMark(sample.sample_id, "disagree")}
      >
        Dispute
      </Btn>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Add-example modal
// ---------------------------------------------------------------------------

function AddExampleModal({
  onClose,
  onSubmit,
}: {
  onClose: () => void;
  onSubmit: (input: string, expected: string) => Promise<void>;
}) {
  const [input, setInput] = useState("");
  const [expected, setExpected] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const firstRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { firstRef.current?.focus(); }, []);

  const valid = input.trim().length > 0 && expected.trim().length > 0;

  async function handleSubmit() {
    if (!valid) return;
    setSubmitting(true);
    await onSubmit(input.trim(), expected.trim());
    setSubmitting(false);
  }

  return (
    <div
      data-testid="curator-add-example-modal"
      style={{
        position: "fixed", inset: 0, zIndex: 50,
        background: "rgba(0,0,0,0.3)",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        style={{
          background: "#fff", borderRadius: 10, padding: 24, width: 580,
          maxWidth: "90vw", boxShadow: "var(--shadow-lg)",
        }}
      >
        <h2 style={{ margin: "0 0 4px", fontSize: 16, fontWeight: 600 }}>Add golden example</h2>
        <p style={{ margin: "0 0 16px", fontSize: 13, color: "var(--neutral-6)" }}>
          Schema-validated. Staged for PR review.
        </p>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <Field label="Task prompt (required)">
            <textarea
              ref={firstRef}
              data-testid="add-example-input"
              rows={3}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Summarise the key obligations…"
              style={textareaStyle()}
            />
          </Field>
          <Field label="Golden answer JSON (required)">
            <textarea
              data-testid="add-example-expected"
              rows={4}
              value={expected}
              onChange={(e) => setExpected(e.target.value)}
              placeholder='{"themes": [...], "summary": "..."}'
              style={{ ...textareaStyle(), fontFamily: "var(--font-mono)", fontSize: 12 }}
            />
          </Field>
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
          <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
          <Btn
            variant="default"
            data-testid="add-example-submit"
            disabled={!valid || submitting}
            onClick={handleSubmit}
          >
            Validate & stage
          </Btn>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <label style={{ fontSize: 11, fontWeight: 600, color: "var(--neutral-3)", letterSpacing: 0.2 }}>{label}</label>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Style helpers
// ---------------------------------------------------------------------------

function th() {
  return { padding: "8px 12px", textAlign: "center" as const, fontSize: 11, fontWeight: 600, color: "var(--neutral-5)", whiteSpace: "nowrap" as const };
}

function td() {
  return { padding: "10px 12px", verticalAlign: "middle" as const };
}

function textareaStyle() {
  return {
    padding: 10, fontSize: 13, border: "1px solid var(--neutral-10)",
    borderRadius: 4, background: "#fff", fontFamily: "inherit",
    color: "var(--neutral-1)", width: "100%", boxSizing: "border-box" as const,
    outline: "none", resize: "vertical" as const,
  };
}
