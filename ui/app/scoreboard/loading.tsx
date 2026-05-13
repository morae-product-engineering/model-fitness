// Next.js App Router loading.tsx — renders while the async ScoreboardPage
// awaits the API fetch. Three placeholder panels, one per tier.
// No testids here; none of these elements are read by the acceptance tests.

export default function ScoreboardLoading() {
  return (
    <div
      className="min-h-screen p-8"
      style={{ background: "var(--neutral-13)" }}
    >
      <div className="max-w-5xl mx-auto">
        {/* Three tier card placeholders */}
        <div className="flex flex-col gap-4">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="bg-white border border-neutral-11 rounded-lg p-5 shadow-sm"
            >
              <div className="h-4 w-48 bg-neutral-11 rounded animate-pulse mb-2" />
              <div className="h-3 w-72 bg-neutral-11 rounded animate-pulse mb-4" />
              <div className="space-y-2">
                <div className="h-8 bg-neutral-12 rounded animate-pulse" />
                <div className="h-8 bg-neutral-12 rounded animate-pulse" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
