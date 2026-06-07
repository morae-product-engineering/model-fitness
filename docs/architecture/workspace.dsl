workspace "Morae Model Fitness Platform" "MMFP scores LLM candidates against a versioned rubric, producing scorecards for primary/fallback model decisions." {

    !identifiers hierarchical

    model {

        # --- People ---

        steward = person "Steward" "Adjusts the rubric and reviews scorecards. Represented by Wayne (ARB)."
        curator = person "Dataset Curator" "Curates golden datasets and annotates judge results. Represented by Jagdish and domain SMEs."
        viewer = person "Portfolio Viewer" "Views scorecards and cites them in production model decisions. Represented by Peter and onboarding teams."

        # --- External software systems ---

        foundry = softwareSystem "Azure AI Foundry" "Hosts and serves candidate LLMs invoked during matrix runs." "External"
        azureml = softwareSystem "Azure ML" "Hosts custom-model deployments invoked via the binding plugin's custom-model path." "External"
        consuming = softwareSystem "Consuming Product (e.g. MLI)" "Reads MMFP scorecards and configures its own runtime model routing." "External"
        testrail = softwareSystem "TestRail" "Test case catalogue and evidence store; ARB uses it to audit run history." "External"
        langsmith = softwareSystem "LangSmith" "Stores raw evaluator outputs and provides agent-quality observability for matrix runs." "External"
        appinsights = softwareSystem "Application Insights" "Platform telemetry sink for the MMFP containers (traces, metrics, alerts)." "External"
        slack = softwareSystem "Slack" "Receives operational alerts raised from Application Insights." "External"
        ci = softwareSystem "GitHub Actions CI" "Runs the Playwright e2e suite and posts results to TestRail after each deployment." "External"

        # --- MMFP system ---

        mmfp = softwareSystem "MMFP" "Scores LLM candidates against a versioned rubric and produces scorecards." {

            ui = container "UI" "Steward and viewer interface for browsing scorecards and triggering runs." "Next.js / TypeScript"
            cli = container "CLI" "Headless client for triggering runs and reading scorecards; predates the UI (headless-before-UI)." "Python"
            api = container "API" "Owns business logic for runs, scorecards, and rubric management." "FastAPI / Python 3.12"
            db = container "DB" "Persists matrix runs and per-result scores. SQLite for R1; planned migration to Postgres." "SQLite"

            # Internal relationships
            ui -> api "Calls" "HTTPS/JSON"
            cli -> api "Calls" "HTTPS/JSON"
            api -> db "Reads and writes" "SQL"
        }

        # NOTE: the DB is intentionally narrow — matrix runs and per-result
        # scores only. The rubric and golden datasets are versioned in Git, and
        # raw evaluator outputs live in LangSmith; neither is stored in the DB.

        # --- Person -> MMFP relationships ---
        # Container-level: used in Container view.
        steward -> mmfp.ui "Adjusts rubric and reviews scorecards via"
        curator -> mmfp.ui "Curates datasets and annotates judge results via"
        viewer -> mmfp.ui "Views scorecards via"

        # System-level: required for the dynamic view, which can only reference
        # people and software systems (not containers).
        steward -> mmfp "Kicks off matrix runs and reviews scorecards"
        curator -> mmfp "Curates datasets and annotates judge results"
        viewer -> mmfp "Views scorecards"

        # --- MMFP -> external relationships ---
        # Container-level: used in Container view.
        mmfp.api -> foundry "Invokes candidate LLMs during matrix runs" "HTTPS"
        mmfp.api -> azureml "Invokes custom models via the binding plugin's custom-model path" "HTTPS"
        consuming -> mmfp.api "Reads scorecards for production routing decisions" "HTTPS/JSON"
        consuming -> mmfp.api "PR gate: CI checks routing config against the approved portfolio" "HTTPS/JSON"
        mmfp.api -> langsmith "Posts raw evaluator outputs and traces for agent-quality observability" "HTTPS"
        mmfp.api -> appinsights "Emits platform telemetry (traces, metrics)" "HTTPS"
        appinsights -> slack "Raises operational alerts to" "Webhook"
        ci -> testrail "Posts e2e test results after each deployment" "HTTPS"

        # System-level: used in dynamic view.
        mmfp -> testrail "Posts e2e evidence after each run (via CI)" "HTTPS"

        # --- Deployment (Azure) ---
        # Backs the deployment view. Infra-only nodes (ACR, Key Vault, GitHub
        # Actions OIDC) are infrastructureNodes. App Insights is a software
        # system instance so the api -> appinsights model edge is replicated as
        # a deployment edge automatically. Container images run in Azure
        # Container Apps; CI/CD authenticates to Azure via OIDC federation.
        deploymentEnvironment "Azure" {
            gha = deploymentNode "GitHub Actions" "CI/CD on GitHub-hosted runners" "GitHub Actions" {
                oidc = infrastructureNode "OIDC Federated Identity" "Secret-less federated auth to Azure; no long-lived credentials."
            }
            azure = deploymentNode "Azure" "Morae Azure subscription" "Azure" {
                acr = infrastructureNode "Azure Container Registry" "Stores built images; pulled by Container Apps."
                kv = infrastructureNode "Azure Key Vault" "Secrets and connection strings referenced by the apps."
                aca = deploymentNode "Azure Container Apps" "ca-mmfp-* container apps" "Azure Container Apps" {
                    containerInstance mmfp.ui
                    containerInstance mmfp.cli
                    containerInstance mmfp.api
                }
                softwareSystemInstance appinsights

                # Deployment-only wiring not present in the logical model.
                aca -> acr "Pulls images from" "HTTPS"
                aca -> kv "Reads secrets from" "HTTPS"
            }
            gha.oidc -> azure.aca "Builds, authenticates, and deploys to" "OIDC / HTTPS"
        }

    }

    views {

        systemContext mmfp "SystemContext" "MMFP in its environment." {
            include *
            autoLayout lr
        }

        container mmfp "Containers" "MMFP internals and external dependencies." {
            include *
            autoLayout lr
        }

        # MatrixRun: system-level flow from Steward triggering a run through to scorecard delivery.
        # Container-level detail (UI->API->DB) lives in the Container view, not here.
        # dynamic * scopes to software systems and people only — no containers allowed.
        # Step descriptions are omitted — Structurizr infers them from the model relationship
        # descriptions. Adding inline descriptions here would redefine the relationship,
        # causing a "relationship already exists" parse error.
        dynamic * "MatrixRun" "How a matrix run flows from trigger to evidence." {
            steward -> mmfp
            mmfp -> foundry
            mmfp -> testrail
            autolayout lr
        }

        # Deployment view: MMFP on Azure Container Apps, with ACR, Key Vault,
        # App Insights, and the GitHub Actions OIDC deploy path. View key
        # "Deployment" -> rendered file structurizr-Deployment.svg, which the
        # Confluence sync publishes.
        deployment mmfp "Azure" "Deployment" "MMFP deployed to Azure Container Apps." {
            include *
            autoLayout lr
        }

        styles {
            element "External" {
                background #999999
                color #ffffff
            }
            element "Person" {
                shape Person
            }
        }

    }

}
 # adds a trailing blank line, harmless
