// AUTH-REMOVAL: when Entra SSO lands, delete:
//   1. this file (ui/middleware.ts) and its test (tests/unit/ui-middleware.test.ts)
//   2. BASIC_AUTH_USER and BASIC_AUTH_PASS env vars on Container App ca-mmfp-ui-dev
//   3. Key Vault secrets `basic-auth-user` and `basic-auth-pass`
//   4. `httpCredentials` block in playwright.config.ts
//   5. MMFP_BASIC_AUTH_USER and MMFP_BASIC_AUTH_PASS env vars on the e2e job
//      in .github/workflows/ci.yml
//   6. GitHub repo secrets MMFP_BASIC_AUTH_USER and MMFP_BASIC_AUTH_PASS
//   7. "Running Playwright locally" note in README.md
//
// HTTP Basic Auth gate for the dev UI. Temporary; small handful of users behind
// Container Apps rate limiting. Threat model does not warrant timing-safe compare.

import { NextResponse, type NextRequest } from "next/server";

const REALM = "MMFP dev";
const HEALTH_PATHS = new Set(["/health", "/healthz", "/_health"]);

type Role = "steward" | "viewer";
type Decision = { kind: "pass"; role: Role } | { kind: "reject" };

type CredConfig = { user: string; pass: string; role: Role };

// Build the ordered list of valid credential pairs from env.
// Checked in order: steward pair, viewer pair, legacy BASIC_AUTH alias (steward).
// An empty list means no credentials are configured → fail closed.
function buildCredentials(env: Record<string, string | undefined>): CredConfig[] {
  const creds: CredConfig[] = [];
  const stewardUser = env.STEWARD_USER ?? "";
  const stewardPass = env.STEWARD_PASS ?? "";
  if (stewardUser && stewardPass) creds.push({ user: stewardUser, pass: stewardPass, role: "steward" });

  const viewerUser = env.VIEWER_USER ?? "";
  const viewerPass = env.VIEWER_PASS ?? "";
  if (viewerUser && viewerPass) creds.push({ user: viewerUser, pass: viewerPass, role: "viewer" });

  // Legacy alias: BASIC_AUTH_USER/PASS maps to steward role.
  const legacyUser = env.BASIC_AUTH_USER ?? "";
  const legacyPass = env.BASIC_AUTH_PASS ?? "";
  if (legacyUser && legacyPass) creds.push({ user: legacyUser, pass: legacyPass, role: "steward" });

  return creds;
}

// Pure decision so unit tests don't need NextRequest/NextResponse.
// Fails closed: no recognised credential pair in env = reject every request.
export function decideAuth(
  authHeader: string | null | undefined,
  env: Record<string, string | undefined>,
): Decision {
  const credentials = buildCredentials(env);
  if (credentials.length === 0) return { kind: "reject" };

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

  for (const cred of credentials) {
    if (givenUser === cred.user && givenPass === cred.pass) {
      return { kind: "pass", role: cred.role };
    }
  }
  return { kind: "reject" };
}

export function middleware(req: NextRequest): NextResponse {
  if (HEALTH_PATHS.has(req.nextUrl.pathname)) {
    return NextResponse.next();
  }

  const decision = decideAuth(req.headers.get("authorization"), process.env);
  if (decision.kind === "pass") return NextResponse.next();

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
