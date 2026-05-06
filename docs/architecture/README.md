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

## Slice close-out

Future slices should update `workspace.dsl` as part of their close-out — adding containers, relationships, or views as the platform grows. CI takes care of re-rendering and publishing.
