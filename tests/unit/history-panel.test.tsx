// Vitest component tests for HistoryPanel (MFP-16).
//
// Exercises:
//   - Loading state visible on mount
//   - Empty state when both APIs return no entries
//   - history-toggle NOT rendered in empty state
//   - history-toggle rendered when entries exist
//   - Click toggle → history-entry elements appear (collapsed by default)
//   - Click toggle again → entries hidden
//   - Status-change entries and rubric-save entries render with history-entry testid
//   - Load-more button appears when entries > PAGE_SIZE (20); clicking it reveals more

import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import HistoryPanel from "../../ui/components/HistoryPanel";

const API_BASE = "http://api.test";
const PRODUCT = "mli";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeAuditEntry(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: "entry-1",
    action: "promote_primary",
    tier_id: "tier_1",
    candidate_deployment: "gpt-4o-mini",
    previous_status: "under_evaluation",
    new_status: "approved_primary",
    rationale: "Best accuracy",
    rubric_version_at_time: "v0.1",
    run_id_at_time: "run-1",
    actor: "wayne@morae.com",
    timestamp: "2026-06-01T10:00:00Z",
    sequence: 1,
    ...overrides,
  };
}

function makeRubricRecord(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    product: "mli",
    previous_version: "v0.1",
    new_version: "v0.2",
    note: "Increased latency weight",
    steward: "wayne@morae.com",
    timestamp: "2026-06-01T11:00:00Z",
    schema_version: 1,
    ...overrides,
  };
}

// Build N audit entries with distinct timestamps (newest-first order, but
// the component sorts, so order here doesn't matter).
function makeEntries(n: number) {
  return Array.from({ length: n }, (_, i) =>
    makeAuditEntry({
      id: `entry-${i}`,
      timestamp: `2026-06-01T${String(10 + i).padStart(2, "0")}:00:00Z`,
    }),
  );
}

// ---------------------------------------------------------------------------
// fetch stub helpers
// ---------------------------------------------------------------------------

type FetchResponses = {
  auditEntries?: unknown[];
  rubricEntries?: unknown[];
};

function stubFetch({ auditEntries = [], rubricEntries = [] }: FetchResponses = {}) {
  const fn = vi.fn(async (url: string) => {
    if ((url as string).includes("rubric-audit")) {
      return new Response(JSON.stringify({ entries: rubricEntries }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if ((url as string).includes("audit-log")) {
      return new Response(JSON.stringify({ entries: auditEntries }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response("{}", { status: 404 });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

function renderPanel() {
  return render(<HistoryPanel product={PRODUCT} apiBaseUrl={API_BASE} />);
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("HistoryPanel", () => {
  it("shows loading state on mount", () => {
    // fetch never resolves — panel stays in loading state
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    renderPanel();
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("renders empty state when both APIs return no entries", async () => {
    stubFetch();
    renderPanel();
    await waitFor(() => {
      expect(screen.getByTestId("history-empty")).toBeInTheDocument();
    });
    expect(screen.getByTestId("history-empty").textContent).toMatch(/no history yet/i);
  });

  it("does NOT render history-toggle in the empty state", async () => {
    stubFetch();
    renderPanel();
    await waitFor(() => {
      expect(screen.getByTestId("history-empty")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("history-toggle")).not.toBeInTheDocument();
  });

  it("renders history-toggle when there are entries", async () => {
    stubFetch({ auditEntries: [makeAuditEntry()] });
    renderPanel();
    await waitFor(() => {
      expect(screen.getByTestId("history-toggle")).toBeInTheDocument();
    });
  });

  it("entries are hidden by default (collapsed)", async () => {
    stubFetch({ auditEntries: [makeAuditEntry()] });
    renderPanel();
    await waitFor(() => {
      expect(screen.getByTestId("history-toggle")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("history-entry")).not.toBeInTheDocument();
  });

  it("clicking toggle reveals history-entry elements", async () => {
    stubFetch({ auditEntries: [makeAuditEntry()] });
    renderPanel();
    const toggle = await screen.findByTestId("history-toggle");
    fireEvent.click(toggle);
    await waitFor(() => {
      expect(screen.getByTestId("history-entry")).toBeInTheDocument();
    });
  });

  it("clicking toggle a second time hides entries again", async () => {
    stubFetch({ auditEntries: [makeAuditEntry()] });
    renderPanel();
    const toggle = await screen.findByTestId("history-toggle");
    fireEvent.click(toggle);
    await waitFor(() => {
      expect(screen.getByTestId("history-entry")).toBeInTheDocument();
    });
    fireEvent.click(toggle);
    expect(screen.queryByTestId("history-entry")).not.toBeInTheDocument();
  });

  it("status-change entries carry data-testid history-entry and include action label text", async () => {
    stubFetch({ auditEntries: [makeAuditEntry({ action: "promote_primary" })] });
    renderPanel();
    const toggle = await screen.findByTestId("history-toggle");
    fireEvent.click(toggle);
    const entry = await screen.findByTestId("history-entry");
    expect(entry.textContent).toMatch(/promoted to primary/i);
  });

  it("rubric-save entries carry data-testid history-entry and include version delta text", async () => {
    stubFetch({ rubricEntries: [makeRubricRecord()] });
    renderPanel();
    const toggle = await screen.findByTestId("history-toggle");
    fireEvent.click(toggle);
    const entry = await screen.findByTestId("history-entry");
    expect(entry.textContent).toMatch(/rubric saved/i);
    expect(entry.textContent).toContain("v0.1");
    expect(entry.textContent).toContain("v0.2");
  });

  it("merges status and rubric entries and sorts newest-first", async () => {
    // rubric entry has a LATER timestamp — should appear first after sort
    stubFetch({
      auditEntries: [
        makeAuditEntry({ id: "older", timestamp: "2026-06-01T10:00:00Z" }),
      ],
      rubricEntries: [
        makeRubricRecord({ timestamp: "2026-06-01T11:00:00Z" }),
      ],
    });
    renderPanel();
    const toggle = await screen.findByTestId("history-toggle");
    fireEvent.click(toggle);
    const entries = await screen.findAllByTestId("history-entry");
    expect(entries).toHaveLength(2);
    // Newest first: rubric entry (11:00) before status entry (10:00)
    expect(entries[0]!.textContent).toMatch(/rubric saved/i);
    expect(entries[1]!.textContent).toMatch(/promoted to primary/i);
  });

  it("shows first 20 entries and a load-more button when total > 20", async () => {
    stubFetch({ auditEntries: makeEntries(25) });
    renderPanel();
    const toggle = await screen.findByTestId("history-toggle");
    fireEvent.click(toggle);
    await waitFor(() => {
      expect(screen.getAllByTestId("history-entry")).toHaveLength(20);
    });
    expect(screen.getByTestId("history-load-more")).toBeInTheDocument();
  });

  it("load-more button reveals additional entries", async () => {
    stubFetch({ auditEntries: makeEntries(25) });
    renderPanel();
    const toggle = await screen.findByTestId("history-toggle");
    fireEvent.click(toggle);
    await waitFor(() => {
      expect(screen.getAllByTestId("history-entry")).toHaveLength(20);
    });
    fireEvent.click(screen.getByTestId("history-load-more"));
    expect(screen.getAllByTestId("history-entry")).toHaveLength(25);
    expect(screen.queryByTestId("history-load-more")).not.toBeInTheDocument();
  });

  it("does NOT show load-more when total <= 20", async () => {
    stubFetch({ auditEntries: makeEntries(20) });
    renderPanel();
    const toggle = await screen.findByTestId("history-toggle");
    fireEvent.click(toggle);
    await waitFor(() => {
      expect(screen.getAllByTestId("history-entry")).toHaveLength(20);
    });
    expect(screen.queryByTestId("history-load-more")).not.toBeInTheDocument();
  });
});
