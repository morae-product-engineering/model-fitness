"use server";

import { cookies } from "next/headers";
import type { Role } from "./roles";

// Sets a view-override cookie so the user can switch between role contexts
// without re-authenticating. No capability cap — this is a dev convenience;
// the basic auth gate is temporary (pending Entra SSO) and the backend
// enforces its own role checks independently.
export async function switchRole(next: Role): Promise<void> {
  cookies().set("mmfp-role-view", next, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
  });
}
