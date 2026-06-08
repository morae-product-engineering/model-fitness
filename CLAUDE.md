# CLAUDE.md — agent contract for `model-fitness`

How to work in this repo if you're an AI coding agent. If you're a human reading this, it's the contract we hold AI agents to.

## What this repo is

The Morae Model Fitness Platform (MMFP). An internal Morae product that scores LLM candidate models against a versioned rubric and produces scorecards humans use to designate primary/fallback models for AI products. **Assessment, not deployment.** Other products read the recommendation and update their own configuration; this platform doesn't control runtime model selection.

Jira epic: **MLI-104**. Project: `MLI` at `morae.atlassian.net`. Sub-tasks contain prompts written for AI execution — you'll be assigned one, not asked to invent one.

## Stack

| Layer       | Choice                                                            |
| ----------- | ----------------------------------------------------------------- |
| Backend     | Python 3.12, FastAPI, Pydantic v2, SQLite (R1), pytest             |
| Frontend    | Next.js, React, Tailwind, vitest                                   |
| Tests       | Playwright (E2E), pytest, vitest                                   |
| Infra       | Azure Container Apps, ACR, Key Vault, Storage, App Insights        |
| CI/CD       | GitHub Actions, OIDC federated auth (no long-lived secrets)        |
| Reporting   | TestRail (top-level), Playwright HTML report (engineering detail)  |
| Observ.     | LangSmith (agent quality), App Insights (infra)                    |
| Models      | Azure AI Foundry (binding plugin abstracts this)                   |

## Four working rules

These map to MLI architectural principles P1, P3, P7, P9.

1. **Think before coding (P9 — hypothesis in, evidence out).** State assumptions. If two interpretations exist, present both — don't pick silently. If a simpler approach exists, say so. If unclear, stop and ask.
2. **Earn complexity (P1).** Minimum code that solves the problem. No speculation, no single-use abstractions, no error handling for impossible scenarios. If 200 lines could be 50, rewrite it.
3. **Surgical changes (P3 — stable boundaries).** Every changed line traces to the request. Match existing style. Don't refactor or reformat adjacent code. Mention orphans you spot; don't act on them unless your own changes created them.
4. **Goal-driven execution (P7 — testability).** Write the test first. Slice acceptance tests exist *before* the implementation; unit tests are written *with* the code. Verify acceptance empirically — actually run the tests, don't just claim they pass.

## Hard rules

| Don't                                                  | Do instead                                                            |
| ------------------------------------------------------ | --------------------------------------------------------------------- |
| Commit secrets — code, fixtures, `.env`, anywhere      | Azure Key Vault or GHA secrets only; fixtures use `"sk-fake-test-key-xxx"` |
| Commit to `main` directly                              | Feature branch + PR, even one-line fixes                              |
| Force-push a shared branch                             | New commits or rebase on a private branch only                        |
| Modify CI/CD, infra, or security config                | Ask first — *unless* the sub-task brief explicitly authorises it      |
| Modify the public contract of a P3 plugin interface    | Implementation is yours; signatures need explicit human approval      |
| Delete or rename files outside the sub-task scope      | Ask before touching anything not in the sub-task brief                |

P3 plugin interfaces: `EvaluatorPlugin`, `BindingPlugin`.

## Default workflow per sub-task

1. Read the Jira sub-task in full via the Atlassian MCP. If anything is ambiguous, ask before starting.
2. Read the parent slice task to see what slice you're contributing to.
3. `tree -L 3` to see what already exists. Don't duplicate; don't break what you don't need to touch.
4. Branch from the sub-task ID: `MFP-XXX/<short-description>` (e.g. `MFP-32/playwright-reporter`).
5. Write the test first (or confirm one exists).
6. Implement the smallest thing that makes it pass.
7. Refactor only against a green test.
8. Commit small. Imperative tense, ≤72 chars first line, reference the Jira ID: `Add Playwright reporter (MFP-32)`.
9. Open a PR. Summarise *what* and *why*; link the Jira sub-task.
10. Close the loop in Jira (next section).

## Closing the loop

When the PR is open and ready for human review, you finish in Jira yourself. Don't write the summary to chat for the human to copy-paste — post it directly via the Atlassian MCP.

1. **Transition to `In Review`** (`transitionJiraIssue`).
2. **Add a comment** (`addCommentToJiraIssue`) containing:
   - Branch and PR URL.
   - Files changed — one-line description per file.
   - Acceptance criteria — each one quoted, marked ✅ / ⚠️ / ❌, with how you verified it. Distinguish behaviours you actually ran from behaviours you only proved via mocks.
   - Decisions worth review — judgement calls the human might want to revisit. Honest, not defensive.
   - Anything pending — env vars, credentials, infrastructure not yet in place, follow-ups.

The human (Wayne) reviews, merges, and transitions to `Done`. **Don't transition to `Done` yourself.**

## When to ask vs. when to decide

| Situation                                                    | Action                                |
| ------------------------------------------------------------ | ------------------------------------- |
| New dependency not named in this file or the sub-task brief  | Ask. Show alternatives considered.    |
| Modify a P3 plugin interface                                 | Ask.                                  |
| Modify CI workflows or infra outside the sub-task scope      | Ask.                                  |
| Change the test surface of an existing test                  | Ask.                                  |
| Naming, structuring, idioms within an existing language      | Decide.                               |
| Add tests, refactor for clarity within a tested unit         | Decide.                               |
| New file in a clearly-scoped location                        | Decide.                               |
| Two implementation paths with the same observable behaviour  | Decide.                               |

When in doubt: one-line message, no preamble, "OK to proceed?". Wayne replies in minutes.

## Subagents

Each Jira sub-task has a `## Recommended model` field. Translate it:

| Recommended model | Subagent           | When                                     |
| ----------------- | ------------------ | ---------------------------------------- |
| Haiku             | `helper`           | Mechanical edits, no thinking required   |
| Sonnet            | `engineer`         | Well-defined sub-tasks, clear specs      |
| Opus              | `senior-engineer`  | Ambiguous specs, design, novel logic     |

If you're running as the wrong tier — the prompt is more ambiguous than the recommended model expected — say so at the top of your response and ask whether to escalate. Don't push through.

## Comments, logs, tests

**Comments:** explain *why*, not *what*. Type hints and pydantic descriptions cover *what*. Mark assumptions explicitly: `# ASSUMES: caller has validated rubric_version`. TODOs reference Jira: `# TODO(MFP-NNN): replace with rubric.fetch_active()`.

**Logs:** structured (`structlog` for Python, `pino` for TS — confirm if a different one is already established). Log at boundaries: API request received, external call made, external call returned. Never log secrets, full request bodies that may contain user data, or full LLM completions in production paths.

**Tests:**
- Unit — next to the code (`mmfp/engine/tests/test_foo.py`, `ui/components/Foo.test.tsx`). Mock external dependencies.
- Integration — `mmfp/tests/`. Real-but-local dependencies (real SQLite, mocked HTTP).
- E2E — `tests/e2e/`. Playwright against the deployed dev environment. One per slice as the slice acceptance test.

**Slice acceptance tests:** Tests that gate a slice's completion (deliberately red until the slice's implementation lands) are marked with `@pytest.mark.slice_acceptance` (or module-level `pytestmark = pytest.mark.slice_acceptance`). The standard `Unit Tests (pytest)` CI job excludes them; a separate `Slice Acceptance Tests (pytest)` job runs them with `continue-on-error: true` so deliberate-red doesn't block downstream CI. When the slice's implementation lands and the test goes green, the marker stays on the file — its purpose is identification, not a temporary skip.

**Defer imports of not-yet-existent symbols into the test body**, not the module top-level. Module-level imports that fail (`from mmfp.engine.matrix import MatrixEngine` before MFP-39 lands) cause pytest collection to fail BEFORE `-m` filtering can deselect the test, blocking the whole pipeline. With the import inside the test body, the file collects cleanly, the test FAILs (assertion-time) rather than ERRORs (collection-time), and `-m` filtering works as designed.

Slice acceptance tests can fail with different errors locally vs in CI depending on what's missing (missing fixtures, missing engine, missing UI). All such failures are correct deliberate-red. Document the expected failure modes in the test file's docstring so a future engineer debugging "why is this red?" finds the answer is "because it's supposed to be."

All tests deterministic — no wall-clock dependence, no unfixed random seeds, no order-dependence. The TestRail reporter (`tests/reporters/testrail-reporter.ts`) auto-creates cases from Playwright titles. Test code is the source of truth — don't manually create cases in TestRail.

## Dev-environment access

The dev UI (Container App `ca-mmfp-ui-dev`) sits behind HTTP Basic Auth as an interim access gate. Credentials live in 1Password under `MMFP / dev UI basic auth`; the running container reads them from the `BASIC_AUTH_USER` / `BASIC_AUTH_PASS` env vars wired to Key Vault secrets `basic-auth-user` and `basic-auth-pass`. The middleware lives in [ui/middleware.ts](ui/middleware.ts) and is intentionally fail-closed and easily removable — it is temporary, pending the Entra SSO migration tracked in [TODO: link]. Removal steps are listed in the `AUTH-REMOVAL` block at the top of that file.

## References

- Product hypothesis — https://morae.atlassian.net/wiki/spaces/MMFP/overview
- Architecture — https://morae.atlassian.net/wiki/spaces/MMFP/pages/218530029/System+Architecture
- Architectural principles (P1–P10) — https://morae.atlassian.net/wiki/spaces/MLI/pages/146571276/Architectural+Principles
- Rubric reference — https://morae.atlassian.net/wiki/spaces/MMFP/pages/218628525/Model+Scoring+Framework+Reference
- Architecture Decision Records — Confluence, MMFP space → **Architecture Decision Records** (`MFP-ADR-NNN`)

## When this file is wrong

It will become wrong. When you notice it's out of step with reality, say so explicitly in your output. Don't silently follow stale rules. Updates to this file are themselves PRs needing human review.
