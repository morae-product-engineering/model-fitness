# CLAUDE.md — agent guidance for `morae-product-engineering/model-fitness`

This file is read automatically by Claude Code (and other AI coding agents) when working in this repository. It describes how the repo is structured, what conventions are non-negotiable, and what to do when starting any piece of work.

If you are an AI agent reading this: read it fully before making changes. If you are a human reading this: this is the contract we hold AI agents to.

## What this repo is

The Morae Model Fitness Platform (MMFP). An internal Morae product that scores LLM candidate models against a versioned rubric, producing scorecards humans use to decide which models to designate as primary or fallback for a given AI product (MLI is the first consumer).

This is **an assessment tool, not a deployment tool.** The platform records evidence and recommendations. It does not control runtime model selection in other products — those products read the recommendation and update their own configuration.

Reference docs:
- Product hypothesis: `https://morae.atlassian.net/wiki/spaces/MLI/pages/213549111/Model+Fitness+Platform`
- Architectural approach: `https://morae.atlassian.net/wiki/spaces/MLI/pages/218530029/MFP+Architecture`
- Architectural principles (P1–P10): `https://morae.atlassian.net/wiki/spaces/MLI/pages/146571276/Architectural+Principles`
- Rubric reference (v0.1): `https://morae.atlassian.net/wiki/spaces/MLI/pages/218628525/Model+Fitness+Rubric+-+Reference+Document`
- Decisions: `ADRs/` (MADR format, one file per decision)

The Jira epic is **MLI-104** in the `MLI` project at `morae.atlassian.net`. Sub-tasks have prompts written for AI execution; you will be given a sub-task to do, not asked to invent one.

## Stack

- **Language:** Python 3.12 (backend), TypeScript (frontend, tests)
- **Backend:** FastAPI, Pydantic v2, SQLite (R1), pytest
- **Frontend:** Next.js, React, Tailwind, vitest
- **Tests:** Playwright for end-to-end, pytest for Python, vitest for TypeScript
- **Infra:** Azure (Container Apps, Container Registry, Key Vault, Storage, Application Insights), GitHub Actions, OIDC federated auth (no long-lived secrets)
- **Reporting:** TestRail as top-level test reporting; Playwright HTML report as engineering-facing detail
- **Observability:** LangSmith for agent quality / evals; Application Insights for infra
- **External services:** Azure AI Foundry for model hosting (binding plugin abstracts this)

## Hard rules — never violate

These are non-negotiable. If you find yourself wanting to break one, stop and ask the human.

1. **Never commit secrets.** Not in code, not in tests, not in fixtures, not in `.env` files committed to the repo. Secrets live in Azure Key Vault or GitHub Actions secrets only. If you generate a fixture that needs a secret-like string, use `"REDACTED"` or a clearly fake value like `"sk-fake-test-key-xxxxxx"`.
2. **Never commit directly to `main`.** Every change goes via a feature branch and a pull request, even one-line fixes.
3. **Never force-push to a shared branch.** `main` and any branch with an open PR are off-limits.
4. **Never delete or rename files outside the working scope** of the sub-task you're on. If you genuinely need to, ask first.
5. **Never modify CI/CD pipeline definitions, infrastructure config, or security policy** without explicit human approval — *unless* the sub-task you're working on explicitly asks you to (e.g. a sub-task to author the CI workflow). The default is "ask first"; the sub-task description overrides this if it explicitly authorises the change.
6. **Never modify the public contract of a stable boundary** without explicit human approval. The four plugin interfaces (`EvaluatorPlugin`, `BindingPlugin`, `ReporterPlugin`, `SensorPlugin`) are P3 stable boundaries — implementation behind them can change freely; their signatures cannot.

## Default workflow per sub-task

When given a sub-task:

1. **Read the sub-task description in full** via the Atlassian MCP, including its acceptance criteria. If anything is ambiguous, ask before starting work — do not guess.
2. **Read the parent slice task** to understand what slice you're contributing to.
3. **Check what already exists.** Run `tree -L 3` or equivalent. Don't recreate things that exist; don't break things you don't need to touch.
4. **Make a branch.** Branch name from the Jira sub-task ID: MLI-XXX/<short-description> (e.g. MLI-158/acceptance-test). The Jira ID is the unit of work; the slice context is recoverable from the parent task. Don't use slice-XX/... — older sub-task descriptions reference that pattern, but it's superseded by this rule.
5. **Write the test first** if there isn't one already. The whole repo is built on TDD/ATDD. The acceptance test for a slice is written *before* the implementation. Unit tests are written *with* the code they test, not after.
6. **Implement the smallest thing that makes the test pass.** Don't anticipate future needs (P1 — earn complexity).
7. **Refactor only if you have a green test.** Refactoring without test coverage is editing.
8. **Commit in coherent small chunks.** Commit messages: present tense, imperative, max 72 chars first line. Body if needed. Reference the Jira sub-task: `Add Playwright reporter (MLI-218)`.
9. **Open a PR.** PR description: summarise *what* changed and *why*, link the Jira sub-task. Don't just dump the commit messages.
10. **Close the loop in Jira.** See "Closing the loop" below.

## Closing the loop

When you have completed a sub-task to the point where the PR is open and ready for human review, you complete the loop yourself in Jira. Do not write the summary to chat for the human to copy-paste — post it directly.

Steps:

1. **Transition the Jira sub-task to `In Review`** via the Atlassian MCP (`transitionJiraIssue`).
2. **Add a comment to the Jira sub-task** (`addCommentToJiraIssue`) containing your summary. The comment includes:
   - **Branch and PR URL** — so the human can jump straight to the diff.
   - **Files changed** — bullet list with one-line description per file.
   - **Acceptance criteria** — each one quoted, marked ✅ / ⚠️ / ❌, with a short note on how it was verified. Distinguish between behaviours you ran and behaviours you only proved via mocks.
   - **Decisions worth review** — anywhere you made a judgement call the human might want to revisit. Be honest, not defensive.
   - **Anything pending** — env vars, credentials, infrastructure not yet in place, follow-ups.

The human (Wayne) takes it from there: reviews the PR, merges it, and transitions the ticket to `Done` after merge.

**Do not transition to `Done` yourself.** That's the human's call after merge.

## When to ask the human

You are allowed to make any decision that doesn't change a stable boundary or a test surface. You **must ask** before:

- **Adding a new dependency** (Python or npm) that isn't already named in CLAUDE.md or in the sub-task brief. Show what alternatives you considered. Dependencies already named here or in the brief are pre-authorised — install as needed.
- **Modifying a plugin interface** (the P3 boundaries listed above).
- **Modifying CI workflows** (`.github/workflows/*.yml`) outside of a sub-task that explicitly asks you to author or change them.
- **Modifying infrastructure config** (`infra/`) outside of a sub-task that explicitly asks you to.
- **Changing the test surface** of an existing test (renaming, deleting, weakening assertions).
- **Designing a new architectural concept** that doesn't have an ADR yet. If your work needs one, propose the ADR first; don't bury architecture inside an implementation PR.

Things you do **not** need to ask about:

- Naming variables, structuring functions, picking idioms within the existing language.
- Adding tests, refactoring for clarity within a tested unit, writing comments.
- Adding new files in clearly-scoped locations (e.g. a new evaluator under `mmfp/evaluators/deterministic/`).
- Picking between two implementation paths that produce the same observable behaviour.

When in doubt, write a one-line message describing what you're about to do and ask "OK to proceed?" — short ask, no preamble. The human will say yes, no, or "do this instead" within minutes.

## Comments

Write comments that a future human or AI agent would thank you for. Specifically:

- **Comment the *why*, not the *what*.** Code shows what; comments explain decisions, trade-offs, gotchas, why-not-the-obvious-thing.
- **Use type hints and pydantic models for *what*.** A pydantic field `cost_usd: float = Field(description="Cost in USD for this invocation")` is better than a comment.
- **Mark assumptions explicitly.** `# ASSUMES: caller has validated rubric_version exists` is useful. Silent assumptions cause bugs.
- **Mark TODOs with a Jira reference** if the work is real. `# TODO(MLI-242): replace with rubric.fetch_active() once MLO graph is wired`.
- **Don't write narrative comments.** "First, we initialise the client. Then we call the API." is noise.

## Logging

- Use structured logs. Python: `structlog` (preferred — confirm with the human if a different library is already established when you arrive). TypeScript: `pino` or equivalent.
- Log at the boundaries: API request received, external call made, external call returned. Don't log every line of business logic.
- Never log secrets, API keys, full request bodies that may contain user data, or full LLM completions in production paths.
- Use `INFO` for normal flow, `WARNING` for recoverable problems, `ERROR` for failures the system can't fix itself.

## Tests

- **Unit tests** sit next to the code: `mmfp/core/foo.py` has tests in `mmfp/core/tests/test_foo.py` (Python) or `ui/components/Foo.test.tsx` (TypeScript). Mock external dependencies; test logic in isolation.
- **Integration tests** sit in `mmfp/tests/` (Python) and exercise the boundary between modules with real-but-local dependencies (e.g. real SQLite, mocked HTTP).
- **End-to-end tests** sit in `tests/e2e/` and run via Playwright against the deployed dev environment. One per slice as the slice-level acceptance test.
- **All tests must be deterministic.** No reliance on wall-clock time, no random seeds without explicit fixing, no order-dependence between tests.

The TestRail reporter (in `tests/reporters/testrail-reporter.ts`) auto-creates TestRail cases from Playwright test titles on first run. The test code is the source of truth for the test catalogue. Don't manually create cases in TestRail and reference them from code.

When confirming acceptance criteria, distinguish between behaviours you have **actually run** (with real or simulated env vars) and behaviours you have only **proved via mocks**. Be explicit about which is which. The human deciding to merge needs to know.

## Architecture documentation

Architectural decisions are recorded as ADRs in `ADRs/` using MADR format (one page max). When implementing a sub-task whose acceptance includes an ADR, write the ADR first as a draft, get it reviewed, then implement.

ADR titles use the form `NNNN-short-decision-title.md` where `NNNN` is the next free number. Don't reuse numbers from superseded ADRs; mark the old one as superseded and write a new one with the next number.

## What you should not do without being asked

- Build a UI component you weren't asked for, however helpful it might be.
- Add a "while I was here" refactor of unrelated code.
- Optimise for performance without measurement showing it's needed.
- Add a configuration option for a hypothetical future need.
- Generate documentation that duplicates the code (READMEs that just list filenames, etc.).

## Subagents and model selection

The repo defines three subagents in `.claude/agents/`:

- **`quick`** — Haiku. Mechanical edits inside one or two files. Typo fixes, single-line changes, renames, mechanical updates that don't need reasoning.
- **`junior-dev`** — Sonnet. The default. Well-defined sub-tasks, scaffolding, implementation against clear specs.
- **`senior-dev`** — Opus. Ambiguous specs, novel logic, multi-file debugging, anything where the prompt itself is the work — i.e. you have to think before you can implement.

Each Claude Code sub-task in Jira has a `## Recommended model` field. Translate it:
- "Haiku" → `quick`
- "Sonnet" → `junior-dev`
- "Opus" → `senior-dev`

The human invokes the subagent at session start with words like *"Use the senior-dev subagent for MLI-218."* If you find yourself running as the wrong tier — e.g. the prompt is more ambiguous than the recommended model suggested — say so at the top of your response and ask whether to escalate before doing the work.

## When this file is wrong

This file will become wrong over time. When you notice it's out of step with reality (a convention has shifted, a stack component has been replaced, a hard rule no longer holds), say so explicitly in your output. Don't silently follow stale rules.

Updates to this file are themselves PRs that need human review.
