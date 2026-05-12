// Unit tests for CandidateDetail (MLI-187).
//
// What we exercise:
//   - Testids required by the slice-03 Playwright acceptance test
//     (candidate-detail-dimensions, dimension-row)
//   - Per-tier filtering: a multi-tier candidate only shows the clicked tier
//   - Loading and error states (best-effort fetch posture from MLI-186)
//   - Empty state for unscored slate candidates — 200 with latest_run: null
//     (mmfp/api/candidate_detail.py:14 documents this case)
//   - Close affordances: × button, Escape key, backdrop click
//   - Deployment name is URL-encoded preserving case (Phi-4-mini-instruct)

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import CandidateDetail from "../../ui/components/CandidateDetail";
import type { WireCandidateDetail } from "../../ui/lib/scoreboard";

const API_BASE = "http://api.test";

function loadedPayload(overrides: Partial<WireCandidateDetail> = {}): WireCandidateDetail {
  return {
    product: "mli",
    candidate_id: "gpt-4o",
    display_name: "GPT-4o",
    family: "chat",
    deployment: "azure-gpt-4o",
    status: "under_evaluation",
    tiers: ["tier_3"],
    latest_run: {
      run_id: "run-2026-05-12",
      rubric_version: "v0.1",
      started_at: "2026-05-12T12:00:00Z",
      completed_at: "2026-05-12T12:00:30Z",
      per_tier: [
        {
          tier_id: "tier_3",
          weighted_score: "78.500",
          per_dimension: {
            citation_presence: "82.000",
            structural_completeness: "73.000",
          },
        },
      ],
    },
    history: [
      {
        run_id: "run-2026-05-12",
        started_at: "2026-05-12T12:00:00Z",
        completed_at: "2026-05-12T12:00:30Z",
        per_tier_scores: { tier_3: "78.500" },
      },
    ],
    ...overrides,
  };
}

function mockFetchOnce(payload: WireCandidateDetail, status = 200): ReturnType<typeof vi.fn> {
  const fn = vi.fn(async () =>
    new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}

function renderDetail(overrides: Partial<React.ComponentProps<typeof CandidateDetail>> = {}) {
  return render(
    <CandidateDetail
      product="mli"
      deployment="azure-gpt-4o"
      displayName="GPT-4o"
      family="chat"
      tierId="tier_3"
      apiBaseUrl={API_BASE}
      onClose={() => {}}
      {...overrides}
    />,
  );
}

describe("CandidateDetail", () => {
  beforeEach(() => {
    vi.useRealTimers();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("renders dimension-row testids matching the rubric tier dimensions", async () => {
    mockFetchOnce(loadedPayload());
    renderDetail();
    await screen.findByTestId("candidate-detail-dimensions");
    const rows = screen.getAllByTestId("dimension-row");
    expect(rows).toHaveLength(2);
    expect(rows[0]!.textContent).toContain("citation_presence");
    expect(rows[1]!.textContent).toContain("structural_completeness");
  });

  it("formats dimension scores to 1 decimal", async () => {
    mockFetchOnce(loadedPayload());
    renderDetail();
    const container = await screen.findByTestId("candidate-detail-dimensions");
    expect(within(container).getByText("82.0")).toBeInTheDocument();
    expect(within(container).getByText("73.0")).toBeInTheDocument();
  });

  it("filters per_tier to the clicked tier when the candidate is multi-tier", async () => {
    mockFetchOnce(
      loadedPayload({
        tiers: ["tier_1", "tier_3"],
        latest_run: {
          run_id: "run-1",
          rubric_version: "v0.1",
          started_at: "2026-05-12T12:00:00Z",
          completed_at: "2026-05-12T12:00:30Z",
          per_tier: [
            {
              tier_id: "tier_1",
              weighted_score: "55.000",
              per_dimension: {
                classification_accuracy: "60.000",
                routing_validity: "50.000",
              },
            },
            {
              tier_id: "tier_3",
              weighted_score: "80.000",
              per_dimension: {
                citation_presence: "85.000",
                structural_completeness: "75.000",
              },
            },
          ],
        },
      }),
    );
    renderDetail({ tierId: "tier_3" });
    const container = await screen.findByTestId("candidate-detail-dimensions");
    const rows = within(container).getAllByTestId("dimension-row");
    expect(rows).toHaveLength(2);
    expect(container.textContent).toContain("citation_presence");
    expect(container.textContent).not.toContain("classification_accuracy");
  });

  it("URL-encodes the deployment name preserving case (Phi-4-mini-instruct)", async () => {
    const fetchFn = mockFetchOnce(loadedPayload({ latest_run: null, history: [] }));
    renderDetail({ deployment: "Phi-4-mini-instruct", displayName: "Phi-4 mini" });
    await waitFor(() => expect(fetchFn).toHaveBeenCalledTimes(1));
    const url = String(fetchFn.mock.calls[0]![0]);
    expect(url).toBe(`${API_BASE}/api/products/mli/candidates/Phi-4-mini-instruct`);
  });

  it("renders the empty state when latest_run is null", async () => {
    mockFetchOnce(loadedPayload({ latest_run: null, history: [] }));
    renderDetail({ deployment: "Phi-4-mini-instruct", displayName: "Phi-4 mini" });
    await screen.findByTestId("candidate-detail-empty");
    expect(screen.queryByTestId("candidate-detail-dimensions")).not.toBeInTheDocument();
    expect(screen.queryAllByTestId("dimension-row")).toHaveLength(0);
  });

  it("renders the error state on a non-OK response", async () => {
    mockFetchOnce(loadedPayload(), 503);
    renderDetail();
    const err = await screen.findByTestId("candidate-detail-error");
    expect(err.textContent).toContain("503");
  });

  it("renders the error state when fetch rejects", async () => {
    const fetchFn = vi.fn(async () => {
      throw new Error("network down");
    });
    vi.stubGlobal("fetch", fetchFn);
    renderDetail();
    const err = await screen.findByTestId("candidate-detail-error");
    expect(err.textContent).toContain("network down");
  });

  it("shows the loading state before the fetch resolves", () => {
    // Never-resolving fetch.
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    renderDetail();
    expect(screen.getByTestId("candidate-detail-loading")).toBeInTheDocument();
  });

  it("calls onClose when the × button is clicked", async () => {
    mockFetchOnce(loadedPayload());
    const onClose = vi.fn();
    renderDetail({ onClose });
    await screen.findByTestId("candidate-detail-dimensions");
    fireEvent.click(screen.getByTestId("candidate-detail-close"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when Escape is pressed", async () => {
    mockFetchOnce(loadedPayload());
    const onClose = vi.fn();
    renderDetail({ onClose });
    await screen.findByTestId("candidate-detail-dimensions");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when the backdrop is clicked but not when the panel is clicked", async () => {
    mockFetchOnce(loadedPayload());
    const onClose = vi.fn();
    renderDetail({ onClose });
    const container = await screen.findByTestId("candidate-detail-dimensions");
    // Click on the inner content — should not close.
    fireEvent.click(container);
    expect(onClose).not.toHaveBeenCalled();
    // Click on the backdrop overlay itself.
    fireEvent.click(screen.getByTestId("candidate-detail-overlay"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
