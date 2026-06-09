import { cookies } from "next/headers";

export type Role = "steward" | "viewer";

// Call only in server components or server actions — `next/headers` is
// server-only. Defaults to "viewer" (least privilege) when the cookie is
// absent so an unauthenticated render degrades safely.
export function readRole(): Role {
  const val = cookies().get("mmfp-role")?.value;
  return val === "steward" ? "steward" : "viewer";
}
