// Async server component — fetches the live scoreboard API and renders tier cards.
// ASSUMES: NEXT_PUBLIC_API_URL is set; falls back to localhost:8000 for local dev.

import {
  parseScoreboard,
  parseTrends,
  TIERS,
  Trends,
  WireScoreboard,
  WireTrends,
  TierId,
} from "@/lib/scoreboard";
import { resolveEnvLabel } from "@/lib/env";
import { readRole } from "@/lib/roles";
import TierCard from "@/components/TierCard";
import AppShell from "@/components/AppShell";
import Link from "next/link";

// The three tier IDs in the order the API always returns them.
const TIER_ORDER: TierId[] = ["tier_1", "tier_2", "tier_3"];

// Hardcoded for MLI-186 — configurable run-count is explicitly out of scope.
const TREND_RUNS = 10;

interface DriftSignal {
  candidate_id: string;
  tier_id: string;
  severity: string;
  status: string;
}

interface DriftResult {
  signals: DriftSignal[];
  active_count: number;
}

async function fetchDriftSignals(product: string): Promise<DriftResult> {
  try {
    const res = await fetch(
      `${apiBaseUrl()}/api/products/${encodeURIComponent(product)}/drift/signals`,
      { cache: "no-store" },
    );
    if (!res.ok) return { signals: [], active_count: 0 };
    return (await res.json()) as DriftResult;
  } catch {
    return { signals: [], active_count: 0 };
  }
}

type FetchResult =
  | { ok: true; data: WireScoreboard }
  | { ok: false; error: string };

function apiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
}

async function fetchScoreboard(product: string): Promise<FetchResult> {
  try {
    const res = await fetch(
      `${apiBaseUrl()}/api/products/${encodeURIComponent(product)}/scoreboard`,
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

// Best-effort trends fetch — a missing or failing trends response degrades to
// the scorecard alone rather than failing the page. The trends endpoint also
// 404s when no runs have ever been recorded (already a scoreboard-page error)
// so missing data here is benign in practice.
async function fetchTrends(
  product: string,
  tier: TierId,
): Promise<Trends | null> {
  try {
    const res = await fetch(
      `${apiBaseUrl()}/api/products/${encodeURIComponent(
        product,
      )}/trends?tier=${tier}&runs=${TREND_RUNS}`,
      { cache: "no-store" },
    );
    if (!res.ok) return null;
    const data: WireTrends = await res.json();
    return parseTrends(data);
  } catch {
    return null;
  }
}

interface PageProps {
  searchParams: { product?: string };
}

export default async function ScoreboardPage({ searchParams }: PageProps) {
  const product = searchParams.product ?? "mli";
  const env = resolveEnvLabel();
  const role = readRole();
  const productMeta = { id: product, name: product.toUpperCase() };
  const result = await fetchScoreboard(product);
  const drift = await fetchDriftSignals(product);

  if (!result.ok) {
    return (
      <AppShell
        env={env}
        rubricVersion="—"
        product={productMeta}
        activeTab="scoreboard"
        role={role}
      >
        <div className="flex items-center justify-center p-8">
          <div className="max-w-md w-full bg-white border border-neutral-11 rounded-lg p-6 shadow-sm">
            <h1 className="text-lg font-semibold text-neutral-1 mb-2">
              Model Fitness Scoreboard
            </h1>
            <p className="text-sm text-neutral-5">{result.error}</p>
          </div>
        </div>
      </AppShell>
    );
  }

  const scoreboard = parseScoreboard(result.data);

  // Build a lookup so TierCards can get their candidates by tier_id.
  const candidatesByTier = Object.fromEntries(
    scoreboard.tiers.map((t) => [t.tier_id, t.candidates])
  );

  // Browser-reachable API URL for client-side fetches (candidate-detail
  // drill-down, MLI-187). NEXT_PUBLIC_API_URL is inlined at build time, so
  // this resolves the same way client and server.
  const clientApiBaseUrl =
    process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  // Parallel fetch one trends payload per tier. Sibling server-side fetches
  // run concurrently; a failure on any one tier degrades to scorecard-only
  // (handled in TierCard via the optional `trends` prop).
  const trendsByTier = Object.fromEntries(
    await Promise.all(
      TIER_ORDER.map(async (tierId) => [
        tierId,
        await fetchTrends(product, tierId),
      ] as const),
    ),
  ) as Record<TierId, Trends | null>;

  return (
    <AppShell
      env={env}
      runId={scoreboard.run_id}
      rubricVersion={scoreboard.rubric_version}
      product={productMeta}
      activeTab="scoreboard"
      role={role}
    >
      <div className="p-8">
        <div className="max-w-5xl mx-auto">
          {drift.active_count > 0 && (
            <div
              data-testid="drift-banner"
              className="mb-4 flex items-center gap-3 bg-light-yellow border border-yellow-300 rounded-lg px-4 py-3 text-sm"
            >
              <span className="font-semibold text-neutral-1">
                <span data-testid="drift-signal-count">{drift.active_count}</span>
                {" "}active drift signal{drift.active_count !== 1 ? "s" : ""}
              </span>
              <Link
                href={`/monitor?product=${encodeURIComponent(product)}`}
                data-testid="drift-monitor-link"
                className="ml-auto text-xs underline text-neutral-3 hover:text-neutral-1"
              >
                View in Monitor →
              </Link>
            </div>
          )}
          <div className="flex flex-col gap-4">
            {TIER_ORDER.map((tierId) => (
              <TierCard
                key={tierId}
                tierId={tierId}
                meta={TIERS[tierId]}
                candidates={candidatesByTier[tierId] ?? []}
                trends={trendsByTier[tierId] ?? undefined}
                product={product}
                apiBaseUrl={clientApiBaseUrl}
              />
            ))}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
