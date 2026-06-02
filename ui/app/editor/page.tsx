// Async server component — fetches the live rubric and renders the Editor.
// ASSUMES: NEXT_PUBLIC_API_URL is set; falls back to localhost:8000 for local dev.

import { resolveEnvLabel } from "@/lib/env";
import type { RubricReadResponse } from "@/lib/rubric";
import AppShell from "@/components/AppShell";
import RubricEditor from "@/components/RubricEditor";

function apiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
}

interface PageProps {
  searchParams: { product?: string };
}

export default async function EditorPage({ searchParams }: PageProps) {
  const product = searchParams.product ?? "mli";
  const env = resolveEnvLabel();
  const productMeta = { id: product, name: product.toUpperCase() };
  const base = apiBaseUrl();

  let data: RubricReadResponse | null = null;
  let errorMsg: string | null = null;

  try {
    const res = await fetch(
      `${base}/api/products/${encodeURIComponent(product)}/rubric`,
      { cache: "no-store" },
    );
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
      errorMsg = body.detail ?? `API returned ${res.status} ${res.statusText}`;
    } else {
      data = (await res.json()) as RubricReadResponse;
    }
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown network error";
    errorMsg = `API not reachable: ${msg}`;
  }

  if (!data) {
    return (
      <AppShell
        env={env}
        rubricVersion="—"
        product={productMeta}
        activeTab="editor"
      >
        <div className="flex items-center justify-center p-8">
          <div className="max-w-md w-full bg-white border border-neutral-11 rounded-lg p-6 shadow-sm">
            <h1 className="text-lg font-semibold text-neutral-1 mb-2">
              Rubric Editor
            </h1>
            <p className="text-sm text-neutral-5">{errorMsg}</p>
          </div>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell
      env={env}
      rubricVersion={data.version}
      product={productMeta}
      activeTab="editor"
    >
      <RubricEditor
        product={product}
        apiBaseUrl={base}
        initialRubric={data.rubric}
        version={data.version}
      />
    </AppShell>
  );
}
