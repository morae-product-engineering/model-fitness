// Vendor inference for the candidate slate. Frontend-only display concern:
// no backend field, no schema change. The slate carries `candidate_id` (a
// stable kebab-case identifier like `gpt-4o`, `llama-4-scout-17b-16e-instruct`)
// and we project it onto a vendor label via a prefix table.
//
// The mapping convention is surfaced as architectural-input on MLI-267 so the
// Slice 4 Editor (MLI-190) and any future UI that wants to badge candidates
// inherits the same rule rather than re-deciding. The prototype's `vendor`
// field on its mock data (ui/prototype/data.jsx:60-69) is the source for the
// human-readable labels — keep these spellings in sync.
//
// Unknown prefix returns `null`, which the UI surfaces as a neutral "—"
// badge rather than a guessed label. The dev seeder's `(unknown)` deployment
// rows (mmfp/api/scoreboard.py:178) end up here too.

export type Vendor =
  | "OpenAI"
  | "Meta"
  | "Mistral"
  | "Moonshot"
  | "Microsoft"
  | "Anthropic"
  | "Google";

// Ordered by specificity-of-prefix so e.g. `gpt-4-1-mini` resolves before
// `gpt-4o` would; the iteration finds the first matching prefix. Keep
// `id.startsWith(prefix)` semantics: the prefix is matched as a literal at
// the start of the candidate id with no separator stripping.
const VENDOR_BY_PREFIX: ReadonlyArray<readonly [string, Vendor]> = [
  ["gpt-", "OpenAI"],
  ["o4-", "OpenAI"],
  ["llama-", "Meta"],
  ["mistral-", "Mistral"],
  ["kimi-", "Moonshot"],
  ["phi-", "Microsoft"],
  ["claude-", "Anthropic"],
  ["opus-", "Anthropic"],
  ["sonnet-", "Anthropic"],
  ["haiku-", "Anthropic"],
  ["gemini-", "Google"],
];

export function inferVendor(candidateId: string): Vendor | null {
  const id = candidateId.toLowerCase();
  for (const [prefix, vendor] of VENDOR_BY_PREFIX) {
    if (id.startsWith(prefix)) return vendor;
  }
  return null;
}
