// Async server component — fetches the live scoreboard API and renders tier cards.
// ASSUMES: NEXT_PUBLIC_API_URL is set; falls back to localhost:8000 for local dev.

import { parseScoreboard, TIERS, WireScoreboard, TierId } from "@/lib/scoreboard";
import TierCard from "@/components/TierCard";

// The three tier IDs in the order the API always returns them.
const TIER_ORDER: TierId[] = ["tier_1", "tier_2", "tier_3"];

type FetchResult =
  | { ok: true; data: WireScoreboard }
  | { ok: false; error: string };

async function fetchScoreboard(product: string): Promise<FetchResult> {
  const apiUrl =
    process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  try {
    const res = await fetch(
      `${apiUrl}/api/products/${encodeURIComponent(product)}/scoreboard`,
      { cache: "no-store" }
    );

    if (res.status === 404) {
      const body = await res.json().catch(() => ({ detail: "Not found" }));
      return { ok: false, error: body.detail ?? "Unknown product or no runs" };
    }

    if (!res.ok) {
      return {
        ok: false,
        error: `API returned ${res.status} ${res.statusText}`,
      };
    }

    const data: WireScoreboard = await res.json();
    return { ok: true, data };
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Unknown network error";
    return { ok: false, error: `API not reachable: ${message}` };
  }
}

interface PageProps {
  searchParams: { product?: string };
}

export default async function ScoreboardPage({ searchParams }: PageProps) {
  const product = searchParams.product ?? "mli";
  const result = await fetchScoreboard(product);

  if (!result.ok) {
    return (
      <main className="min-h-screen bg-neutral-13 flex items-center justify-center p-8">
        <div className="max-w-md w-full bg-white border border-neutral-11 rounded-lg p-6 shadow-sm">
          <h1 className="text-lg font-semibold text-neutral-1 mb-2">
            Model Fitness Scoreboard
          </h1>
          <p className="text-sm text-neutral-5">{result.error}</p>
        </div>
      </main>
    );
  }

  const scoreboard = parseScoreboard(result.data);

  // Build a lookup so TierCards can get their candidates by tier_id.
  const candidatesByTier = Object.fromEntries(
    scoreboard.tiers.map((t) => [t.tier_id, t.candidates])
  );

  return (
    <main className="min-h-screen bg-neutral-13 p-8">
      <div className="max-w-5xl mx-auto">
        {/* Page header */}
        <div className="mb-6">
          <p className="text-xs font-semibold text-neutral-6 uppercase tracking-wide mb-1">
            Model Fitness · {product.toUpperCase()}
          </p>
          <h1 className="text-2xl font-semibold text-neutral-1 tracking-tight mb-1">
            Scoreboard
          </h1>
          <p className="text-xs text-neutral-6 font-mono">
            Run{" "}
            <span className="text-neutral-3">{scoreboard.run_id}</span>
            {" · "}
            Rubric{" "}
            <span data-testid="rubric-version" className="text-neutral-3">
              {scoreboard.rubric_version}
            </span>
            {" · "}
            Started{" "}
            <span className="text-neutral-3">
              {new Date(scoreboard.started_at).toLocaleString()}
            </span>
          </p>
        </div>

        {/* Tier cards */}
        <div className="flex flex-col gap-4">
          {TIER_ORDER.map((tierId) => (
            <TierCard
              key={tierId}
              tierId={tierId}
              meta={TIERS[tierId]}
              candidates={candidatesByTier[tierId] ?? []}
            />
          ))}
        </div>
      </div>
    </main>
  );
}
