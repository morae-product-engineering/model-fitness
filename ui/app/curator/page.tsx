// Placeholder server component for the Curator route (MLI-196).
// This stub exists so the Curator tab is navigable in the app shell.
// Slice 6 will replace this with real content from ui/prototype/curator.jsx —
// that prototype is deliberately NOT lifted here (out of scope for MLI-196).

import { redirect } from "next/navigation";
import { resolveEnvLabel } from "@/lib/env";
import { readRole } from "@/lib/roles";
import AppShell from "@/components/AppShell";

interface PageProps {
  searchParams: { product?: string };
}

export default function CuratorPage({ searchParams }: PageProps) {
  const product = searchParams.product ?? "mli";
  const role = readRole();
  if (role === "viewer") redirect(`/scoreboard?product=${product}`);

  const env = resolveEnvLabel();
  const productMeta = { id: product, name: product.toUpperCase() };

  return (
    <AppShell env={env} rubricVersion="—" product={productMeta} activeTab="curator">
      <div className="flex items-center justify-center p-8">
        <div
          data-testid="curator-placeholder"
          className="max-w-md w-full bg-white border border-neutral-11 rounded-lg p-6 shadow-sm text-center"
        >
          <h1 className="text-lg font-semibold text-neutral-1 mb-2">Curator</h1>
          <p className="text-sm text-neutral-5">Coming in Slice 6</p>
        </div>
      </div>
    </AppShell>
  );
}
