// Curator page (MFP-76). Thin server component — passes product, tier, and
// apiBaseUrl down to the Curator client component.

import { resolveEnvLabel } from "@/lib/env";
import AppShell from "@/components/AppShell";
import Curator from "@/components/Curator";

function apiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
}

interface PageProps {
  searchParams: { product?: string; tier?: string };
}

export default function CuratorPage({ searchParams }: PageProps) {
  const product = searchParams.product ?? "mli";
  const tier = searchParams.tier ?? "tier_3";
  const env = resolveEnvLabel();
  const productMeta = { id: product, name: product.toUpperCase() };

  return (
    <AppShell env={env} rubricVersion="—" product={productMeta} activeTab="curator">
      <Curator product={product} tierId={tier} apiBaseUrl={apiBaseUrl()} />
    </AppShell>
  );
}
