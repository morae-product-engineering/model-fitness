# MMFP Architecture

`workspace.dsl` is a [Structurizr DSL](https://docs.structurizr.com/dsl) file that describes the Morae Model Fitness Platform architecture as code — three people (Steward, Dataset Curator, Portfolio Viewer), one system (MMFP) with three containers (UI, API, DB), five external systems (Azure AI Foundry, Consuming Product, TestRail, LangSmith, GitHub Actions CI), and three views (system context, container, and a MatrixRun dynamic sequence).

`workspace.dsl` is the source of truth. Everything else under `docs/architecture/` is generated.

## Rendered diagrams

Every change to `workspace.dsl` on `main` is validated, rendered to SVG and PNG, committed back under `docs/architecture/exports/`, and published to GitHub Pages:

- https://morae-product-engineering.github.io/model-fitness/

The pipeline lives in `.github/workflows/docs-architecture.yml`.

## Local editing

Render and explore views in your browser with Structurizr Lite:

```
docker run -it --rm -p 8080:8080 -v $(pwd)/docs/architecture:/usr/local/structurizr structurizr/lite
```

Then open `http://localhost:8080`.

## Pre-merge preview

When a PR changes `workspace.dsl`, the workflow validates the DSL and uploads the rendered exports as a workflow artifact named `architecture-exports`. Download it from the PR's Checks tab to preview diagrams before merging.

## Confluence sync

After Phase 1 commits new SVGs to `main`, a second workflow (`.github/workflows/confluence-sync.yml`) pushes them to the MFP Architecture page on Confluence as page attachments:

- https://morae.atlassian.net/wiki/spaces/MLI/pages/218530029

What gets pushed: the three SVG views — `structurizr-SystemContext.svg`, `structurizr-Containers.svg`, `structurizr-MatrixRun.svg` — as page attachments. The page body embeds them via `<ac:image>` macros referencing those filenames, so refreshing the attachments refreshes the rendered diagrams without touching prose.

Trigger chain: `workspace.dsl` change → Phase 1 renders + commits SVGs to `main` → Phase 1 fires a `repository_dispatch` event (`confluence-sync-needed`) → Phase 2 runs and updates the page. The bridge is explicit because Phase 1's auto-commit uses `[skip ci]`, which suppresses the natural path-filtered push trigger on the same commit.

Body-edit-once contract: the first sync run rewrites the page's "System context" section to embed the three diagrams and then sets a Confluence content property (`architecture_diagrams_managed`) on the page. Every run after that sees the property and refreshes attachments only — humans editing prose elsewhere on the page are not overwritten. The marker lives on the page metadata rather than in the body itself: in-body HTML comments do not survive Confluence's storage normalisation, but content properties are designed for CI metadata and are invisible to editors. To restore the embed structure if it has been deleted manually, delete the property via the REST API (`DELETE /wiki/rest/api/content/{pageId}/property/architecture_diagrams_managed`) and re-run the workflow.

Manual re-sync: Actions tab → "Sync Architecture to Confluence" → Run workflow. Useful after rotating the API token or after manually editing the page in a way that needs re-syncing the diagrams.

Required configuration on the repo (one-time, by Wayne):
- Secret: `CONFLUENCE_API_TOKEN` — token from https://id.atlassian.com/manage-profile/security/api-tokens, owned by a user with edit access to the page.
- Variable: `CONFLUENCE_USER_EMAIL` — the Atlassian email tied to that token.
- Variable: `CONFLUENCE_BASE_URL` — `https://morae.atlassian.net`.
- Variable: `CONFLUENCE_PAGE_ID` — `218530029`.

Trade-off: attachment filenames are tied to view names in `workspace.dsl`. Renaming a view in the DSL leaves the old attachment orphaned on the page — clean it up by hand if needed.

## Slice close-out

Future slices should update `workspace.dsl` as part of their close-out — adding containers, relationships, or views as the platform grows. CI takes care of re-rendering and publishing.
