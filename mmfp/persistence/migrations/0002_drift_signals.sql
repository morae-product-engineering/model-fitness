-- 0002_drift_signals.sql — DriftSignal table (MFP-96).
--
-- Idempotent: every statement uses IF NOT EXISTS. Follows the same
-- conventions as 0001_initial.sql (ISO-8601 TEXT datetimes, JSON blob for
-- the evolving DriftSignal payload, created_at default for insertion order).
--
-- `status` is promoted to a column so active-signal reads are an indexed
-- scan rather than a full-payload deserialisation loop. `payload_json`
-- is the authoritative snapshot at append time; the status column is the
-- mutable state used for filtering.

CREATE TABLE IF NOT EXISTS drift_signals (
    id              TEXT PRIMARY KEY,
    product_id      TEXT NOT NULL,
    candidate_id    TEXT NOT NULL,
    tier_id         TEXT NOT NULL,
    baseline_run_id TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active',
    detected_at     TEXT NOT NULL,
    payload_json    TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_drift_signals_product_candidate_status
    ON drift_signals (product_id, candidate_id, status);
