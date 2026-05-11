// MLI-178: vitest-only stub for `next/server`.
//
// ui/middleware.ts imports from `next/server`, but the next package only
// exists under ui/node_modules. The root vitest job runs from the repo root
// where the package is unresolvable, breaking the whole unit-typescript CI
// job. ui-middleware.test.ts further intercepts these exports with vi.mock,
// so this stub only needs to be import-resolvable.

export class NextResponse {
  constructor(_body?: BodyInit | null, _init?: ResponseInit) {}
  static next() {
    return new NextResponse();
  }
}

export type NextRequest = Request & { nextUrl: { pathname: string } };
