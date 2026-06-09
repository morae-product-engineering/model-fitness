-- 0002_judge_queue.sql — judge_queue_samples table (MFP-75).
--
-- Idempotent: CREATE IF NOT EXISTS converges first-run and already-migrated DBs.
-- decision column encodes curation state: 'pending' | 'agree' | 'disagree'.
-- judge_score / judge_reasoning are written when the LLM judge evaluator runs
-- (MFP-77); the mark endpoint updates decision/note/decided_at only.

CREATE TABLE IF NOT EXISTS judge_queue_samples (
    id              TEXT PRIMARY KEY,
    product         TEXT NOT NULL,
    tier_id         TEXT NOT NULL,
    example_id      TEXT NOT NULL,
    candidate_id    TEXT NOT NULL,
    model_output    TEXT NOT NULL DEFAULT '',
    judge_score     REAL,
    judge_reasoning TEXT,
    decision        TEXT NOT NULL DEFAULT 'pending',
    note            TEXT,
    decided_at      TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_jqs_product_decision
    ON judge_queue_samples (product, decision);
