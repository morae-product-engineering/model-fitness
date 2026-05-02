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

        steward -> mmfp.ui "Adjusts rubric and reviews scorecards via"
        curator -> mmfp.ui "Curates datasets and annotates judge results via"
        viewer -> mmfp.ui "Views scorecards via"

        # --- MMFP -> external relationships ---

        mmfp.api -> foundry "Invokes candidate LLMs during matrix runs" "HTTPS"
        consuming -> mmfp.api "Reads scorecards for production routing decisions" "HTTPS/JSON"
        mmfp.api -> langsmith "Posts traces for agent quality observability (planned, not yet wired)" "HTTPS"
        ci -> testrail "Posts e2e test results after each deployment" "HTTPS"

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

        # MatrixRun: sequence from Steward kicking off a run through to TestRail evidence posting.
        # CI->TestRail step is included because it is the observable close of the run lifecycle.
        dynamic * "MatrixRun" "How a matrix run flows from trigger to evidence." {
            steward -> mmfp.ui "Kicks off matrix run"
            mmfp.ui -> mmfp.api "POSTs run request"
            mmfp.api -> foundry "Invokes candidate LLM"
            mmfp.api -> mmfp.db "Persists run result"
            ci -> testrail "Posts e2e evidence to TestRail"
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
