/* global React */
// ============================================================
// MMFP — Mock data
// Realistic-feeling rubric, candidates, runs and dataset slice.
// All values are illustrative; no production data is implied.
// ============================================================

const MMFP_PRODUCTS = [
  { id: 'mli',     name: 'MLI',        full: 'Morae Legal Intelligence', status: 'active' },
  { id: 'product-b', name: 'Product B', full: 'Coming soon',              status: 'soon'   },
  { id: 'product-c', name: 'Product C', full: 'Coming soon',              status: 'soon'   },
];

// Rubric version starts here; Editor saves bump the patch number.
const MMFP_INITIAL_RUBRIC_VERSION = 'v0.1.4';

// Audit log seed — recent activity (rubric saves + promotions/rejections)
const MMFP_INITIAL_HISTORY = [
  { id: 'h1', kind: 'rubric_save',  at: '2026-04-29 14:02', actor: 'wayne.palmer',
    version: 'v0.1.4', tier: 't3', note: 'Reweight citation faithfulness toward synthesis after Q4 review.' },
  { id: 'h2', kind: 'promote',      at: '2026-04-28 17:18', actor: 'chris.tabb',
    candidate: 'opus-4-1', tier: 't3', toRole: 'primary', runId: 'run-2026-04-28-mli-r1',
    rationale: 'Sustained 92.1 composite over 3 quarters; citation gate clean; ARB consensus.' },
  { id: 'h3', kind: 'reject',       at: '2026-04-28 17:11', actor: 'chris.tabb',
    candidate: 'mistral-l-2', tier: 't3', runId: 'run-2026-04-28-mli-r1',
    rationale: 'Hallucination rate 3.4% — exceeds T3 gate of <2%. Recheck after vendor v3 release.' },
  { id: 'h4', kind: 'rubric_save',  at: '2026-04-22 09:47', actor: 'wayne.palmer',
    version: 'v0.1.3', tier: 't1', note: '' },
  { id: 'h5', kind: 'promote',      at: '2026-04-15 11:30', actor: 'wayne.palmer',
    candidate: 'ft-routing-v3', tier: 't1', toRole: 'primary', runId: 'run-2026-04-15-mli-r1',
    rationale: 'Beats Haiku 4.5 on accuracy and cost; latency well under p95 gate.' },
  { id: 'h6', kind: 'rubric_save',  at: '2026-04-08 16:21', actor: 'wayne.palmer',
    version: 'v0.1.2', tier: 't2', note: 'Doubled schema conformance gate weight.' },
];

const MMFP_TIERS = [
  {
    id: 't1', code: 'T1', accent: 'var(--yellow)',
    name: 'Classification & Routing',
    blurb: 'Cheap, fast, deterministic. Intent classification, query routing, structured triage.',
    weightCount: 5,
  },
  {
    id: 't2', code: 'T2', accent: 'var(--orange)',
    name: 'Structured Generation & Tool Use',
    blurb: 'Tool-calling, schema-bound output, multi-step extraction. The workhorse tier.',
    weightCount: 6,
  },
  {
    id: 't3', code: 'T3', accent: 'var(--warm-red)',
    name: 'Synthesis & Client-Facing Reasoning',
    blurb: 'Long-form synthesis, citations, advisory tone. Highest stakes; client-visible.',
    weightCount: 7,
  },
];

// Candidate models. Mix of frontier, fine-tunes, custom.
const MMFP_CANDIDATES = [
  // frontier
  { id: 'sonnet-4',      name: 'Claude Sonnet 4',         vendor: 'Anthropic', binding: 'Foundry',  family: 'frontier' },
  { id: 'opus-4-1',      name: 'Claude Opus 4.1',         vendor: 'Anthropic', binding: 'Foundry',  family: 'frontier' },
  { id: 'haiku-4-5',     name: 'Claude Haiku 4.5',        vendor: 'Anthropic', binding: 'Foundry',  family: 'frontier' },
  { id: 'gpt-4o',        name: 'GPT-4o',                  vendor: 'OpenAI',    binding: 'Foundry',  family: 'frontier' },
  { id: 'gpt-4-1-mini',  name: 'GPT-4.1-mini',            vendor: 'OpenAI',    binding: 'Foundry',  family: 'frontier' },
  { id: 'o4-mini',       name: 'o4-mini',                 vendor: 'OpenAI',    binding: 'Foundry',  family: 'frontier' },
  { id: 'gemini-2-5-pro',name: 'Gemini 2.5 Pro',          vendor: 'Google',    binding: 'Foundry',  family: 'frontier' },
  { id: 'gemini-2-5-fl', name: 'Gemini 2.5 Flash',        vendor: 'Google',    binding: 'Foundry',  family: 'frontier' },
  { id: 'mistral-l-2',   name: 'Mistral Large 2',         vendor: 'Mistral',   binding: 'Foundry',  family: 'frontier' },
  { id: 'llama-3-3-70b', name: 'Llama 3.3 70B Instruct',  vendor: 'Meta',      binding: 'Foundry',  family: 'frontier' },
  // fine-tunes
  { id: 'ft-routing-v3',  name: 'mli-routing-ft v3',      vendor: 'Morae',     binding: 'Foundry',  family: 'fine-tune', base: 'GPT-4.1-mini' },
  { id: 'ft-extract-v2',  name: 'mli-extract-ft v2',      vendor: 'Morae',     binding: 'Foundry',  family: 'fine-tune', base: 'Claude Haiku 4.5' },
  // custom
  { id: 'morai-synth-1',  name: 'MorAI-Synth-1 (custom)', vendor: 'Morae',     binding: 'Azure ML', family: 'custom' },
];

// Dimensions per tier. Each has weight (0-100) and gating flag.
const MMFP_DIMENSIONS = {
  t1: [
    { id: 'accuracy',     label: 'Routing accuracy',        weight: 35, gate: true,  gateText: '≥ 92%',  enabled: true,  unit: '%', desc: 'Top-1 intent label match against golden set.' },
    { id: 'latency',      label: 'Latency p95',             weight: 25, gate: true,  gateText: '≤ 600ms', enabled: true, unit: 'ms', desc: 'Server-side p95 across the routing dataset.' },
    { id: 'cost',         label: 'Cost per query',          weight: 20, gate: false, enabled: true, unit: '¢',  desc: 'Foundry-billed cost amortised per request.' },
    { id: 'robustness',   label: 'Robustness to paraphrase',weight: 15, gate: false, enabled: true, unit: '%',  desc: 'Stability across LLM-rephrased query variants.' },
    { id: 'safety',       label: 'Refusal calibration',     weight: 5,  gate: true,  gateText: '0 unsafe', enabled: true, unit: '%', desc: 'Refusal rate on benign queries (false positive).' },
  ],
  t2: [
    { id: 'schema',       label: 'Schema conformance',      weight: 25, gate: true,  gateText: '100%',  enabled: true, unit: '%',  desc: 'JSON Schema validation pass rate.' },
    { id: 'tool',         label: 'Tool selection',          weight: 20, gate: false, enabled: true, unit: '%',  desc: 'Correct tool chosen vs. golden tool transcripts.' },
    { id: 'extraction',   label: 'Extraction F1',           weight: 20, gate: false, enabled: true, unit: 'F1', desc: 'Span-level F1 on entity extraction tasks.' },
    { id: 'latency',      label: 'Latency p95',             weight: 15, gate: false, enabled: true, unit: 'ms', desc: 'p95 over multi-turn tool calls.' },
    { id: 'cost',         label: 'Cost per task',           weight: 15, gate: false, enabled: true, unit: '¢',  desc: 'Cost amortised per completed task.' },
    { id: 'safety',       label: 'PII leakage',             weight: 5,  gate: true,  gateText: '0 leaks', enabled: true, unit: '%', desc: 'Detected PII in outputs vs. allow-list.' },
  ],
  t3: [
    { id: 'synthesis',    label: 'Synthesis quality',       weight: 30, gate: false, enabled: true, unit: '/5', desc: 'LLM-judge composite (faithfulness × coverage × structure).' },
    { id: 'citation',     label: 'Citation faithfulness',   weight: 20, gate: true,  gateText: '≥ 95%', enabled: true, unit: '%', desc: 'Cited spans verifiable against source.' },
    { id: 'tone',         label: 'Advisory tone',           weight: 10, gate: false, enabled: true, unit: '/5', desc: 'Tone calibration vs. Morae voice rubric.' },
    { id: 'reasoning',    label: 'Reasoning depth',         weight: 15, gate: false, enabled: true, unit: '/5', desc: 'Multi-hop reasoning over long context.' },
    { id: 'latency',      label: 'Latency p95',             weight: 10, gate: false, enabled: true, unit: 's',  desc: 'Wall-clock p95, includes tool round-trips.' },
    { id: 'cost',         label: 'Cost per response',       weight: 10, gate: false, enabled: true, unit: '¢',  desc: 'Amortised cost per client-visible response.' },
    { id: 'safety',       label: 'Hallucination rate',      weight: 5,  gate: true,  gateText: '< 2%',  enabled: true, unit: '%', desc: 'Unsupported claims per response (judge-graded).' },
  ],
};

// Latest matrix run scores (per candidate, per tier). 0–100 composite + per-dim raw.
// NOTE: These are constructed so the leaders look plausible:
//   - T1 leader: ft-routing-v3 (cheap, fast, accurate)
//   - T2 leader: Sonnet 4 (Haiku 4.5 fallback)
//   - T3 leader: Opus 4.1 (Sonnet 4 fallback)
// Some candidates are gated out and become "rejected".
const MMFP_RUNS = {
  // [tier]: { [candidate]: { score, gates:{passed,failed[]}, dims:{ [dimId]: rawValue }, status, role } }
  t1: {
    'ft-routing-v3':  { composite: 91.2, role: 'primary',   status: 'approved', dims: { accuracy: 96.4, latency: 380, cost: 0.18, robustness: 92, safety: 0.4 } },
    'haiku-4-5':      { composite: 88.7, role: 'fallback',  status: 'approved', dims: { accuracy: 94.1, latency: 520, cost: 0.41, robustness: 89, safety: 0.5 } },
    'gpt-4-1-mini':   { composite: 86.2, role: '—',         status: 'eval',     dims: { accuracy: 93.0, latency: 610, cost: 0.55, robustness: 86, safety: 0.6 } },
    'gemini-2-5-fl':  { composite: 84.8, role: '—',         status: 'eval',     dims: { accuracy: 92.4, latency: 480, cost: 0.34, robustness: 81, safety: 1.1 } },
    'llama-3-3-70b':  { composite: 78.3, role: '—',         status: 'rejected', reason: 'Latency p95 gate failed (790ms > 600ms)', dims: { accuracy: 91.0, latency: 790, cost: 0.62, robustness: 84, safety: 0.7 } },
    'mistral-l-2':    { composite: 75.1, role: '—',         status: 'rejected', reason: 'Routing accuracy gate failed (89.2% < 92%)', dims: { accuracy: 89.2, latency: 540, cost: 0.48, robustness: 82, safety: 0.8 } },
  },
  t2: {
    'sonnet-4':       { composite: 89.3, role: 'primary',   status: 'approved', dims: { schema: 100, tool: 91, extraction: 0.88, latency: 1850, cost: 1.9, safety: 0.0 } },
    'haiku-4-5':      { composite: 84.6, role: 'fallback',  status: 'approved', dims: { schema: 100, tool: 86, extraction: 0.83, latency: 1100, cost: 0.7, safety: 0.0 } },
    'ft-extract-v2':  { composite: 82.9, role: '—',         status: 'eval',     dims: { schema: 100, tool: 79, extraction: 0.86, latency: 980,  cost: 0.5, safety: 0.0 } },
    'gpt-4o':         { composite: 81.5, role: '—',         status: 'eval',     dims: { schema: 99.6, tool: 88, extraction: 0.82, latency: 1620, cost: 2.4, safety: 0.0 } },
    'gemini-2-5-pro': { composite: 80.1, role: '—',         status: 'eval',     dims: { schema: 99.2, tool: 84, extraction: 0.80, latency: 1730, cost: 1.2, safety: 0.1 } },
    'mistral-l-2':    { composite: 73.4, role: '—',         status: 'rejected', reason: 'Schema conformance gate failed (97.8% < 100%)', dims: { schema: 97.8, tool: 78, extraction: 0.74, latency: 1400, cost: 0.9, safety: 0.0 } },
    'llama-3-3-70b':  { composite: 71.0, role: '—',         status: 'rejected', reason: 'Schema conformance gate failed (96.4% < 100%)', dims: { schema: 96.4, tool: 75, extraction: 0.71, latency: 1280, cost: 0.6, safety: 0.0 } },
  },
  t3: {
    'opus-4-1':       { composite: 92.1, role: 'primary',   status: 'approved', dims: { synthesis: 4.6, citation: 97.3, tone: 4.5, reasoning: 4.5, latency: 8.2, cost: 9.4, safety: 1.1 } },
    'sonnet-4':       { composite: 87.8, role: 'fallback',  status: 'approved', dims: { synthesis: 4.3, citation: 95.8, tone: 4.4, reasoning: 4.2, latency: 5.4, cost: 4.1, safety: 1.6 } },
    'gpt-4o':         { composite: 86.0, role: '—',         status: 'eval',     dims: { synthesis: 4.2, citation: 94.1, tone: 4.1, reasoning: 4.3, latency: 6.1, cost: 6.8, safety: 1.8 } },
    'gemini-2-5-pro': { composite: 84.4, role: '—',         status: 'eval',     dims: { synthesis: 4.1, citation: 93.0, tone: 4.0, reasoning: 4.2, latency: 7.0, cost: 4.6, safety: 2.0 } },
    'morai-synth-1':  { composite: 82.1, role: '—',         status: 'eval',     dims: { synthesis: 4.0, citation: 96.2, tone: 4.4, reasoning: 3.8, latency: 4.2, cost: 2.9, safety: 1.3 } },
    'o4-mini':        { composite: 79.9, role: '—',         status: 'rejected', reason: 'Citation faithfulness gate failed (91.2% < 95%)', dims: { synthesis: 4.0, citation: 91.2, tone: 3.8, reasoning: 4.1, latency: 5.8, cost: 3.2, safety: 2.1 } },
    'mistral-l-2':    { composite: 74.6, role: '—',         status: 'rejected', reason: 'Hallucination rate gate failed (3.4% > 2%)',     dims: { synthesis: 3.8, citation: 92.4, tone: 3.7, reasoning: 3.6, latency: 4.9, cost: 2.6, safety: 3.4 } },
  },
};

// Trend data: 6 quarterly runs, composite scores per candidate per tier.
// Slight noise; primary candidates trend up, rejected candidates flat or down.
const MMFP_TREND_LABELS = ['Q3 24', 'Q4 24', 'Q1 25', 'Q2 25', 'Q3 25', 'Q4 25'];
const MMFP_TRENDS = {
  t1: {
    'ft-routing-v3': [82.1, 84.6, 87.0, 88.5, 90.4, 91.2],
    'haiku-4-5':     [85.2, 86.1, 87.0, 87.9, 88.4, 88.7],
    'gpt-4-1-mini':  [83.4, 84.0, 84.9, 85.6, 85.9, 86.2],
    'gemini-2-5-fl': [80.3, 81.8, 82.6, 83.4, 84.2, 84.8],
    'llama-3-3-70b': [76.8, 77.1, 77.6, 78.0, 78.2, 78.3],
    'mistral-l-2':   [78.4, 77.9, 76.6, 76.0, 75.4, 75.1],
  },
  t2: {
    'sonnet-4':      [84.0, 85.6, 86.9, 87.8, 88.7, 89.3],
    'haiku-4-5':     [80.1, 81.5, 82.7, 83.5, 84.1, 84.6],
    'ft-extract-v2': [76.0, 78.4, 80.0, 81.4, 82.3, 82.9],
    'gpt-4o':        [82.4, 82.0, 81.9, 81.7, 81.6, 81.5],
    'gemini-2-5-pro':[77.2, 78.1, 78.9, 79.5, 79.9, 80.1],
    'mistral-l-2':   [73.0, 73.2, 73.4, 73.5, 73.4, 73.4],
    'llama-3-3-70b': [71.6, 71.4, 71.2, 71.0, 71.0, 71.0],
  },
  t3: {
    'opus-4-1':      [88.4, 89.6, 90.4, 91.0, 91.6, 92.1],
    'sonnet-4':      [82.1, 83.6, 85.0, 86.4, 87.2, 87.8],
    'gpt-4o':        [86.1, 86.0, 86.0, 86.0, 86.0, 86.0],
    'gemini-2-5-pro':[80.4, 81.5, 82.6, 83.5, 84.0, 84.4],
    'morai-synth-1': [null, null, 78.4, 80.1, 81.2, 82.1],
    'o4-mini':       [80.1, 80.3, 80.0, 79.9, 79.9, 79.9],
    'mistral-l-2':   [75.4, 75.0, 74.8, 74.7, 74.6, 74.6],
  },
};
// Drift signals (online observability — flagged as v0.2 but shown for demo)
const MMFP_DRIFT = [
  { id: 'd1', tier: 't3', candidate: 'opus-4-1', dim: 'citation',  delta: -2.4, severity: 'warn',
    summary: 'Citation faithfulness in production trailing eval by 2.4pp over 14d.', detected: '8d ago' },
  { id: 'd2', tier: 't2', candidate: 'sonnet-4', dim: 'latency',   delta: +18,  severity: 'warn',
    summary: 'p95 latency drifted +18% vs eval baseline; Foundry region instability suspected.', detected: '3d ago' },
  { id: 'd3', tier: 't1', candidate: 'ft-routing-v3', dim: 'cost', delta: +12, severity: 'info',
    summary: 'Cost per query up 12% — token-rate change on 2026-04-15.', detected: '16d ago' },
];

// Run metadata
const MMFP_LATEST_RUN = {
  id: 'run-2026-04-28-mli-r1',
  product: 'mli',
  rubricVersion: 'r1.4.0',
  startedAt: '2026-04-28T08:14:00Z',
  durationMin: 47,
  tasks: 1284,
  judgeCallsK: 3.2,
  costUsd: 184.20,
  langsmithUrl: 'https://smith.langchain.com/...',
  authors: ['wayne.palmer', 'ci-runner'],
};

// Curator: dataset slice + judge sample queue
const MMFP_DATASETS = [
  { id: 'mli-t1-routing',     tier: 't1', name: 'mli/routing-golden',     version: '2.4.1', count: 412, lastEdit: '2026-04-22', coverage: 0.86, owner: 'jagdish.k' },
  { id: 'mli-t2-extraction',  tier: 't2', name: 'mli/extraction-golden',  version: '1.8.0', count: 528, lastEdit: '2026-04-19', coverage: 0.79, owner: 'jagdish.k' },
  { id: 'mli-t2-tools',       tier: 't2', name: 'mli/tool-transcripts',   version: '0.6.2', count: 96,  lastEdit: '2026-04-10', coverage: 0.62, owner: 'wayne.palmer' },
  { id: 'mli-t3-synthesis',   tier: 't3', name: 'mli/synthesis-golden',   version: '1.2.0', count: 184, lastEdit: '2026-04-25', coverage: 0.71, owner: 'sme.review' },
  { id: 'mli-t3-citations',   tier: 't3', name: 'mli/citation-faithfulness',version:'0.9.1',count: 144, lastEdit: '2026-04-23', coverage: 0.68, owner: 'sme.review' },
  { id: 'shared-judge-cal',   tier: '—',  name: 'shared/judge-calibration',version:'1.0.0', count: 240, lastEdit: '2026-03-30', coverage: 0.92, owner: 'wayne.palmer' },
];

const MMFP_JUDGE_QUEUE = [
  { id: 'jq-001', dataset: 'mli/synthesis-golden', tier: 't3', candidate: 'opus-4-1', dim: 'synthesis',
    task: 'Summarise novation clauses in §3 of attached MSA and flag uncapped indemnities.',
    judgeScore: 4.2, judgeReason: 'Faithful synthesis; minor coverage gap on §3.4(b). Tone within rubric.', status: 'pending' },
  { id: 'jq-002', dataset: 'mli/citation-faithfulness', tier: 't3', candidate: 'sonnet-4', dim: 'citation',
    task: 'Cite the exact clause governing termination-for-convenience in this 84-page MSA.',
    judgeScore: 91, judgeReason: 'Citation [3] points to §11.2 but quoted span is from §11.4.', status: 'pending' },
  { id: 'jq-003', dataset: 'mli/extraction-golden', tier: 't2', candidate: 'ft-extract-v2', dim: 'extraction',
    task: 'Extract all parties, governing law, and effective date from the attached SOW.',
    judgeScore: 0.84, judgeReason: 'Missed alias for "Customer" in §1.1; otherwise clean.', status: 'agree' },
  { id: 'jq-004', dataset: 'mli/synthesis-golden', tier: 't3', candidate: 'gpt-4o', dim: 'synthesis',
    task: 'Compare liability caps across the three attached supplier agreements.',
    judgeScore: 3.6, judgeReason: 'Conflated cap on direct vs consequential damages in supplier C.', status: 'disagree',
    note: 'Disagree — supplier C cap is correctly identified; judge mis-read §9.2.' },
  { id: 'jq-005', dataset: 'mli/citation-faithfulness', tier: 't3', candidate: 'morai-synth-1', dim: 'citation',
    task: 'Identify the change-of-control trigger and quote it.',
    judgeScore: 96, judgeReason: 'Exact span match; correct §6.4(a) reference.', status: 'pending' },
];

Object.assign(window, {
  MMFP_PRODUCTS, MMFP_TIERS, MMFP_CANDIDATES, MMFP_DIMENSIONS,
  MMFP_RUNS, MMFP_TREND_LABELS, MMFP_TRENDS, MMFP_DRIFT,
  MMFP_LATEST_RUN, MMFP_DATASETS, MMFP_JUDGE_QUEUE,
  MMFP_INITIAL_RUBRIC_VERSION, MMFP_INITIAL_HISTORY,
});
