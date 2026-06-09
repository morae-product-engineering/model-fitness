// Unit tests for TabNav (MLI-196).
//
// What we exercise:
//   - All three navigable tabs (scoreboard, editor, curator) plus history render
//     on every page, confirming the full nav shape is always present.
//   - Active tab receives data-active="true"; all others data-active="false".
//   - Navigable tabs carry the expected href link targets.
//   - All four tabs are now navigable (no data-disabled); History route shipped.

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import TabNav from "../../ui/components/TabNav";

// next/link is stubbed globally via vitest.config.ts resolve.alias (MLI-196)
// to avoid the dual-React-instance hook mismatch that occurs when next resolves
// to ui/node_modules/next.

describe("TabNav", () => {
  // -------------------------------------------------------------------------
  // All tabs visible on every page
  // -------------------------------------------------------------------------

  it("renders all four tabs regardless of which tab is active", () => {
    render(<TabNav activeTab="scoreboard" />);
    expect(screen.getByTestId("tab-scoreboard")).toBeInTheDocument();
    expect(screen.getByTestId("tab-editor")).toBeInTheDocument();
    expect(screen.getByTestId("tab-curator")).toBeInTheDocument();
    expect(screen.getByTestId("tab-history")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Active tab styling matches current route
  // -------------------------------------------------------------------------

  it("marks the curator tab active and all others inactive when activeTab='curator'", () => {
    render(<TabNav activeTab="curator" />);
    expect(screen.getByTestId("tab-curator")).toHaveAttribute("data-active", "true");
    expect(screen.getByTestId("tab-scoreboard")).toHaveAttribute("data-active", "false");
    expect(screen.getByTestId("tab-editor")).toHaveAttribute("data-active", "false");
  });

  // -------------------------------------------------------------------------
  // Link targets (hrefs) on navigable tabs
  // -------------------------------------------------------------------------

  it("renders correct href on each navigable tab", () => {
    render(<TabNav activeTab="scoreboard" />);
    expect(screen.getByTestId("tab-scoreboard")).toHaveAttribute(
      "href",
      "/scoreboard?product=mli",
    );
    expect(screen.getByTestId("tab-editor")).toHaveAttribute(
      "href",
      "/editor?product=mli",
    );
    expect(screen.getByTestId("tab-curator")).toHaveAttribute(
      "href",
      "/curator?product=mli",
    );
  });

  // -------------------------------------------------------------------------
  // All tabs navigable — no disabled tabs remain
  // -------------------------------------------------------------------------

  it("all four tabs are navigable (no data-disabled)", () => {
    render(<TabNav activeTab="scoreboard" />);
    for (const id of ["editor", "curator", "history"]) {
      expect(screen.getByTestId(`tab-${id}`)).not.toHaveAttribute("data-disabled", "true");
    }
  });

  it("renders correct href on history tab", () => {
    render(<TabNav activeTab="scoreboard" />);
    expect(screen.getByTestId("tab-history")).toHaveAttribute(
      "href",
      "/history?product=mli",
    );
  });
});
