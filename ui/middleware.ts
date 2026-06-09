// AUTH-REMOVAL: when Entra SSO lands, delete:
//   1. this file (ui/middleware.ts) and its test (tests/unit/ui-middleware.test.ts)
//   2. BASIC_AUTH_USER/BASIC_AUTH_PASS, STEWARD_USER/STEWARD_PASS, VIEWER_USER/VIEWER_PASS
//      env vars on Container App ca-mmfp-ui-dev
//   3. Key Vault secrets `basic-auth-user` and `basic-auth-pass`
//   4. `httpCredentials` block in playwright.config.ts
//   5. MMFP_BASIC_AUTH_USER and MMFP_BASIC_AUTH_PASS env vars on the e2e job
//      in .github/workflows/ci.yml
//   6. GitHub repo secrets MMFP_BASIC_AUTH_USER and MMFP_BASIC_AUTH_PASS
//   7. "Running Playwright locally" note in README.md
//
// HTTP Basic Auth gate with two roles:
//   steward — full access (rubric editor, curator, all decision actions)
//   viewer  — scoreboard + history + decisions; no editor/curator
//
// Credential pairs in env (both optional; at least one must be configured):
//   STEWARD_USER / STEWARD_PASS           — steward role
//   BASIC_AUTH_USER / BASIC_AUTH_PASS     — also maps to steward (backwards compat)
//   VIEWER_USER / VIEWER_PASS             — viewer role
//
// Role is written to the `mmfp-role` httpOnly cookie on every successful
// response so server components can read it without re-parsing the header.
// Fails closed: if no credential pair is configured, every request is rejected.

import { NextResponse, type NextRequest } from "next/server";

const REALM = "MMFP dev";
const HEALTH_PATHS = new Set(["/health", "/healthz", "/_health"]);
const ROLE_COOKIE = "mmfp-role";

export type Role = "steward" | "viewer";
type Decision = { kind: "pass"; role: Role } | { kind: "reject" };

function credentialPairs(
  env: Record<string, string | undefined>,
): Array<{ user: string; pass: string; role: Role }> {
  const pairs: Array<{ user: string; pass: string; role: Role }> = [];
  // STEWARD_USER/PASS takes precedence over the legacy BASIC_AUTH_USER/PASS alias.
  const su = (env.STEWARD_USER ?? env.BASIC_AUTH_USER ?? "").trim();
  const sp = (env.STEWARD_PASS ?? env.BASIC_AUTH_PASS ?? "").trim();
  if (su && sp) pairs.push({ user: su, pass: sp, role: "steward" });
  const vu = (env.VIEWER_USER ?? "").trim();
  const vp = (env.VIEWER_PASS ?? "").trim();
  if (vu && vp) pairs.push({ user: vu, pass: vp, role: "viewer" });
  return pairs;
}

// Pure decision so unit tests don't need NextRequest/NextResponse.
// Fails closed: no configured pairs = reject every request.
export function decideAuth(
  authHeader: string | null | undefined,
  env: Record<string, string | undefined>,
): Decision {
  const pairs = credentialPairs(env);
  if (pairs.length === 0) return { kind: "reject" };

  if (!authHeader || !authHeader.startsWith("Basic ")) {
    return { kind: "reject" };
  }

  let decoded: string;
  try {
    decoded = atob(authHeader.slice("Basic ".length).trim());
  } catch {
    return { kind: "reject" };
  }

  const sep = decoded.indexOf(":");
  if (sep < 0) return { kind: "reject" };
  const givenUser = decoded.slice(0, sep);
  const givenPass = decoded.slice(sep + 1);

  const matched = pairs.find(
    (p) => p.user === givenUser && p.pass === givenPass,
  );
  return matched ? { kind: "pass", role: matched.role } : { kind: "reject" };
}

export function middleware(req: NextRequest): NextResponse {
  if (HEALTH_PATHS.has(req.nextUrl.pathname)) {
    return NextResponse.next();
  }

  const decision = decideAuth(req.headers.get("authorization"), process.env);
  if (decision.kind === "pass") {
    const res = NextResponse.next();
    res.cookies.set(ROLE_COOKIE, decision.role, {
      httpOnly: true,
      sameSite: "lax",
      path: "/",
    });
    return res;
  }

  return new NextResponse("Authentication required", {
    status: 401,
    headers: {
      "WWW-Authenticate": `Basic realm="${REALM}", charset="UTF-8"`,
      "Content-Type": "text/plain; charset=utf-8",
    },
  });
}

// Skip framework static assets at the matcher level so the function never runs
// for them. Health paths are skipped inside the function.
export const config = {
  matcher: ["/((?!_next/static|_next/image|_next/data|favicon\\.ico).*)"],
};
