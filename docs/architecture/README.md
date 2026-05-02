# MMFP Architecture

`workspace.dsl` is a [Structurizr DSL](https://docs.structurizr.com/dsl) file that describes the Morae Model Fitness Platform architecture as code — three people (Steward, Dataset Curator, Portfolio Viewer), one system (MMFP) with three containers (UI, API, DB), five external systems (Azure AI Foundry, Consuming Product, TestRail, LangSmith, GitHub Actions CI), and three views (system context, container, and a MatrixRun dynamic sequence). Render it locally with Structurizr Lite:

```
docker run -it --rm -p 8080:8080 -v $(pwd)/docs/architecture:/usr/local/structurizr structurizr/lite
```

Then open `http://localhost:8080` in your browser.

Future slices should update `workspace.dsl` as part of their close-out — adding containers, relationships, or views as the platform grows.
