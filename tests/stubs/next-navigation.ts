// MLI-195: vitest-only stub for `next/navigation`.
//
// next is only installed in ui/node_modules; the root vitest job can't
// resolve `next/navigation` when RubricEditor.tsx imports it. Tests that
// need the real behaviour use vi.mock("next/navigation", ...) to override
// this stub inline — all they need is that this file is import-resolvable.

export function useRouter() {
  return { refresh: () => {} };
}

export function usePathname() {
  return "/";
}

export function useSearchParams() {
  return new URLSearchParams();
}
