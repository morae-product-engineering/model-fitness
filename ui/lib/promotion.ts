// API helpers and wire types for promote / reject / audit-log endpoints
// (mmfp/api/promotion.py). All three functions are best-effort and return
// structured results rather than throwing so callers decide how to surface errors.

import { Status, TierId } from "./scoreboard";

export type DecisionKind = "promote_primary" | "promote_fallback" | "reject";

export interface PendingDecision {
  kind: DecisionKind;
  displayName: string;
  deployment: string;
  tierId: TierId;
}

export interface AuditEntry {
  id: string;
  action: string;
  tier_id: TierId;
  candidate_deployment: string;
  previous_status: Status;
  new_status: Status;
  rationale: string;
  rubric_version_at_time: string;
  run_id_at_time: string;
  actor: string;
  timestamp: string;
  sequence: number;
}

type ActionResult = { ok: true } | { ok: false; error: string };

export async function promoteCandidate(
  apiBaseUrl: string,
  product: string,
  deployment: string,
  tierId: TierId,
  role: "primary" | "fallback",
  rationale: string,
): Promise<ActionResult> {
  try {
    const res = await fetch(
      `${apiBaseUrl}/api/products/${encodeURIComponent(product)}/candidates/${encodeURIComponent(deployment)}/promote`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tier_id: tierId, role, rationale }),
      },
    );
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      return { ok: false, error: body.detail ?? `API returned ${res.status}` };
    }
    return { ok: true };
  } catch (err) {
    return {
      ok: false,
      error: err instanceof Error ? err.message : "Network error",
    };
  }
}

export async function rejectCandidate(
  apiBaseUrl: string,
  product: string,
  deployment: string,
  tierId: TierId,
  rationale: string,
): Promise<ActionResult> {
  try {
    const res = await fetch(
      `${apiBaseUrl}/api/products/${encodeURIComponent(product)}/candidates/${encodeURIComponent(deployment)}/reject`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tier_id: tierId, rationale }),
      },
    );
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      return { ok: false, error: body.detail ?? `API returned ${res.status}` };
    }
    return { ok: true };
  } catch (err) {
    return {
      ok: false,
      error: err instanceof Error ? err.message : "Network error",
    };
  }
}

export interface RubricAuditRecord {
  product: string;
  previous_version: string;
  new_version: string;
  note: string | null;
  steward: string;
  timestamp: string;
  schema_version: number;
}

// Returns at most 10 entries newest-first; empty array on any failure.
export async function fetchAuditLog(
  apiBaseUrl: string,
  product: string,
  deployment: string,
): Promise<AuditEntry[]> {
  try {
    const url = `${apiBaseUrl}/api/products/${encodeURIComponent(product)}/audit-log?candidate=${encodeURIComponent(deployment)}&limit=10`;
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) return [];
    const data = await res.json();
    return (data.entries ?? []) as AuditEntry[];
  } catch {
    return [];
  }
}

// Returns at most `limit` rubric save records newest-first; empty array on any failure.
export async function fetchRubricAudit(
  apiBaseUrl: string,
  product: string,
  limit = 50,
): Promise<RubricAuditRecord[]> {
  try {
    const url = `${apiBaseUrl}/api/products/${encodeURIComponent(product)}/rubric-audit?limit=${limit}`;
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) return [];
    const data = await res.json();
    return (data.entries ?? []) as RubricAuditRecord[];
  } catch {
    return [];
  }
}
