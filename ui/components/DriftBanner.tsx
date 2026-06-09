// Standalone drift banner — mounts on any page without modifying
// CandidateDetail or History. Renders nothing when activeCount is zero.
// Testid contract (pinned by slice-07-drift.spec.ts):
//   drift-banner        container, visible iff activeCount >= 1
//   drift-signal-count  element whose text is the active count
//   drift-monitor-link  link navigating to the Monitor view

import Link from "next/link";

interface DriftBannerProps {
  activeCount: number;
  product: string;
}

export default function DriftBanner({ activeCount, product }: DriftBannerProps) {
  if (activeCount === 0) return null;

  return (
    <div
      data-testid="drift-banner"
      className="mb-4 flex items-center gap-3 bg-light-yellow border border-yellow-300 rounded-lg px-4 py-3 text-sm"
    >
      <span className="font-semibold text-neutral-1">
        <span data-testid="drift-signal-count">{activeCount}</span>
        {" "}active drift signal{activeCount !== 1 ? "s" : ""}
      </span>
      <Link
        href={`/monitor?product=${encodeURIComponent(product)}`}
        data-testid="drift-monitor-link"
        className="ml-auto text-xs underline text-neutral-3 hover:text-neutral-1"
      >
        View in Monitor →
      </Link>
    </div>
  );
}
