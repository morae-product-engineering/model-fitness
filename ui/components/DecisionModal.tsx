"use client";

// Rationale-capture dialog for promote / reject decisions (AC1).
// Rendered on top of the CandidateDetail drawer via z-50; confirm is disabled
// until the rationale has at least 5 characters.

import { useEffect, useRef, useState } from "react";
import {
  DecisionKind,
  PendingDecision,
  promoteCandidate,
  rejectCandidate,
} from "@/lib/promotion";
import { TierId } from "@/lib/scoreboard";
import Btn from "./primitives/Btn";

interface DecisionModalProps {
  action: PendingDecision;
  product: string;
  apiBaseUrl: string;
  onClose: () => void;
  onSuccess: () => void;
  onToast: (message: string) => void;
}

const TOAST_MESSAGES: Record<DecisionKind, string> = {
  promote_primary: "promoted to primary",
  promote_fallback: "set as fallback",
  reject: "candidate rejected",
};

const TIER_LABELS: Record<TierId, string> = {
  tier_1: "T1 · Classification & Routing",
  tier_2: "T2 · Structured Generation",
  tier_3: "T3 · Synthesis",
};

const PLACEHOLDERS: Record<DecisionKind, string> = {
  promote_primary:
    "e.g. Sustained 92.1 composite over 3 quarters; ARB consensus; gate clean.",
  promote_fallback:
    "e.g. Consistent performance; strong fallback candidate; no gate failures.",
  reject:
    "e.g. Hallucination rate 3.4% — exceeds T3 gate of <2%. Recheck after vendor v3.",
};

const DESCRIPTIONS: Record<DecisionKind, string> = {
  promote_primary: "This becomes the production primary for this tier.",
  promote_fallback: "This becomes the production fallback for this tier.",
  reject:
    "The candidate moves to Rejected and is excluded from portfolio consideration.",
};

export default function DecisionModal({
  action,
  product,
  apiBaseUrl,
  onClose,
  onSuccess,
  onToast,
}: DecisionModalProps) {
  const [rationale, setRationale] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setRationale("");
    setError(null);
    textareaRef.current?.focus();
  }, [action.kind, action.deployment]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !submitting) onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, submitting]);

  const title =
    action.kind === "promote_primary"
      ? `Promote ${action.displayName} to Primary`
      : action.kind === "promote_fallback"
        ? `Set ${action.displayName} as Fallback`
        : `Reject ${action.displayName}`;

  async function handleConfirm() {
    if (rationale.trim().length < 5 || submitting) return;
    setSubmitting(true);
    setError(null);

    const result =
      action.kind === "reject"
        ? await rejectCandidate(
            apiBaseUrl,
            product,
            action.deployment,
            action.tierId,
            rationale.trim(),
          )
        : await promoteCandidate(
            apiBaseUrl,
            product,
            action.deployment,
            action.tierId,
            action.kind === "promote_primary" ? "primary" : "fallback",
            rationale.trim(),
          );

    setSubmitting(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    onToast(TOAST_MESSAGES[action.kind]);
    onSuccess();
    onClose();
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      className="fixed inset-0 z-50 bg-neutral-1/40 flex items-center justify-center p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget && !submitting) onClose();
      }}
    >
      <div className="bg-white rounded-lg shadow-elev-lg border border-neutral-11 w-full max-w-lg">
        <div className="px-6 py-4 border-b border-neutral-11">
          <h2
            data-testid="decision-modal-title"
            className="text-sm font-semibold text-neutral-1"
          >
            {title}
          </h2>
        </div>

        <div className="px-6 py-4">
          <p className="text-xs text-neutral-5 mb-4">
            {DESCRIPTIONS[action.kind]}
          </p>

          <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-xs bg-neutral-13 rounded-md px-3 py-2.5 mb-4">
            <span className="text-neutral-6">Tier</span>
            <span className="text-neutral-2 font-medium">
              {TIER_LABELS[action.tierId]}
            </span>
            <span className="text-neutral-6">Candidate</span>
            <span className="font-medium text-neutral-1">
              {action.displayName}
            </span>
          </div>

          <label className="block text-xs font-medium text-neutral-3 mb-1.5">
            Rationale{" "}
            <span className="text-neutral-6 font-normal">(required)</span>
          </label>
          <textarea
            ref={textareaRef}
            data-testid="promotion-rationale"
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
            placeholder={PLACEHOLDERS[action.kind]}
            rows={3}
            disabled={submitting}
            className="w-full text-xs border border-neutral-10 rounded-md p-2.5 resize-y text-neutral-1 placeholder:text-neutral-7 focus:outline-none focus:border-neutral-5 disabled:opacity-50"
          />
          {error && (
            <p data-testid="decision-error" className="text-xs text-warm-red mt-2">
              {error}
            </p>
          )}
        </div>

        <div className="px-6 py-3 border-t border-neutral-11 flex justify-end gap-2">
          <Btn variant="ghost" size="sm" onClick={onClose} disabled={submitting}>
            Cancel
          </Btn>
          <Btn
            data-testid="promotion-submit"
            variant={action.kind === "reject" ? "destructive" : "default"}
            size="sm"
            disabled={rationale.trim().length < 5 || submitting}
            onClick={handleConfirm}
          >
            {submitting
              ? "Saving…"
              : action.kind === "reject"
                ? "Reject candidate"
                : "Confirm decision"}
          </Btn>
        </div>
      </div>
    </div>
  );
}
