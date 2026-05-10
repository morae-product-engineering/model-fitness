# 1. SQLite persistence layer for MatrixRun / MatrixRunResult

* Status: Proposed (with MLI-258)
* Date: 2026-05-10
* Deciders: Wayne Palmer (review)
* Context: MLI-258 (this PR), MLI-172 (matrix engine, deferred persistence here), MLI-201 (audit log, will inherit pattern), Slice 6 (datasets table, will inherit pattern)

## Context

The matrix engine (MLI-172) emits an in-memory `MatrixRun` containing
`MatrixRunResult` rows. The Scoreboard API (MLI-174) and the CI seed
job (MLI-177) need that artefact persisted. Slice 5's audit log
(MLI-201) and Slice 6's datasets will reuse whatever pattern lands
here, so four decisions need committing-to: migration tooling,
`Decimal` storage shape, connection lifecycle, DB path source.

The data has two awkward shapes for SQLite:

1. `Decimal` for `normalized_score`, `cost_usd`, weights — SQLite has
   no native fixed-point type, and storing as REAL silently loses
   precision (`Decimal("33.33")` → `33.33` round-trips through float).
2. `EvaluatorScore.raw_value: Any` — payload shape varies per
   evaluator (string for exact_match, dict for json_schema, list for
   regex_match groups). Column-shredding it would require schema
   churn every time an evaluator reshapes its raw output.

## Decision

### Migration tooling — hand-rolled SQL files (R1), revisit if it hurts

Single `mmfp/persistence/migrations/0001_initial.sql`, applied via
`sqlite3.executescript()` with `CREATE TABLE IF NOT EXISTS`.
Idempotent on a fresh DB and on an already-migrated DB. No
`schema_migrations` tracking table yet — when the second migration
lands (likely MLI-201's audit-log table or a real schema change here),
that's the moment to either keep a numbered-files convention or move
to Alembic.

Rejected: Alembic for R1. Adds a real dependency, requires
`alembic.ini` plus an `env.py` and a versions directory, and earns
its keep when migrations get topologically interesting (downgrades,
branch merges). For one table-pair on SQLite at R1 it's overkill.

Trigger to revisit: the third migration, OR the first migration that
isn't a pure `CREATE`.

### Decimal storage — TEXT via Pydantic JSON serialisation

`MatrixRunResult` rows are stored as a Pydantic `model_dump_json()`
blob in a `payload_json TEXT` column. Pydantic v2 serialises
`Decimal` as a JSON string by default, and `model_validate_json()`
parses it back to `Decimal` — round-trip preserves precision and
trailing zeros (`Decimal("33.300")` round-trips byte-exact).

`MatrixRun.rubric_version`, `started_at`, `completed_at`, `id`,
`product` and `schema_version` are stored as their own columns
because we filter / order by them. `started_at` / `completed_at` are
ISO-8601 UTC strings — chronologically sortable, timezone-explicit,
and Pydantic's `UTCDatetime` validator round-trips them losslessly.

Rejected: NUMERIC affinity. SQLite's NUMERIC affinity converts to
INTEGER or REAL based on the value, which defeats the point of
storing exact decimals.

Rejected: shredding `EvaluatorScore` into many columns. Every change
to an evaluator's `raw_value` shape would force a migration; for
forensic queries we'd lift fields when we actually need them.

### Connection lifecycle — per-call context-managed

`sqlite3.connect(db_path)` per public method, inside a `with` block.
No pool, no module-level singleton. SQLite's connection cost is
negligible at MMFP's expected QPS (R1 is one run per CI invocation,
not a serving path). Foreign keys explicitly enabled per connection
(`PRAGMA foreign_keys = ON`).

Schema initialisation runs lazily on the first call per
`MatrixRunRepository` instance — `CREATE IF NOT EXISTS` makes this
safe and free.

Rejected: connection pool. No measured need; YAGNI.

### DB path source — explicit constructor argument

`MatrixRunRepository(db_path: Path)`. The repository doesn't read env
vars or config files. The wiring layer (Slice 2's CLI seed-job and
the API factory) is responsible for resolving the path. Convention
for dev: `data/mmfp.db`. Convention for CI / Container Apps: an
explicit env var (`MMFP_DB_PATH` is a good name; not committed
to here because no consumer needs it yet).

Rejected: env-var sniffing inside the repo. Hides configuration,
makes tests touchy.

### Product dimension — not on the model, explicit on save

`MatrixRun` does not carry a `product` field today (MLI-169). MLI-258
requires `list_for_product(product, limit)`, so `product` has to live
on the row. Two options:

* (A) Add `product: str` to `MatrixRun`. Touches MLI-169's model and
  every caller; broader blast radius than this PR warrants.
* (B) Pass `product` explicitly at the persistence boundary.
  `repo.save(run, product=...)`; `MatrixEngine.run(..., repository=,
  product=)` accepts it as a sibling parameter.

This PR takes (B). It keeps `MatrixRun` clean, makes the persistence
column visible at the call site, and is non-breaking. If product
later becomes a runtime concern (rubric-per-product, candidate-per-
product, status-per-product), promote it to the model in its own
ticket.

## Consequences

* New dir `mmfp/persistence/`. Subsequent persisted artefacts (audit
  log, datasets) get sibling repositories under this dir, sharing
  the migrations file convention.
* No new runtime dependency — `sqlite3` is stdlib.
* JSON-blob storage for `MatrixRunResult` payload means ad-hoc
  inspection (`sqlite3 data/mmfp.db "SELECT ..."`) needs JSON
  functions (`json_extract`) to drill into score fields. Acceptable
  for R1; promote a column when a query needs it.
* The choice cascades: MLI-201's audit log, when it lands, should
  follow the same conventions (TEXT for ISO datetimes, JSON-blob for
  evolving payloads, explicit constructor for db path).
