// MLI-AUTH-BASIC: Basic Auth middleware unit tests.
//
// `next/server` is only installed under ui/node_modules, so the root vitest
// runner can't resolve it. Mock to a minimal shape — we only need the module
// to load; the pure `decideAuth` is what we exercise.

import { describe, expect, it, vi } from "vitest";

vi.mock("next/server", () => ({
  NextResponse: {
    next: () => ({ kind: "next" }),
  },
}));

import { decideAuth } from "../../ui/middleware";

const ENV_OK = { BASIC_AUTH_USER: "wayne", BASIC_AUTH_PASS: "sekret" };
const header = (u: string, p: string) =>
  "Basic " + Buffer.from(`${u}:${p}`).toString("base64");

describe("MLI-AUTH-BASIC: Basic Auth middleware", () => {
  it("MLI-AUTH-BASIC: rejects when no Authorization header is sent (-> 401)", () => {
    expect(decideAuth(null, ENV_OK).kind).toBe("reject");
    expect(decideAuth(undefined, ENV_OK).kind).toBe("reject");
  });

  it("MLI-AUTH-BASIC: rejects wrong credentials (-> 401)", () => {
    expect(decideAuth(header("nope", "sekret"), ENV_OK).kind).toBe("reject");
    expect(decideAuth(header("wayne", "wrong"), ENV_OK).kind).toBe("reject");
  });

  it("MLI-AUTH-BASIC: passes correct credentials (-> 200)", () => {
    expect(decideAuth(header("wayne", "sekret"), ENV_OK).kind).toBe("pass");
  });

  it("MLI-AUTH-BASIC: fails closed when env vars are missing or empty", () => {
    const valid = header("wayne", "sekret");
    expect(decideAuth(valid, {}).kind).toBe("reject");
    expect(
      decideAuth(valid, { BASIC_AUTH_USER: "", BASIC_AUTH_PASS: "" }).kind,
    ).toBe("reject");
    expect(decideAuth(valid, { BASIC_AUTH_USER: "wayne" }).kind).toBe("reject");
    expect(decideAuth(valid, { BASIC_AUTH_PASS: "sekret" }).kind).toBe(
      "reject",
    );
  });
});
