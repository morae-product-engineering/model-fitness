workspace "Morae Model Fitness Platform" "MMFP scores LLM candidates against a versioned rubric, producing scorecards for primary/fallback model decisions." {

    !identifiers hierarchical

    model {

        # --- People ---

        steward = person "Steward" "Adjusts the rubric and reviews scorecards. Represented by Wayne (ARB)."
        curator = person "Dataset Curator" "Curates golden datasets and annotates judge results. Represented by Jagdish and domain SMEs."
        viewer = person "Portfolio Viewer" "Views scorecards and cites them in production model decisions. Represented by Peter and onboarding teams."

        # --- External software systems ---

        foundry = softwareSystem "Azure AI Foundry" "Hosts and serves candidate LLMs invoked during matrix runs." "External"
        consuming = softwareSystem "Consuming Product (e.g. MLI)" "Reads MMFP scorecards and configures its own runtime model routing." "External"
        testrail = softwareSystem "TestRail" "Test case catalogue and evidence store; ARB uses it to audit run history." "External"
        langsmith = softwareSystem "LangSmith" "Agent quality observability for matrix runs. Integration planned but not yet wired." "External"
        ci = softwareSystem "GitHub Actions CI" "Runs the Playwright e2e suite and posts results to TestRail after each deployment." "External"

        # --- MMFP system ---

        mmfp = softwareSystem "MMFP" "Scores LLM candidates against a versioned rubric and produces scorecards." {

            ui = container "UI" "Steward and viewer interface for browsing scorecards and triggering runs." "Next.js / TypeScript"
            api = container "API" "Owns business logic for runs, scorecards, and rubric management." "FastAPI / Python 3.12"
            db = container "DB" "Persists runs, scorecards, rubric versions, and the audit log. SQLite for R1; planned migration to Postgres for R2+." "SQLite"

            # Internal relationships
            ui -> api "Calls" "HTTPS/JSON"
            api -> db "Reads and writes" "SQL"
        }

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
        consuming -> mmfp.api "Reads scorecards for production routing decisions" "HTTPS/JSON"
        mmfp.api -> langsmith "Posts traces for agent quality observability (planned, not yet wired)" "HTTPS"
        ci -> testrail "Posts e2e test results after each deployment" "HTTPS"

        # System-level: used in dynamic view.
        mmfp -> foundry "Invokes candidate LLMs during matrix runs" "HTTPS"
        mmfp -> testrail "Posts e2e evidence after each run (via CI)" "HTTPS"

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
        dynamic * "MatrixRun" "How a matrix run flows from trigger to evidence." {
            steward -> mmfp "Kicks off matrix run via UI"
            mmfp -> foundry "Invokes candidate LLM"
            mmfp -> testrail "Posts e2e evidence after run"
            mmfp -> steward "Returns scorecard"
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
