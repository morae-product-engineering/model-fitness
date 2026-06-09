// Unit tests for DecisionModal (MFP-15).
//
// What we exercise:
//   - promotion-submit is disabled until rationale has >= 5 characters
//   - promotion-submit is enabled at exactly 5 characters
//   - onToast is called with the correct message on a successful promote_primary
//   - onToast is called with the correct message on a successful reject
//   - onSuccess and onClose are called after a successful submission
//   - decision-error renders when the API returns a failure

import { describe, it, expect, vi, afterEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import DecisionModal from "../../ui/components/DecisionModal";
import type { PendingDecision } from "../../ui/lib/promotion";

vi.mock("../../ui/lib/promotion", async (importOriginal) => {
  const original = await importOriginal<typeof import("../../ui/lib/promotion")>();
  return {
    ...original,
    promoteCandidate: vi.fn(),
    rejectCandidate: vi.fn(),
  };
});

import { promoteCandidate, rejectCandidate } from "../../ui/lib/promotion";

const promotePrimary: PendingDecision = {
  kind: "promote_primary",
  displayName: "GPT-4o",
  deployment: "gpt-4o",
  tierId: "tier_1",
};

const rejectAction: PendingDecision = {
  kind: "reject",
  displayName: "GPT-4o",
  deployment: "gpt-4o",
  tierId: "tier_1",
};

function renderModal(
  action: PendingDecision = promotePrimary,
  overrides: Partial<{
    onClose: () => void;
    onSuccess: () => void;
    onToast: (msg: string) => void;
  }> = {},
) {
  return render(
    <DecisionModal
      action={action}
      product="mli"
      apiBaseUrl="http://api.test"
      onClose={overrides.onClose ?? vi.fn()}
      onSuccess={overrides.onSuccess ?? vi.fn()}
      onToast={overrides.onToast ?? vi.fn()}
    />,
  );
}

afterEach(() => {
  vi.resetAllMocks();
});

describe("DecisionModal — rationale gate", () => {
  it("submit is disabled when rationale is empty", () => {
    renderModal();
    expect(screen.getByTestId("promotion-submit")).toBeDisabled();
  });

  it("submit stays disabled with 4 characters", () => {
    renderModal();
    fireEvent.change(screen.getByTestId("promotion-rationale"), {
      target: { value: "abcd" },
    });
    expect(screen.getByTestId("promotion-submit")).toBeDisabled();
  });

  it("submit is enabled at exactly 5 characters", () => {
    renderModal();
    fireEvent.change(screen.getByTestId("promotion-rationale"), {
      target: { value: "abcde" },
    });
    expect(screen.getByTestId("promotion-submit")).not.toBeDisabled();
  });

  it("submit is enabled with more than 5 characters", () => {
    renderModal();
    fireEvent.change(screen.getByTestId("promotion-rationale"), {
      target: { value: "Meets all quality gates for T1." },
    });
    expect(screen.getByTestId("promotion-submit")).not.toBeDisabled();
  });
});

describe("DecisionModal — success path", () => {
  it("calls onToast with 'promoted to primary' after a successful promote_primary", async () => {
    vi.mocked(promoteCandidate).mockResolvedValue({ ok: true });
    const onToast = vi.fn();
    const onSuccess = vi.fn();
    const onClose = vi.fn();
    renderModal(promotePrimary, { onToast, onSuccess, onClose });

    fireEvent.change(screen.getByTestId("promotion-rationale"), {
      target: { value: "Sustained 92.1 composite; gate clean." },
    });
    fireEvent.click(screen.getByTestId("promotion-submit"));

    await waitFor(() => expect(onToast).toHaveBeenCalledWith("promoted to primary"));
    expect(onSuccess).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onToast with 'candidate rejected' after a successful reject", async () => {
    vi.mocked(rejectCandidate).mockResolvedValue({ ok: true });
    const onToast = vi.fn();
    renderModal(rejectAction, { onToast });

    fireEvent.change(screen.getByTestId("promotion-rationale"), {
      target: { value: "Hallucination rate exceeds gate." },
    });
    fireEvent.click(screen.getByTestId("promotion-submit"));

    await waitFor(() => expect(onToast).toHaveBeenCalledWith("candidate rejected"));
  });
});

describe("DecisionModal — error path", () => {
  it("renders decision-error and does not call onSuccess when API fails", async () => {
    vi.mocked(promoteCandidate).mockResolvedValue({ ok: false, error: "No matrix run found" });
    const onSuccess = vi.fn();
    renderModal(promotePrimary, { onSuccess });

    fireEvent.change(screen.getByTestId("promotion-rationale"), {
      target: { value: "Meets all criteria." },
    });
    fireEvent.click(screen.getByTestId("promotion-submit"));

    await waitFor(() => expect(screen.getByTestId("decision-error")).toBeInTheDocument());
    expect(screen.getByTestId("decision-error").textContent).toContain("No matrix run found");
    expect(onSuccess).not.toHaveBeenCalled();
  });
});
