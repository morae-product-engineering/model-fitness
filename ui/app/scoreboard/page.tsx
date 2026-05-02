// Server component — fetches from the MMFP API at build/request time.
// ASSUMES: NEXT_PUBLIC_API_URL is set; falls back to localhost:8000 for local dev.
// TODO(MLI-???): replace skeleton endpoint with real /api/runs once Slice 2 is wired.

interface SkeletonRun {
  weighted_score: number;
  source: string;
}

type FetchResult =
  | { ok: true; data: SkeletonRun }
  | { ok: false; error: string };

async function fetchSkeletonRun(): Promise<FetchResult> {
  const apiUrl =
    process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  try {
    // cache: 'no-store' — this is a development skeleton; no caching needed yet.
    const res = await fetch(`${apiUrl}/api/runs/skeleton`, {
      cache: "no-store",
    });

    if (!res.ok) {
      return {
        ok: false,
        error: `API returned ${res.status} ${res.statusText}`,
      };
    }

    const data: SkeletonRun = await res.json();
    return { ok: true, data };
  } catch (err) {
    // Network failure (API not running, DNS resolution failure, etc.)
    const message =
      err instanceof Error ? err.message : "Unknown network error";
    return { ok: false, error: `API not reachable: ${message}` };
  }
}

export default async function ScoreboardPage() {
  const result = await fetchSkeletonRun();

  if (!result.ok) {
    return (
      <main className="min-h-screen bg-white flex items-center justify-center p-8">
        <div className="max-w-md w-full bg-neutral-12 border border-neutral-11 rounded-lg p-6 shadow-sm">
          <h1 className="text-lg font-semibold text-neutral-1 mb-2">
            Model Fitness Scoreboard
          </h1>
          <p className="text-sm text-neutral-5">
            {result.error}
          </p>
        </div>
      </main>
    );
  }

  const { weighted_score, source } = result.data;

  return (
    <main className="min-h-screen bg-white p-8">
      <div className="max-w-lg mx-auto">
        {/* Page header — mirrors prototype SectionHeader style */}
        <div className="mb-6">
          <p className="text-xs font-semibold text-neutral-6 uppercase tracking-wide mb-1">
            Walking Skeleton
          </p>
          <h1 className="text-2xl font-semibold text-neutral-1 tracking-tight">
            Model Fitness Scoreboard
          </h1>
        </div>

        {/* Score card — white background, subtle border, matches prototype Panel */}
        <div className="bg-white border border-neutral-11 rounded-lg p-5 shadow-sm">
          <div className="mb-4">
            <p className="text-xs font-semibold text-neutral-6 uppercase tracking-wide mb-1">
              Weighted Score
            </p>
            <p
              data-testid="skeleton-score"
              className="text-5xl font-semibold text-neutral-1 tabular-nums"
            >
              {weighted_score}
            </p>
          </div>

          <hr className="border-neutral-11 mb-4" />

          <div>
            <p className="text-xs font-semibold text-neutral-6 uppercase tracking-wide mb-1">
              Source
            </p>
            <p
              data-testid="skeleton-source"
              className="text-sm text-neutral-3 font-mono"
            >
              {source}
            </p>
          </div>
        </div>
      </div>
    </main>
  );
}
