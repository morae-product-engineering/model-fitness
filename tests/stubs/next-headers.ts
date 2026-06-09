// Vitest-only stub for `next/headers`.
//
// next is only installed under ui/node_modules; the root vitest job can't
// resolve `next/headers`. Tests that need real behaviour (readRole) use
// vi.mock("next/headers", ...) to override this stub — all they need is that
// this file is import-resolvable.

export function cookies() {
  return {
    get: (_name: string) => undefined,
  };
}

export function headers() {
  return new Headers();
}
