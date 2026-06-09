// Unit tests for DriftBanner (MFP-98).
//
// What we exercise:
//   - Renders nothing when activeCount is 0 (acceptance criterion)
//   - Shows the active count and banner container when activeCount > 0
//   - Shows singular "signal" at count 1, plural "signals" at count > 1
//   - The drift-monitor-link href encodes the product correctly

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import DriftBanner from "../../ui/components/DriftBanner";

describe("DriftBanner — zero count", () => {
  it("renders nothing when activeCount is 0", () => {
    const { container } = render(
      <DriftBanner activeCount={0} product="mli" />,
    );
    expect(container.firstChild).toBeNull();
  });
});

describe("DriftBanner — active count", () => {
  it("shows the drift-banner container when activeCount > 0", () => {
    render(<DriftBanner activeCount={3} product="mli" />);
    expect(screen.getByTestId("drift-banner")).toBeInTheDocument();
  });

  it("displays the active count in drift-signal-count", () => {
    render(<DriftBanner activeCount={3} product="mli" />);
    expect(screen.getByTestId("drift-signal-count")).toHaveTextContent("3");
  });

  it("uses plural 'signals' when count is greater than 1", () => {
    render(<DriftBanner activeCount={3} product="mli" />);
    expect(screen.getByTestId("drift-banner")).toHaveTextContent(
      "3 active drift signals",
    );
  });

  it("uses singular 'signal' when count is exactly 1", () => {
    render(<DriftBanner activeCount={1} product="mli" />);
    expect(screen.getByTestId("drift-banner")).toHaveTextContent(
      "1 active drift signal",
    );
    expect(screen.getByTestId("drift-banner")).not.toHaveTextContent(
      "1 active drift signals",
    );
  });

  it("renders the drift-monitor-link pointing to the Monitor view", () => {
    render(<DriftBanner activeCount={2} product="mli" />);
    const link = screen.getByTestId("drift-monitor-link");
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "/monitor?product=mli");
  });

  it("URL-encodes the product in the monitor link", () => {
    render(<DriftBanner activeCount={1} product="my product" />);
    expect(screen.getByTestId("drift-monitor-link")).toHaveAttribute(
      "href",
      "/monitor?product=my%20product",
    );
  });
});
