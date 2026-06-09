// Unit tests for CandidateDetail (MLI-187 + MLI-274 weight-aware breakdown).
//
// What we exercise:
//   - Testids required by the slice-03 Playwright acceptance test
//     (candidate-detail-dimensions, dimension-row)
//   - The MLI-274 dim-weight-<dimension_id> testid contract (the parent
//     acceptance test MLI-268 selects on `dim-weight-classification_accuracy`
//     and expects "35%")
//   - Active vs draft rendering: drafts are visually de-emphasised, labelled,
//     and do not contribute to the composite (MLI-269 weight-zero invariant)
//   - Per-tier filtering: a multi-tier candidate only shows the clicked tier
//   - Loading and error states (best-effort fetch posture from MLI-186)
//   - Empty state for unscored slate candidates — 200 with latest_run: null
//     (mmfp/api/candidate_detail.py:14 documents this case)
//   - Close affordances: × button, Escape key, backdrop click
//   - Deployment name is URL-encoded preserving case (Phi-4-mini-instruct)

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import CandidateDetail from "../../ui/components/CandidateDetail";
import type {
  WireCandidateDetail,
  WireRubric,
  WireRubricDimension,
} from "../../ui/lib/scoreboard";

const API_BASE = "http://api.test";

function dim(
  overrides: Partial<WireRubricDimension> & Pick<WireRubricDimension, "id">,
): WireRubricDimension {
  return {
    name: overrides.id,
    description: `${overrides.id} description`,
    weight: "0",
    status: "active",
    method: "deterministic",
    direction: "higher_is_better",
    ...overrides,
  };
}

function tier3Rubric(): WireRubric {
  return {
    version: "v0.1",
    tiers: [
      {
        tier_id: "tier_3",
        name: "Synthesis & Client-Facing Reasoning",
        dimensions: [
          dim({ id: "citation_presence", name: "Citation presence", weight: "60" }),
          dim({
            id: "structural_completeness",
            name: "Structural completeness",
            weight: "40",
          }),
        ],
      },
    ],
  };
}

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
    rubric: tier3Rubric(),
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

  it("renders one dimension-row per rubric dimension for the clicked tier", async () => {
    mockFetchOnce(loadedPayload());
    renderDetail();
    await screen.findByTestId("candidate-detail-dimensions");
    const rows = screen.getAllByTestId("dimension-row");
    expect(rows).toHaveLength(2);
    expect(rows[0]!.textContent).toContain("Citation presence");
    expect(rows[1]!.textContent).toContain("Structural completeness");
  });

  it("formats dimension scores to 1 decimal", async () => {
    mockFetchOnce(loadedPayload());
    renderDetail();
    const container = await screen.findByTestId("candidate-detail-dimensions");
    expect(within(container).getByText("82.0")).toBeInTheDocument();
    expect(within(container).getByText("73.0")).toBeInTheDocument();
  });

  it("renders the dim-weight-<id> testid carrying the formatted weight", async () => {
    // The parent acceptance test (slice-3p5-editor-and-scoreboard.spec.ts)
    // selects `dim-weight-classification_accuracy` and expects "35%".
    mockFetchOnce(
      loadedPayload({
        tiers: ["tier_1"],
        latest_run: {
          run_id: "r",
          rubric_version: "v0.1",
          started_at: "2026-05-12T12:00:00Z",
          completed_at: "2026-05-12T12:00:30Z",
          per_tier: [
            {
              tier_id: "tier_1",
              weighted_score: "82.000",
              per_dimension: { classification_accuracy: "82.000" },
            },
          ],
        },
        rubric: {
          version: "v0.1",
          tiers: [
            {
              tier_id: "tier_1",
              name: "Classification & Routing",
              dimensions: [
                dim({
                  id: "classification_accuracy",
                  name: "Classification accuracy",
                  weight: "35",
                }),
              ],
            },
          ],
        },
      }),
    );
    renderDetail({ tierId: "tier_1" });
    const weight = await screen.findByTestId(
      "dim-weight-classification_accuracy",
    );
    expect(weight.textContent).toBe("35%");
  });

  it("shows weight × score contribution for active dimensions", async () => {
    mockFetchOnce(loadedPayload());
    renderDetail();
    const container = await screen.findByTestId("candidate-detail-dimensions");
    // citation_presence: 60% weight × 82.0 score / 100 = 49.2
    // structural_completeness: 40% × 73.0 / 100 = 29.2
    expect(within(container).getByText("49.2")).toBeInTheDocument();
    expect(within(container).getByText("29.2")).toBeInTheDocument();
  });

  it("renders draft dimensions de-emphasised with the slice-6 label and no contribution", async () => {
    mockFetchOnce(
      loadedPayload({
        rubric: {
          version: "v0.1",
          tiers: [
            {
              tier_id: "tier_3",
              name: "Synthesis & Client-Facing Reasoning",
              dimensions: [
                dim({
                  id: "citation_presence",
                  name: "Citation presence",
                  weight: "60",
                }),
                dim({
                  id: "structural_completeness",
                  name: "Structural completeness",
                  weight: "40",
                }),
                dim({
                  id: "synthesis_quality",
                  name: "Synthesis quality",
                  weight: "0",
                  status: "draft",
                  method: "llm_judge",
                }),
              ],
            },
          ],
        },
      }),
    );
    renderDetail();
    await screen.findByTestId("candidate-detail-dimensions");
    const rows = screen.getAllByTestId("dimension-row");
    expect(rows).toHaveLength(3);

    const draftRow = rows[2]!;
    expect(draftRow.getAttribute("data-dimension-status")).toBe("draft");
    expect(draftRow.getAttribute("data-dimension-id")).toBe("synthesis_quality");
    expect(within(draftRow).getByTestId("dimension-draft-label").textContent)
      .toContain("Draft");
    // Draft weight is 0%; contribution column shows "—".
    expect(within(draftRow).getByTestId("dim-weight-synthesis_quality").textContent)
      .toBe("0%");
  });

  it("falls back to '—' for the score and contribution when no run scored the candidate", async () => {
    // Empty-state payload — rubric is still inlined, scores are absent.
    mockFetchOnce(loadedPayload({ latest_run: null, history: [] }));
    renderDetail();
    // Rubric drives row rendering; the empty-state stamp also appears.
    await screen.findByTestId("candidate-detail-empty");
    const rows = screen.getAllByTestId("dimension-row");
    expect(rows).toHaveLength(2);
    // Composite collapses to em-dash.
    expect(screen.getByTestId("candidate-detail-composite").textContent).toBe(
      "—",
    );
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
        rubric: {
          version: "v0.1",
          tiers: [
            {
              tier_id: "tier_1",
              name: "Classification & Routing",
              dimensions: [
                dim({
                  id: "classification_accuracy",
                  name: "Classification accuracy",
                  weight: "35",
                }),
                dim({
                  id: "routing_validity",
                  name: "Routing validity",
                  weight: "65",
                }),
              ],
            },
            {
              tier_id: "tier_3",
              name: "Synthesis & Client-Facing Reasoning",
              dimensions: [
                dim({
                  id: "citation_presence",
                  name: "Citation presence",
                  weight: "60",
                }),
                dim({
                  id: "structural_completeness",
                  name: "Structural completeness",
                  weight: "40",
                }),
              ],
            },
          ],
        },
      }),
    );
    renderDetail({ tierId: "tier_3" });
    const container = await screen.findByTestId("candidate-detail-dimensions");
    const rows = within(container).getAllByTestId("dimension-row");
    expect(rows).toHaveLength(2);
    expect(container.textContent).toContain("Citation presence");
    expect(container.textContent).not.toContain("Classification accuracy");
  });

  it("URL-encodes the deployment name preserving case (Phi-4-mini-instruct)", async () => {
    // Two fetches fire: the detail fetch and the audit-log fetch (fetchAuditLog).
    const fetchFn = mockFetchOnce(loadedPayload({ latest_run: null, history: [] }));
    renderDetail({ deployment: "Phi-4-mini-instruct", displayName: "Phi-4 mini" });
    await waitFor(() => expect(fetchFn).toHaveBeenCalledTimes(2));
    const detailUrl = String(fetchFn.mock.calls[0]![0]);
    expect(detailUrl).toBe(`${API_BASE}/api/products/mli/candidates/Phi-4-mini-instruct`);
  });

  it("renders the empty-state stamp but keeps the rubric rows when latest_run is null", async () => {
    // MLI-274: the rubric is the source of truth for which dimensions render,
    // so an unscored candidate still shows the rubric shape (scores collapse
    // to em-dashes). The `candidate-detail-empty` testid carries the stamp.
    mockFetchOnce(loadedPayload({ latest_run: null, history: [] }));
    renderDetail({ deployment: "Phi-4-mini-instruct", displayName: "Phi-4 mini" });
    await screen.findByTestId("candidate-detail-empty");
    expect(screen.getByTestId("candidate-detail-dimensions")).toBeInTheDocument();
    expect(screen.getAllByTestId("dimension-row")).toHaveLength(2);
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

  // MLI-275 — vendor badge, candidate sparkline, base-model surface
  describe("MLI-275 surfaces", () => {
    it("renders the vendor-badge in the header when candidateId is supplied", async () => {
      mockFetchOnce(loadedPayload({ candidate_id: "gpt-4o" }));
      renderDetail({ candidateId: "gpt-4o" });
      await screen.findByTestId("candidate-detail-dimensions");
      const badge = screen.getByTestId("vendor-badge");
      expect(badge.textContent).toBe("OpenAI");
      expect(badge.getAttribute("data-vendor")).toBe("OpenAI");
    });

    it("renders the candidate-sparkline once the payload loads", async () => {
      mockFetchOnce(
        loadedPayload({
          tiers: ["tier_3"],
          history: [
            {
              run_id: "r3",
              started_at: "2026-05-12T12:00:00Z",
              completed_at: "2026-05-12T12:00:30Z",
              per_tier_scores: { tier_3: "78.500" },
            },
            {
              run_id: "r2",
              started_at: "2026-05-05T12:00:00Z",
              completed_at: "2026-05-05T12:00:30Z",
              per_tier_scores: { tier_3: "75.000" },
            },
            {
              run_id: "r1",
              started_at: "2026-04-28T12:00:00Z",
              completed_at: "2026-04-28T12:00:30Z",
              per_tier_scores: { tier_3: "72.000" },
            },
          ],
        }),
      );
      renderDetail({ candidateId: "gpt-4o" });
      await screen.findByTestId("candidate-detail-dimensions");
      const sparkline = screen.getByTestId("candidate-sparkline");
      const path = sparkline.querySelector("svg path");
      expect(path).not.toBeNull();
      expect(path!.getAttribute("d")).toMatch(/^M/);
    });

    it("renders base-model line only when the payload carries base_model", async () => {
      // First render: no base_model → no line.
      mockFetchOnce(loadedPayload());
      const { unmount } = renderDetail({ candidateId: "gpt-4o" });
      await screen.findByTestId("candidate-detail-dimensions");
      expect(
        screen.queryByTestId("candidate-detail-base-model"),
      ).not.toBeInTheDocument();
      unmount();

      // Second render: base_model present → line surfaces with the value.
      mockFetchOnce(
        loadedPayload({ base_model: "mistral-large-3" }),
      );
      renderDetail({ candidateId: "gpt-4o" });
      await screen.findByTestId("candidate-detail-dimensions");
      const line = screen.getByTestId("candidate-detail-base-model");
      expect(line.textContent).toContain("mistral-large-3");
    });
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
