// Unit tests for RubricEditor (MLI-195).
//
// What we exercise:
//   - Active dims render weight-input-${tier}.${dim} testids; draft dim has no
//     editable input and shows the draft label.
//   - Editing a weight triggers a debounced preview POST and renders
//     impact-preview-tier_3 with a ranking-change-row when rank_after ≠ rank_before.
//   - coverage_complete:false → coverage-incomplete marker present.
//   - normalization_stale_dimensions → normalization-stale-${tier_id} banner
//     naming the stale dim.
//   - Save 200 → toast contains "Rubric saved" and new version; PUT carried
//     expected_version, X-Steward-Identity header, and applied edited weights.
//   - Save 409 → save-conflict banner, no toast.
//   - Save 422 → save-errors banner, no toast.
//
// Timer strategy: real timers throughout to avoid async state leaks from
// fake-timer mid-test switching. The debounce in RubricEditor is 400ms;
// tests use `waitFor` with a generous timeout to handle async fetch chains.

import {
  describe,
  it,
  expect,
  afterEach,
  vi,
} from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import RubricEditor from "../../ui/components/RubricEditor";
import type { RawRubric } from "../../ui/lib/rubric";

// Mock next/navigation so useRouter is available and controllable.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

const API_BASE = "http://api.test";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

// Two-tier rubric with tier_3 having two active dims and one draft dim, and
// tier_1 with one active dim.
function makeRubric(): RawRubric {
  return {
    schema_version: "v1",
    version: "v0.1",
    gates: {},
    judge: { model: "claude-sonnet-4-5" },
    tiers: [
      {
        id: "tier_1",
        name: "Classification & Routing",
        dimensions: [
          {
            id: "classification_accuracy",
            name: "Classification accuracy",
            description: "Correct classification rate",
            weight: 100,
            status: "active",
            direction: "higher_is_better",
            method: "deterministic",
            evaluator: "exact_match",
          },
        ],
      },
      {
        id: "tier_3",
        name: "Synthesis",
        dimensions: [
          {
            id: "latency_p95",
            name: "Latency p95",
            description: "95th percentile latency",
            weight: 50,
            status: "active",
            direction: "lower_is_better",
            method: "metric",
            evaluator: "latency",
          },
          {
            id: "cost_per_completed_interaction",
            name: "Cost per interaction",
            description: "Cost in USD",
            weight: 50,
            status: "active",
            direction: "lower_is_better",
            method: "metric",
            evaluator: "cost",
          },
          {
            id: "synthesis_quality",
            name: "Synthesis quality",
            description: "LLM judge score",
            weight: 0,
            status: "draft",
            direction: "higher_is_better",
            method: "llm_judge",
            evaluator: "llm_judge",
          },
        ],
      },
    ],
  };
}

// A minimal valid preview response for tier_3 with a ranking change.
function previewPayload(
  opts: {
    coverageComplete?: boolean;
    stale?: string[];
  } = {},
) {
  const { coverageComplete = true, stale = [] } = opts;
  return {
    product: "mli",
    run_id: "run-1",
    current_version: "v0.1",
    candidate_version: "v0.1",
    has_run: true,
    tiers: [
      {
        tier_id: "tier_3",
        normalization_stale_dimensions: stale,
        candidates: [
          {
            candidate: "gpt-4o",
            score_before: "70.0",
            score_after: "80.0",
            rank_before: 2,
            rank_after: 1,
            coverage_complete: coverageComplete,
          },
          {
            candidate: "claude-sonnet",
            score_before: "75.0",
            score_after: "72.0",
            rank_before: 1,
            rank_after: 2,
            coverage_complete: coverageComplete,
          },
        ],
      },
    ],
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function stubFetch(
  responses: Array<{ status: number; body: unknown }>,
): ReturnType<typeof vi.fn> {
  let callIndex = 0;
  const fn = vi.fn(async () => {
    const r = responses[callIndex] ?? responses[responses.length - 1]!;
    callIndex++;
    return new Response(JSON.stringify(r.body), {
      status: r.status,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

function renderEditor(
  overrides: Partial<React.ComponentProps<typeof RubricEditor>> = {},
) {
  const rubric = makeRubric();
  return render(
    <RubricEditor
      product="mli"
      apiBaseUrl={API_BASE}
      initialRubric={rubric}
      version="v0.1"
      {...overrides}
    />,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("RubricEditor", () => {
  // -------------------------------------------------------------------------
  // Rendering: active dims, draft dims
  // -------------------------------------------------------------------------

  it("renders weight-input testids for active dims in both tiers", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    renderEditor();
    expect(
      screen.getByTestId("weight-input-tier_1.classification_accuracy"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("weight-input-tier_3.latency_p95"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("weight-input-tier_3.cost_per_completed_interaction"),
    ).toBeInTheDocument();
  });

  it("does NOT render a weight input for the draft dim", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    renderEditor();
    expect(
      screen.queryByTestId("weight-input-tier_3.synthesis_quality"),
    ).not.toBeInTheDocument();
  });

  it("renders the draft label for the draft dim", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    renderEditor();
    const labels = screen.getAllByTestId("dimension-draft-label");
    expect(labels.length).toBeGreaterThanOrEqual(1);
    expect(labels[0]!.textContent).toContain("Draft");
  });

  // -------------------------------------------------------------------------
  // Debounced preview + impact panel
  // -------------------------------------------------------------------------

  it("POSTs to preview-impact after debounce and renders impact-preview-tier_3 with ranking-change-row", async () => {
    const fetchFn = stubFetch([{ status: 200, body: previewPayload() }]);
    renderEditor();

    const input = screen.getByTestId("weight-input-tier_3.latency_p95");
    fireEvent.change(input, { target: { value: "40" } });

    // Wait for the 400ms debounce + fetch + React re-render.
    await waitFor(
      () => {
        expect(screen.getByTestId("impact-preview-tier_3")).toBeInTheDocument();
      },
      { timeout: 1500 },
    );

    expect(screen.getAllByTestId("ranking-change-row").length).toBeGreaterThan(0);

    expect(fetchFn).toHaveBeenCalledWith(
      expect.stringContaining("preview-impact"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  // -------------------------------------------------------------------------
  // Coverage incomplete
  // -------------------------------------------------------------------------

  it("renders coverage-incomplete marker when coverage_complete is false", async () => {
    stubFetch([{ status: 200, body: previewPayload({ coverageComplete: false }) }]);
    renderEditor();

    const input = screen.getByTestId("weight-input-tier_3.latency_p95");
    fireEvent.change(input, { target: { value: "40" } });

    await waitFor(
      () => {
        expect(screen.getByTestId("impact-preview-tier_3")).toBeInTheDocument();
      },
      { timeout: 1500 },
    );

    const markers = screen.getAllByTestId("coverage-incomplete");
    expect(markers.length).toBeGreaterThan(0);
  });

  // -------------------------------------------------------------------------
  // Normalisation staleness
  // -------------------------------------------------------------------------

  it("renders normalization-stale-tier_3 banner naming the stale dim", async () => {
    stubFetch([
      {
        status: 200,
        body: previewPayload({ stale: ["latency_p95"] }),
      },
    ]);
    renderEditor();

    const input = screen.getByTestId("weight-input-tier_3.latency_p95");
    fireEvent.change(input, { target: { value: "40" } });

    await waitFor(
      () => {
        expect(
          screen.getByTestId("normalization-stale-tier_3"),
        ).toBeInTheDocument();
      },
      { timeout: 1500 },
    );

    expect(
      screen.getByTestId("normalization-stale-tier_3").textContent,
    ).toContain("latency_p95");
  });

  // -------------------------------------------------------------------------
  // Save 200 — toast + PUT shape
  // -------------------------------------------------------------------------

  it("shows toast with 'Rubric saved' and new version on 200, PUT carried expected_version and steward header", async () => {
    const fetchFn = stubFetch([
      { status: 200, body: previewPayload() },
      {
        status: 200,
        body: {
          previous_version: "v0.1",
          new_version: "v0.2",
          commit_sha: "abc123",
        },
      },
    ]);
    renderEditor();

    // Make an edit so save button is enabled.
    const input = screen.getByTestId("weight-input-tier_3.latency_p95");
    fireEvent.change(input, { target: { value: "40" } });

    // Wait for preview.
    await waitFor(
      () => screen.getByTestId("impact-preview-tier_3"),
      { timeout: 1500 },
    );

    // Fill note and click save.
    const note = screen.getByTestId("save-note");
    fireEvent.change(note, { target: { value: "Test save" } });

    const saveBtn = screen.getByTestId("save-button");
    fireEvent.click(saveBtn);

    await waitFor(
      () => {
        expect(screen.getByTestId("toast")).toBeInTheDocument();
      },
      { timeout: 2000 },
    );

    expect(screen.getByTestId("toast").textContent).toContain("Rubric saved");
    expect(screen.getByTestId("toast").textContent).toContain("v0.2");

    // Find the PUT call.
    const putCall = fetchFn.mock.calls.find(
      (call) =>
        typeof call[0] === "string" &&
        (call[0] as string).includes("/rubric") &&
        !(call[0] as string).includes("preview-impact") &&
        (call[1] as RequestInit)?.method === "PUT",
    );
    expect(putCall).toBeDefined();

    const putBody = JSON.parse((putCall![1] as RequestInit).body as string);
    expect(putBody.expected_version).toBe("v0.1");

    const putHeaders = (putCall![1] as RequestInit).headers as Record<string, string>;
    expect(putHeaders["X-Steward-Identity"]).toBeDefined();

    // Verify the weight edit was applied.
    const tier3 = putBody.rubric.tiers.find(
      (t: { id: string }) => t.id === "tier_3",
    );
    const latencyDim = tier3!.dimensions.find(
      (d: { id: string }) => d.id === "latency_p95",
    );
    expect(Number(latencyDim!.weight)).toBe(40);
  });

  // -------------------------------------------------------------------------
  // Save 409 — conflict banner, no toast
  // -------------------------------------------------------------------------

  it("shows save-conflict banner on 409, no toast", async () => {
    stubFetch([
      { status: 200, body: previewPayload() },
      {
        status: 409,
        body: {
          error: "version_conflict",
          current_version: "v0.2",
          expected_version: "v0.1",
        },
      },
    ]);
    renderEditor();

    const input = screen.getByTestId("weight-input-tier_3.latency_p95");
    fireEvent.change(input, { target: { value: "40" } });

    await waitFor(
      () => screen.getByTestId("impact-preview-tier_3"),
      { timeout: 1500 },
    );

    const note = screen.getByTestId("save-note");
    fireEvent.change(note, { target: { value: "Test conflict" } });
    fireEvent.click(screen.getByTestId("save-button"));

    await waitFor(
      () => {
        expect(screen.getByTestId("save-conflict")).toBeInTheDocument();
      },
      { timeout: 2000 },
    );

    expect(screen.queryByTestId("toast")).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Save 422 — errors banner, no toast
  // -------------------------------------------------------------------------

  it("shows save-errors banner on 422, no toast", async () => {
    stubFetch([
      { status: 200, body: previewPayload() },
      {
        status: 422,
        body: {
          detail: [
            {
              loc: ["body", "rubric", "tiers", 0, "dimensions"],
              msg: "active dimension weight sum must be > 0",
              type: "value_error",
            },
          ],
        },
      },
    ]);
    renderEditor();

    const input = screen.getByTestId("weight-input-tier_3.latency_p95");
    fireEvent.change(input, { target: { value: "40" } });

    await waitFor(
      () => screen.getByTestId("impact-preview-tier_3"),
      { timeout: 1500 },
    );

    const note = screen.getByTestId("save-note");
    fireEvent.change(note, { target: { value: "Trigger 422" } });
    fireEvent.click(screen.getByTestId("save-button"));

    await waitFor(
      () => {
        expect(screen.getByTestId("save-errors")).toBeInTheDocument();
      },
      { timeout: 2000 },
    );

    expect(screen.queryByTestId("toast")).not.toBeInTheDocument();
    expect(screen.getByTestId("save-errors").textContent).toContain(
      "active dimension weight sum",
    );
  });
});
