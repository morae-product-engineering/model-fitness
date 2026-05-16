# Golden databases for `query_correctness`

Each `.sql` file builds a hermetic SQLite database from text — schema
plus a small fixed dataset. The `query_correctness` evaluator loads the
script into `:memory:` per evaluation, executes the candidate query
under a SELECT-only authorizer, and compares result rows against the
dataset's `expected.rows`.

Text scripts (not committed `.sqlite` binaries) so diffs are reviewable
and the dataset is auditable from a normal code review. Per-evaluation
load cost is sub-millisecond at this scale; no caching needed.

Add a new golden DB by writing a fresh `.sql` file alongside this README
and referencing its path from the rubric YAML's `evaluator_config.golden_db_path`.

Dialect is SQLite. Candidate SQL written for ANSI-only or Postgres-only
syntax may fail on this harness even when "correct" against a different
target. This is a load-bearing constraint of the v0.1 deterministic
harness — see the dialect-selection architectural-input on MLI-267.
