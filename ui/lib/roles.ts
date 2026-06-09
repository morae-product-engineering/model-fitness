import { cookies } from "next/headers";

export type Role = "steward" | "viewer";

// Call only in server components or server actions — `next/headers` is
// server-only. Defaults to "viewer" (least privilege) when the cookie is
// absent so an unauthenticated render degrades safely.
// Effective role — view override (mmfp-role-view) takes precedence over auth.
export function readRole(): Role {
  const jar = cookies();
  const view = jar.get("mmfp-role-view")?.value;
  if (view === "steward" || view === "viewer") return view;
  const val = jar.get("mmfp-role")?.value;
  return val === "steward" ? "steward" : "viewer";
}

// Auth-granted role only — ignores any view override.
// Use to determine which roles are available to switch to.
export function readAuthRole(): Role {
  const val = cookies().get("mmfp-role")?.value;
  return val === "steward" ? "steward" : "viewer";
}
