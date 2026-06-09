"use client";

// Rubric editor — weight inputs, debounced preview, and inline save bar (MLI-195).
//
// Design decisions (all load-bearing for the e2e acceptance test MLI-191):
//
// 1. ALL THREE tiers rendered at once (no tier picker) so the e2e can locate
//    tier_3 weight inputs without navigating. Each tier is its own stacked
//    section.
//
// 2. Save is INLINE — no modal. The e2e fills `save-note` and clicks
//    `save-button` without opening a modal; both are always in the DOM.
//
// 3. Draft dims have no editable weight input (the Tier validator requires
//    draft weight == 0). They render de-emphasised with the "Draft —
//    activates in Slice 6" label, matching CandidateDetail.tsx's treatment.
//
// 4. Coverage and normalisation caveats (P9 / MLI-190 boundary):
//    - normalization_stale_dimensions → banner per tier, `data-testid="normalization-stale-${tier_id}"`
//    - coverage_complete=false → `data-testid="coverage-incomplete"` marker on the row,
//      delta de-emphasised with a warning chip.

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type {
  PreviewResponse,
  PreviewTier,
  RawRubric,
  RawTier,
  WirePreviewResponse,
} from "@/lib/rubric";
import {
  buildCandidateRubric,
  dimWeightNumber,
  parsePreview,
} from "@/lib/rubric";
import Btn from "@/components/primitives/Btn";
import Chip from "@/components/primitives/Chip";
import Panel from "@/components/primitives/Panel";
import {
  IconAlert,
  IconCheck,
  IconInfo,
  IconRefresh,
} from "@/components/primitives/icons";

interface RubricEditorProps {
  product: string;
  apiBaseUrl: string;
  initialRubric: RawRubric;
  version: string;
}

// Steward identity sent on the X-Steward-Identity header. Populated by the
// deployment from env when SSO lands; until then it falls back to the SINGLE
// reconciled placeholder (MLI-365) — the same string the API uses server-side
// (rubric_write.PLACEHOLDER_STEWARD), so there is one placeholder identity
// across the stack rather than two divergent ones.
const STEWARD_IDENTITY =
  process.env.NEXT_PUBLIC_STEWARD_IDENTITY ??
  "Unknown Steward <steward@unknown.local>";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build the initial weights map from active dimensions in the rubric. */
function initialWeights(rubric: RawRubric): Record<string, number> {
  const out: Record<string, number> = {};
  for (const tier of rubric.tiers) {
    for (const dim of tier.dimensions) {
      if (dim.status === "active") {
        out[`${tier.id}.${dim.id}`] = dimWeightNumber(dim);
      }
    }
  }
  return out;
}

/** Sum of active-dimension weights for a tier given the current weights map. */
function tierActiveSum(tier: RawTier, weights: Record<string, number>): number {
  return tier.dimensions
    .filter((d) => d.status === "active")
    .reduce((s, d) => s + (weights[`${tier.id}.${d.id}`] ?? 0), 0);
}

/** True when all tiers have active-weight sum in (0, 100]. */
function allTiersValid(
  rubric: RawRubric,
  weights: Record<string, number>,
): boolean {
  return rubric.tiers.every((tier) => {
    const sum = tierActiveSum(tier, weights);
    return sum > 0 && sum <= 100;
  });
}

/** True when weights differ from the initial rubric values. */
function hasEdits(
  rubric: RawRubric,
  weights: Record<string, number>,
): boolean {
  for (const tier of rubric.tiers) {
    for (const dim of tier.dimensions) {
      if (dim.status !== "active") continue;
      const key = `${tier.id}.${dim.id}`;
      if ((weights[key] ?? 0) !== dimWeightNumber(dim)) return true;
    }
  }
  return false;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function WeightRow({
  tierId,
  dim,
  value,
  onChange,
}: {
  tierId: string;
  dim: RawTier["dimensions"][number];
  value: number;
  onChange: (v: number) => void;
}) {
  const key = `${tierId}.${dim.id}`;
  const isDraft = dim.status === "draft";

  if (isDraft) {
    return (
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr auto",
          gap: 10,
          alignItems: "start",
          padding: "8px 0",
          borderBottom: "1px solid var(--neutral-12)",
          opacity: 0.45,
        }}
      >
        <div style={{ minWidth: 0 }}>
          <div
            style={{
              fontSize: 12,
              fontWeight: 500,
              color: "var(--neutral-3)",
            }}
          >
            {dim.name}
          </div>
          <div style={{ fontSize: 11, color: "var(--neutral-6)", marginTop: 2 }}>
            {dim.description}
          </div>
          <span
            data-testid="dimension-draft-label"
            style={{
              fontSize: 10,
              color: "var(--neutral-6)",
              fontStyle: "italic",
              display: "block",
              marginTop: 3,
            }}
          >
            Draft — activates in Slice 6
          </span>
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 4,
            paddingTop: 2,
          }}
        >
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 12,
              color: "var(--neutral-7)",
            }}
          >
            0%
          </span>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr auto",
        gap: 10,
        alignItems: "start",
        padding: "8px 0",
        borderBottom: "1px solid var(--neutral-12)",
      }}
    >
      <div style={{ minWidth: 0 }}>
        <div
          style={{ fontSize: 12, fontWeight: 500, color: "var(--neutral-1)" }}
        >
          {dim.name}
        </div>
        <div style={{ fontSize: 11, color: "var(--neutral-6)", marginTop: 2 }}>
          {dim.description}
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
        <input
          type="number"
          min={0}
          max={100}
          data-testid={`weight-input-${key}`}
          value={value}
          onChange={(e) => {
            const n = parseInt(e.target.value || "0", 10);
            onChange(isNaN(n) ? 0 : Math.max(0, Math.min(100, n)));
          }}
          style={{
            width: 52,
            height: 28,
            padding: "0 4px",
            border: "1px solid var(--neutral-10)",
            borderRadius: 4,
            fontSize: 12,
            textAlign: "right",
            fontFamily: "var(--font-mono)",
            color: "var(--neutral-1)",
            background: "#fff",
          }}
        />
        <span style={{ fontSize: 11, color: "var(--neutral-6)" }}>%</span>
      </div>
    </div>
  );
}

function TierSection({
  tier,
  weights,
  previewTier,
  onWeightChange,
}: {
  tier: RawTier;
  weights: Record<string, number>;
  previewTier: PreviewTier | null;
  onWeightChange: (key: string, v: number) => void;
}) {
  const sum = tierActiveSum(tier, weights);
  const sumOk = sum > 0 && sum <= 100;

  return (
    <Panel padding={0} style={{ marginBottom: 16 }}>
      {/* Tier header */}
      <div
        style={{
          padding: "12px 16px",
          borderBottom: "1px solid var(--neutral-11)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 8,
        }}
      >
        <span
          style={{ fontSize: 13, fontWeight: 600, color: "var(--neutral-1)" }}
        >
          {tier.name}
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 11, color: "var(--neutral-6)" }}>
            Σ active weights
          </span>
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 13,
              fontWeight: 600,
              color: sumOk ? "var(--green)" : "var(--warm-red)",
              background: sumOk ? "var(--light-green)" : "var(--light-red)",
              padding: "2px 8px",
              borderRadius: 4,
            }}
          >
            {sum}%
          </span>
        </div>
      </div>

      {/* Dimension rows */}
      <div style={{ padding: "4px 16px 12px" }}>
        {tier.dimensions.map((dim) => (
          <WeightRow
            key={dim.id}
            tierId={tier.id}
            dim={dim}
            value={
              dim.status === "active"
                ? (weights[`${tier.id}.${dim.id}`] ?? 0)
                : 0
            }
            onChange={(v) => onWeightChange(`${tier.id}.${dim.id}`, v)}
          />
        ))}
      </div>

      {/* Impact preview panel */}
      {previewTier && (
        <ImpactPanel tier={tier} previewTier={previewTier} />
      )}
    </Panel>
  );
}

function ImpactPanel({
  tier,
  previewTier,
}: {
  tier: RawTier;
  previewTier: PreviewTier;
}) {
  const hasStale = previewTier.normalization_stale_dimensions.length > 0;

  return (
    <div
      data-testid={`impact-preview-${tier.id}`}
      style={{
        borderTop: "1px solid var(--neutral-11)",
        padding: "12px 16px",
      }}
    >
      <div
        style={{
          fontSize: 11,
          fontWeight: 600,
          color: "var(--neutral-6)",
          letterSpacing: 0.4,
          textTransform: "uppercase",
          marginBottom: 10,
        }}
      >
        Impact preview · {tier.name}
      </div>

      {/* Normalisation-staleness caveat (load-bearing per P9 / MLI-190) */}
      {hasStale && (
        <div
          data-testid={`normalization-stale-${tier.id}`}
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: 8,
            background: "var(--light-yellow)",
            color: "#8a6600",
            borderRadius: 6,
            padding: "8px 12px",
            fontSize: 12,
            marginBottom: 10,
          }}
        >
          <IconAlert size={14} color="#8a6600" style={{ flexShrink: 0, marginTop: 1 }} />
          <span>
            <strong>Normalisation may be stale</strong> for:{" "}
            {previewTier.normalization_stale_dimensions.join(", ")}.{" "}
            These dimensions changed direction or evaluator config — the delta
            may be misleading because normalisation was not re-applied.
          </span>
        </div>
      )}

      {/* Candidate delta rows */}
      <div>
        {previewTier.candidates.map((delta) => {
          const rankChanged = delta.rank_after !== delta.rank_before;
          const shift = delta.rank_before - delta.rank_after; // positive = moved up
          const incomplete = !delta.coverage_complete;

          return (
            <div
              key={delta.candidate}
              data-testid={rankChanged ? "ranking-change-row" : undefined}
              style={{
                display: "grid",
                gridTemplateColumns: "24px 1fr auto auto",
                gap: 8,
                alignItems: "center",
                padding: "6px 0",
                borderBottom: "1px solid var(--neutral-12)",
              }}
            >
              {/* Rank */}
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: 12,
                  color: "var(--neutral-6)",
                }}
              >
                {delta.rank_after}
              </span>

              {/* Name + incomplete coverage marker */}
              <div style={{ minWidth: 0 }}>
                <div
                  style={{
                    fontSize: 12,
                    fontWeight: 500,
                    color: "var(--neutral-1)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {delta.candidate}
                </div>
                {incomplete && (
                  <span
                    data-testid="coverage-incomplete"
                    title="Incomplete coverage: not all active dimensions were measured for this candidate. The delta may partly reflect missing data rather than weight changes."
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 3,
                      fontSize: 10,
                      color: "var(--neutral-6)",
                      background: "var(--neutral-12)",
                      borderRadius: 3,
                      padding: "1px 5px",
                      marginTop: 2,
                    }}
                  >
                    <IconInfo size={9} color="var(--neutral-6)" />
                    incomplete coverage
                  </span>
                )}
              </div>

              {/* Rank shift indicator */}
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: 11,
                  fontWeight: 600,
                  color:
                    shift > 0
                      ? "var(--green)"
                      : shift < 0
                        ? "var(--warm-red)"
                        : "var(--neutral-7)",
                }}
              >
                {shift > 0 ? "↑" : shift < 0 ? "↓" : "·"}
                {shift !== 0 ? Math.abs(shift) : ""}
              </span>

              {/* Score before → after */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 4,
                  opacity: incomplete ? 0.6 : 1,
                }}
              >
                {incomplete ? (
                  <Chip tone="warn" style={{ fontSize: 10 }}>
                    {delta.score_before.toFixed(1)}→{delta.score_after.toFixed(1)}
                  </Chip>
                ) : (
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: 12,
                      fontWeight: 600,
                      color: "var(--neutral-1)",
                    }}
                  >
                    {delta.score_before.toFixed(1)}→{delta.score_after.toFixed(1)}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function RubricEditor({
  product,
  apiBaseUrl,
  initialRubric,
  version,
}: RubricEditorProps) {
  const router = useRouter();

  // Weights state — keyed by "${tier.id}.${dim.id}" for active dims.
  const [weights, setWeights] = useState<Record<string, number>>(() =>
    initialWeights(initialRubric),
  );

  // Reset to the new baseline whenever version changes (after a successful save
  // router.refresh() re-renders the server component with new props).
  useEffect(() => {
    setWeights(initialWeights(initialRubric));
  }, [version]); // eslint-disable-line react-hooks/exhaustive-deps
  // ASSUMES: initialRubric is consistent with version; both arrive together
  // from the server component after router.refresh().

  // Preview state
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  // Debounce ref — cancel in-flight preview when weights change again.
  const abortRef = useRef<AbortController | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const triggerPreview = useCallback(
    (currentWeights: Record<string, number>) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(async () => {
        if (abortRef.current) abortRef.current.abort();
        const ac = new AbortController();
        abortRef.current = ac;

        setPreviewing(true);
        setPreviewError(null);

        try {
          const candidateRubric = buildCandidateRubric(
            initialRubric,
            currentWeights,
          );
          const res = await fetch(
            `${apiBaseUrl}/api/products/${encodeURIComponent(product)}/rubric/preview-impact`,
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ rubric: candidateRubric }),
              signal: ac.signal,
            },
          );
          if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            setPreviewError(
              typeof err.detail === "string"
                ? err.detail
                : `Preview error ${res.status}`,
            );
            setPreview(null);
          } else {
            const wire: WirePreviewResponse = await res.json();
            setPreview(parsePreview(wire));
          }
        } catch (err) {
          if ((err as DOMException).name === "AbortError") return;
          setPreviewError(
            err instanceof Error ? err.message : "Preview unavailable",
          );
          setPreview(null);
        } finally {
          setPreviewing(false);
        }
      }, 400);
    },
    [apiBaseUrl, initialRubric, product],
  );

  // Weight change handler — update state + trigger preview.
  const handleWeightChange = useCallback(
    (key: string, value: number) => {
      setWeights((prev) => {
        const next = { ...prev, [key]: value };
        triggerPreview(next);
        return next;
      });
    },
    [triggerPreview],
  );

  // Save bar state
  const [saveNote, setSaveNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [saveConflict, setSaveConflict] = useState<string | null>(null);
  const [saveErrors, setSaveErrors] = useState<string | null>(null);
  const [saveGenericError, setSaveGenericError] = useState<string | null>(null);

  // Auto-dismiss toast after 3 s.
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(t);
  }, [toast]);

  const dirty = hasEdits(initialRubric, weights);
  const allValid = allTiersValid(initialRubric, weights);
  const canSave = dirty && allValid && !saving;

  const handleReset = useCallback(() => {
    setWeights(initialWeights(initialRubric));
    setPreview(null);
    setPreviewError(null);
  }, [initialRubric]);

  const handleSave = useCallback(async () => {
    if (!canSave) return;
    setSaving(true);
    setSaveConflict(null);
    setSaveErrors(null);
    setSaveGenericError(null);

    try {
      const candidateRubric = buildCandidateRubric(initialRubric, weights);
      const res = await fetch(
        `${apiBaseUrl}/api/products/${encodeURIComponent(product)}/rubric`,
        {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            "X-Steward-Identity": STEWARD_IDENTITY,
          },
          body: JSON.stringify({
            rubric: candidateRubric,
            expected_version: version,
            note: saveNote || undefined,
          }),
        },
      );

      if (res.status === 200) {
        const data = await res.json();
        const newVersion: string = data.new_version;
        // Notify VersionBadge BEFORE setting the toast so both update in the same React render
        window.dispatchEvent(
          new CustomEvent("rubric-saved", { detail: { version: newVersion } }),
        );
        setToast(`Rubric saved · ${newVersion}`);
        setSaveNote("");
        router.refresh();
      } else if (res.status === 409) {
        const data = await res.json();
        setSaveConflict(
          `The rubric was updated by another steward while you were editing. Current version is now ${data.current_version}. Reload to see the latest rubric before saving.`,
        );
      } else if (res.status === 422) {
        const data = await res.json();
        const msgs: string[] = (data.detail ?? []).map(
          (e: { loc: (string | number)[]; msg: string }) =>
            `${e.loc.join(".")}: ${e.msg}`,
        );
        setSaveErrors(msgs.join(" | ") || "Validation error");
      } else {
        setSaveGenericError(`Save failed (${res.status} ${res.statusText})`);
      }
    } catch (err) {
      setSaveGenericError(
        err instanceof Error ? err.message : "Network error",
      );
    } finally {
      setSaving(false);
    }
  }, [
    canSave,
    initialRubric,
    weights,
    apiBaseUrl,
    product,
    version,
    saveNote,
    router,
  ]);

  // Index preview tiers by tier_id for O(1) lookup in the render loop.
  const previewByTier: Record<string, PreviewTier> = {};
  if (preview) {
    for (const pt of preview.tiers) {
      previewByTier[pt.tier_id] = pt;
    }
  }

  return (
    <div style={{ padding: 24, maxWidth: 900, margin: "0 auto" }}>
      {/* Tier sections — all three always in the DOM (no tier picker). */}
      {initialRubric.tiers.map((tier) => (
        <TierSection
          key={tier.id}
          tier={tier}
          weights={weights}
          previewTier={previewByTier[tier.id] ?? null}
          onWeightChange={handleWeightChange}
        />
      ))}

      {/* Preview status line */}
      {previewing && (
        <div
          style={{
            fontSize: 11,
            color: "var(--neutral-6)",
            marginBottom: 12,
            display: "flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          <IconRefresh size={12} color="var(--neutral-6)" />
          Computing preview…
        </div>
      )}
      {previewError && (
        <div
          style={{
            fontSize: 11,
            color: "var(--warm-red)",
            marginBottom: 12,
            display: "flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          <IconAlert size={12} color="var(--warm-red)" />
          Preview unavailable: {previewError}
        </div>
      )}

      {/* Save conflict banner */}
      {saveConflict && (
        <div
          data-testid="save-conflict"
          style={{
            background: "var(--light-red)",
            color: "var(--warm-red)",
            borderRadius: 6,
            padding: "10px 14px",
            fontSize: 13,
            marginBottom: 12,
            display: "flex",
            alignItems: "flex-start",
            gap: 10,
          }}
        >
          <IconAlert size={16} color="var(--warm-red)" style={{ flexShrink: 0, marginTop: 1 }} />
          <div style={{ flex: 1 }}>
            <div>{saveConflict}</div>
            <Btn
              variant="ghost"
              size="sm"
              style={{ marginTop: 8, color: "var(--warm-red)" }}
              onClick={() => {
                setSaveConflict(null);
                router.refresh();
              }}
            >
              Reload
            </Btn>
          </div>
        </div>
      )}

      {/* Save 422 validation errors */}
      {saveErrors && (
        <div
          data-testid="save-errors"
          style={{
            background: "var(--light-red)",
            color: "var(--warm-red)",
            borderRadius: 6,
            padding: "10px 14px",
            fontSize: 13,
            marginBottom: 12,
            display: "flex",
            alignItems: "flex-start",
            gap: 10,
          }}
        >
          <IconAlert size={16} color="var(--warm-red)" style={{ flexShrink: 0, marginTop: 1 }} />
          <div>
            <strong>Validation error:</strong> {saveErrors}
          </div>
        </div>
      )}

      {/* Generic save error */}
      {saveGenericError && (
        <div
          style={{
            background: "var(--light-red)",
            color: "var(--warm-red)",
            borderRadius: 6,
            padding: "10px 14px",
            fontSize: 13,
            marginBottom: 12,
          }}
        >
          {saveGenericError}
        </div>
      )}

      {/* Inline save bar — always visible, no modal */}
      <Panel padding={16} style={{ marginTop: 8 }}>
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            gap: 12,
            flexWrap: "wrap",
          }}
        >
          <div style={{ flex: 1, minWidth: 220 }}>
            <label
              htmlFor="save-note-input"
              style={{
                fontSize: 12,
                fontWeight: 500,
                color: "var(--neutral-3)",
                display: "block",
                marginBottom: 6,
              }}
            >
              Why are you changing this?{" "}
              <span style={{ color: "var(--neutral-6)", fontWeight: 400 }}>
                (stored on the version)
              </span>
            </label>
            <textarea
              id="save-note-input"
              data-testid="save-note"
              value={saveNote}
              onChange={(e) => setSaveNote(e.target.value)}
              placeholder="e.g. Reweight latency toward synthesis after Q4 review."
              style={{
                width: "100%",
                minHeight: 68,
                padding: 10,
                border: "1px solid var(--neutral-10)",
                borderRadius: 6,
                fontFamily: "var(--font-sans)",
                fontSize: 13,
                color: "var(--neutral-1)",
                resize: "vertical",
                boxSizing: "border-box",
                outline: "none",
              }}
            />
          </div>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              flexShrink: 0,
              paddingTop: 24,
            }}
          >
            <Btn
              variant="ghost"
              size="sm"
              icon={<IconRefresh size={12} />}
              onClick={handleReset}
              disabled={!dirty || saving}
            >
              Reset
            </Btn>
            <Btn
              data-testid="save-button"
              variant="default"
              onClick={handleSave}
              disabled={!canSave}
            >
              {saving ? (
                <>
                  <IconRefresh size={13} />
                  Saving…
                </>
              ) : (
                <>
                  <IconCheck size={13} />
                  Save rubric
                </>
              )}
            </Btn>
          </div>
        </div>

        {/* Status line under the save bar */}
        {!allValid && (
          <div
            style={{
              fontSize: 11,
              color: "var(--warm-red)",
              marginTop: 8,
              display: "flex",
              alignItems: "center",
              gap: 5,
            }}
          >
            <IconAlert size={11} color="var(--warm-red)" />
            Active-weight sum must be in (0, 100] for every tier before saving.
          </div>
        )}
        {allValid && dirty && (
          <div
            style={{
              fontSize: 11,
              color: "var(--neutral-6)",
              marginTop: 8,
              display: "flex",
              alignItems: "center",
              gap: 5,
            }}
          >
            <IconAlert size={11} color="var(--neutral-6)" />
            Unsaved edits — add a note and save to commit.
          </div>
        )}
        {!dirty && (
          <div
            style={{
              fontSize: 11,
              color: "var(--green)",
              marginTop: 8,
              display: "flex",
              alignItems: "center",
              gap: 5,
            }}
          >
            <IconCheck size={11} color="var(--green)" />
            Matches saved rubric.
          </div>
        )}
      </Panel>

      {/* Toast — fixed-position pill, bottom-center */}
      {toast && (
        <div
          data-testid="toast"
          style={{
            position: "fixed",
            bottom: 24,
            left: "50%",
            transform: "translateX(-50%)",
            background: "var(--neutral-1)",
            color: "#fff",
            padding: "10px 18px",
            borderRadius: 8,
            fontSize: 13,
            fontWeight: 500,
            zIndex: 200,
            boxShadow: "var(--shadow-md)",
            whiteSpace: "nowrap",
          }}
        >
          {toast}
        </div>
      )}
    </div>
  );
}
