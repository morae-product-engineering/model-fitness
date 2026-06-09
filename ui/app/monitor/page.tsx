// Monitor view — lists active drift signals for a product (MFP-92, Slice 7).
// Server component; fetches drift signals from the API on each request.

import { resolveEnvLabel } from "@/lib/env";
import { readRole } from "@/lib/roles";
import AppShell from "@/components/AppShell";

function apiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "localhost:8000";
}

interface DriftSignal {
  candidate_id: string;
  tier_id: string;
  severity: string;
  status: string;
  summary: string;
  delta: string;
  detected_at: string;
}

async function fetchSignals(
  product: string,
): Promise<{ signals: DriftSignal[]; active_count: number }> {
  try {
    const res = await fetch(
      `${apiBaseUrl()}/api/products/${encodeURIComponent(product)}/drift/signals?status=all`,
      { cache: "no-store" },
    );
    if (!res.ok) return { signals: [], active_count: 0 };
    return await res.json();
  } catch {
    return { signals: [], active_count: 0 };
  }
}

async function fetchRubricVersion(product: string): Promise<string> {
  try {
    const res = await fetch(
      `${apiBaseUrl()}/api/products/${encodeURIComponent(product)}/rubric`,
      { cache: "no-store" },
    );
    if (!res.ok) return "—";
    const data = await res.json();
    return data.version ?? "—";
  } catch {
    return "—";
  }
}

interface PageProps {
  searchParams: { product?: string };
}

export default async function MonitorPage({ searchParams }: PageProps) {
  const product = searchParams.product ?? "mli";
  const env = resolveEnvLabel();
  const role = readRole();
  const productMeta = { id: product, name: product.toUpperCase() };

  const [{ signals }, rubricVersion] = await Promise.all([
    fetchSignals(product),
    fetchRubricVersion(product),
  ]);

  return (
    <AppShell
      env={env}
      rubricVersion={rubricVersion}
      product={productMeta}
      activeTab="scoreboard"
      role={role}
    >
      <div className="p-8">
        <div className="max-w-5xl mx-auto">
          <h1 className="text-lg font-semibold text-neutral-1 mb-6">
            Drift Monitor · {productMeta.name}
          </h1>
          {signals.length === 0 ? (
            <p className="text-sm text-neutral-5">No drift signals found.</p>
          ) : (
            <div className="flex flex-col gap-3">
              {signals.map((signal, i) => (
                <div
                  key={i}
                  data-testid="drift-signal-row"
                  className="bg-white border border-neutral-11 rounded-lg p-4 shadow-sm"
                >
                  <div className="flex items-center gap-3 mb-2">
                    <span
                      data-testid="drift-signal-severity"
                      className="text-xs font-semibold uppercase tracking-wide px-2 py-0.5 rounded bg-light-red text-warm-red"
                    >
                      {signal.severity}
                    </span>
                    <span
                      data-testid="drift-signal-candidate"
                      className="font-mono text-sm font-semibold text-neutral-1"
                    >
                      {signal.candidate_id}
                    </span>
                    <span className="text-xs text-neutral-6">
                      {signal.tier_id}
                    </span>
                  </div>
                  <p className="text-sm text-neutral-3">{signal.summary}</p>
                  <div className="mt-2 flex items-center gap-4 text-xs text-neutral-6">
                    <span>
                      Δ{" "}
                      <span className="font-mono text-warm-red">
                        {signal.delta}
                      </span>
                    </span>
                    <span>{signal.detected_at}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
