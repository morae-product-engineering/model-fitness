-- 0001_initial.sql — MatrixRun / MatrixRunResult tables (MLI-258).
--
-- Idempotent: every statement uses IF NOT EXISTS so first-run and
-- already-migrated DBs converge to the same state. See
-- ADRs/0001-sqlite-persistence.md for the shape rationale (TEXT for
-- ISO-8601 datetimes, JSON blob for evolving MatrixRunResult payload).

CREATE TABLE IF NOT EXISTS matrix_runs (
    id              TEXT PRIMARY KEY,
    schema_version  TEXT NOT NULL,
    rubric_version  TEXT NOT NULL,
    product         TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    completed_at    TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_matrix_runs_product_created
    ON matrix_runs (product, created_at DESC);

CREATE TABLE IF NOT EXISTS matrix_run_results (
    run_id        TEXT NOT NULL,
    ordinal       INTEGER NOT NULL,
    tier_id       TEXT NOT NULL,
    candidate_id  TEXT NOT NULL,
    dataset_id    TEXT NOT NULL,
    example_id    TEXT NOT NULL,
    payload_json  TEXT NOT NULL,
    PRIMARY KEY (run_id, ordinal),
    FOREIGN KEY (run_id) REFERENCES matrix_runs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_matrix_run_results_run
    ON matrix_run_results (run_id);
