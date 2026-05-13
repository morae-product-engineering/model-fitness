// Resolves the label shown in the app-shell environment badge.
// Reads NEXT_PUBLIC_MMFP_ENV when set (Container Apps wires it explicitly per
// environment); falls back to NODE_ENV-derived defaults so local dev shows
// "DEV" without infra config.

export function resolveEnvLabel(): string {
  const explicit = process.env.NEXT_PUBLIC_MMFP_ENV;
  if (explicit) return explicit;
  if (process.env.NODE_ENV === "development") return "DEV";
  // ASSUMES: any deployed container without NEXT_PUBLIC_MMFP_ENV is the dev
  // Container App; the staging/prod envs will set the var when they exist.
  return "DEV";
}
