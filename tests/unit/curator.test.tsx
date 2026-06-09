// Unit tests for the Curator component (MFP-76).
//
// Covers:
//   - Datasets tab renders curator-dataset-table on load
//   - Add-example button opens the modal; submit is disabled until both
//     required fields are filled; successful submit shows a toast with 'example'
//   - Queue tab renders curator-queue-row entries
//   - Agree button updates the curator-queue-status chip to 'Agreed'
//     and shows a toast with 'agree'

import { describe, it, expect, afterEach, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within, act } from "@testing-library/react";
import Curator from "../../ui/components/Curator";

const API_BASE = "http://api.test";
const PRODUCT = "mli";
const TIER_ID = "tier_3";

const EXAMPLE_PAYLOAD = {
  product: PRODUCT,
  tier_id: TIER_ID,
  examples: [
    { id: "ex-1", input: "What is TLS?", expected: { answer: "A protocol" }, tags: [], metadata: {} },
  ],
};

const QUEUE_PAYLOAD = {
  product: PRODUCT,
  samples: [
    {
      sample_id: "samp-1",
      run_id: "run-1",
      dimension_id: "synthesis_quality",
      candidate_id: "gpt-4o",
      candidate_output: "Some output",
      judge_score: 0.82,
      judge_reasoning: "Covers themes",
      judge_confidence: "high",
      created_at: "2026-06-01T00:00:00Z",
      status: "pending",
      decision: null,
      note: null,
    },
  ],
};

const MARK_RESPONSE = {
  sample_id: "samp-1",
  status: "reviewed",
  decision: "agree",
  note: null,
};

const CREATED_EXAMPLE = {
  id: "ex-new",
  input: "New task",
  expected: { themes: ["a"] },
  tags: [],
  metadata: {},
};

function mockFetch(handler: (url: string, opts?: RequestInit) => Response) {
  const fn = vi.fn((url: string, opts?: RequestInit) => Promise.resolve(handler(url, opts)));
  vi.stubGlobal("fetch", fn);
  return fn;
}

function renderCurator() {
  return render(
    <Curator product={PRODUCT} tierId={TIER_ID} apiBaseUrl={API_BASE} />,
  );
}

describe("Curator", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("renders curator-dataset-table after datasets load", async () => {
    mockFetch(() =>
      new Response(JSON.stringify(EXAMPLE_PAYLOAD), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    renderCurator();
    await screen.findByTestId("curator-dataset-table");
    expect(screen.getByText("ex-1")).toBeInTheDocument();
  });

  it("add-example submit is disabled until both required fields are filled", async () => {
    mockFetch(() =>
      new Response(JSON.stringify(EXAMPLE_PAYLOAD), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    renderCurator();
    await screen.findByTestId("curator-dataset-table");

    fireEvent.click(screen.getByTestId("curator-add-example-btn"));
    const modal = await screen.findByTestId("curator-add-example-modal");
    const submit = within(modal).getByTestId("add-example-submit");

    expect(submit).toBeDisabled();

    fireEvent.change(within(modal).getByTestId("add-example-input"), {
      target: { value: "Summarise the contract obligations." },
    });
    expect(submit).toBeDisabled();

    fireEvent.change(within(modal).getByTestId("add-example-expected"), {
      target: { value: '{"themes": ["indemnity"]}' },
    });
    expect(submit).toBeEnabled();
  });

  it("successful add shows toast containing 'example' and closes the modal", async () => {
    let callCount = 0;
    mockFetch(() => {
      callCount += 1;
      // First call: GET datasets. Second: POST new example.
      const body = callCount === 1 ? EXAMPLE_PAYLOAD : CREATED_EXAMPLE;
      return new Response(JSON.stringify(body), {
        status: callCount === 1 ? 200 : 201,
        headers: { "Content-Type": "application/json" },
      });
    });
    renderCurator();
    await screen.findByTestId("curator-dataset-table");

    fireEvent.click(screen.getByTestId("curator-add-example-btn"));
    const modal = await screen.findByTestId("curator-add-example-modal");

    fireEvent.change(within(modal).getByTestId("add-example-input"), {
      target: { value: "Summarise the contract obligations." },
    });
    fireEvent.change(within(modal).getByTestId("add-example-expected"), {
      target: { value: '{"themes": ["indemnity"]}' },
    });

    await act(async () => {
      fireEvent.click(within(modal).getByTestId("add-example-submit"));
    });

    await waitFor(() => expect(screen.queryByTestId("curator-add-example-modal")).not.toBeInTheDocument());
    expect(screen.getByTestId("toast").textContent).toContain("example");
  });

  it("queue tab renders curator-queue-row entries", async () => {
    mockFetch((url) => {
      const body = url.includes("judge-queue") ? QUEUE_PAYLOAD : EXAMPLE_PAYLOAD;
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    renderCurator();
    await screen.findByTestId("curator-dataset-table");

    fireEvent.click(screen.getByTestId("curator-tab-queue"));
    const row = await screen.findByTestId("curator-queue-row");
    expect(within(row).getByTestId("curator-queue-status").textContent).toBe("Pending");
  });

  it("agree button updates status to Agreed and shows toast with 'agree'", async () => {
    mockFetch((url, opts) => {
      if ((opts?.method ?? "GET") === "POST" && url.includes("/mark")) {
        return new Response(JSON.stringify(MARK_RESPONSE), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      const body = url.includes("judge-queue") ? QUEUE_PAYLOAD : EXAMPLE_PAYLOAD;
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    renderCurator();
    await screen.findByTestId("curator-dataset-table");

    fireEvent.click(screen.getByTestId("curator-tab-queue"));
    const row = await screen.findByTestId("curator-queue-row");

    await act(async () => {
      fireEvent.click(within(row).getByTestId("curator-queue-agree"));
    });

    await waitFor(() =>
      expect(within(row).getByTestId("curator-queue-status").textContent).toBe("Agreed"),
    );
    expect(screen.getByTestId("toast").textContent).toContain("agree");
  });
});
