// Unit tests for the Monitor view (MFP-98).
//
// MonitorPage is an async server component — called as a plain async function
// and the resulting JSX rendered with RTL. This avoids RSC runner requirements
// while still exercising the full render path, including signal rows.
//
// What we exercise:
//   - Renders drift-signal-row elements for each seeded signal
//   - Each row contains drift-signal-candidate and drift-signal-severity
//   - Shows the "No drift signals found" empty state when signals array is empty
//
// Dependencies mocked:
//   - @/lib/roles      → readRole, bypassing next/headers (server-only)
//   - global.fetch     → returns seeded signals from the drift API
//
// next/headers is aliased to tests/stubs/next-headers.ts in vitest.config.ts
// so the import resolves even without the full Next.js runtime.

import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";

// Mock readRole before MonitorPage is imported so it never touches next/headers.
vi.mock("@/lib/roles", () => ({
  readRole: () => "viewer" as const,
}));

import MonitorPage from "../../ui/app/monitor/page";

const SEEDED_SIGNALS = [
  {
    candidate_id: "kimi-k2-6",
    tier_id: "tier_1",
    severity: "high",
    status: "active",
    summary: "Composite score dropped 30 points vs baseline",
    delta: "-30",
    detected_at: "2026-06-01T00:00:00Z",
  },
  {
    candidate_id: "gpt-4o",
    tier_id: "tier_2",
    severity: "medium",
    status: "active",
    summary: "Latency degraded 15 points vs baseline",
    delta: "-15",
    detected_at: "2026-06-02T00:00:00Z",
  },
];

function mockFetch(signals = SEEDED_SIGNALS, rubricVersion = "v0.3") {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      if (String(url).includes("/drift/signals")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({ signals, active_count: signals.length }),
        });
      }
      // rubric version fetch
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ version: rubricVersion }),
      });
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetAllMocks();
});

describe("MonitorPage — seeded signals", () => {
  it("renders one drift-signal-row per signal", async () => {
    mockFetch();
    const jsx = await MonitorPage({ searchParams: { product: "mli" } });
    render(jsx);

    const rows = screen.getAllByTestId("drift-signal-row");
    expect(rows).toHaveLength(SEEDED_SIGNALS.length);
  });

  it("each row shows the candidate_id in drift-signal-candidate", async () => {
    mockFetch();
    const jsx = await MonitorPage({ searchParams: { product: "mli" } });
    render(jsx);

    expect(screen.getByText("kimi-k2-6")).toBeInTheDocument();
    expect(screen.getByText("gpt-4o")).toBeInTheDocument();
  });

  it("each row shows the severity in drift-signal-severity", async () => {
    mockFetch();
    const jsx = await MonitorPage({ searchParams: { product: "mli" } });
    render(jsx);

    const severities = screen.getAllByTestId("drift-signal-severity");
    const texts = severities.map((el) => el.textContent);
    expect(texts).toContain("high");
    expect(texts).toContain("medium");
  });

  it("each row shows the delta", async () => {
    mockFetch();
    const jsx = await MonitorPage({ searchParams: { product: "mli" } });
    render(jsx);

    expect(screen.getByText("-30")).toBeInTheDocument();
  });
});

describe("MonitorPage — empty state", () => {
  it("shows the empty-state message when no signals are returned", async () => {
    mockFetch([]);
    const jsx = await MonitorPage({ searchParams: { product: "mli" } });
    render(jsx);

    expect(screen.queryAllByTestId("drift-signal-row")).toHaveLength(0);
    expect(screen.getByText("No drift signals found.")).toBeInTheDocument();
  });
});
