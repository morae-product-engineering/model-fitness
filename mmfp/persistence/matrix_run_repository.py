"""SQLite repository for `MatrixRun` (MLI-258).

The matrix engine (MLI-172) emits in-memory `MatrixRun` artefacts; this
module persists them. The Scoreboard API (MLI-174) and CI seed job
(MLI-177) read through the same surface.

Design choices live in MFP-ADR-004 (Confluence: Architecture Decision Records):
  * Hand-rolled SQL migration files, idempotent CREATE IF NOT EXISTS.
  * Decimals + Any-typed payload preserved by storing each
    `MatrixRunResult` as a Pydantic JSON blob; round-trip through
    `model_dump_json()` / `model_validate_json()` is byte-exact.
  * Connections opened per public call, never pooled; foreign keys
    explicitly enabled per connection.
  * `product` lives on the row (column + index) but not on the
    `MatrixRun` model — passed explicitly at save time.

The constructor takes a `db_path: Path`; the wiring layer (CLI seed
job, API factory) decides where it points. Schema is applied lazily
on first contact so callers don't need to remember to migrate.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from mmfp.models.matrix_run import MatrixRun, MatrixRunResult

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_INITIAL_MIGRATION = _MIGRATIONS_DIR / "0001_initial.sql"


def _to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _from_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class MatrixRunRepository:
    """CRUD for `MatrixRun` against a SQLite file.

    Thread-safety: instances are not shared across threads; SQLite
    connections are opened per call inside a context manager, so
    concurrent calls from different threads each get their own
    connection. Holding the same instance across threads is fine.
    """

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._schema_applied = False

    def save(self, run: MatrixRun, *, product: str) -> None:
        """Persist a `MatrixRun` and its `results`.

        `product` lives on the row, not on the model — see ADR-0001
        for the why. Raises `sqlite3.IntegrityError` if a row with
        the same `run.id` already exists; persistence is one-shot.
        """
        if not product:
            raise ValueError("product must be a non-empty string")
        self._ensure_schema()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO matrix_runs
                    (id, schema_version, rubric_version, product,
                     started_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run.id,
                    run.schema_version,
                    run.rubric_version,
                    product,
                    _to_iso(run.started_at),
                    _to_iso(run.completed_at) if run.completed_at else None,
                ),
            )
            if run.results:
                conn.executemany(
                    """
                    INSERT INTO matrix_run_results
                        (run_id, ordinal, tier_id, candidate_id,
                         dataset_id, example_id, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            run.id,
                            ordinal,
                            r.tier_id,
                            r.candidate_id,
                            r.dataset_id,
                            r.example_id,
                            r.model_dump_json(),
                        )
                        for ordinal, r in enumerate(run.results)
                    ],
                )

    def get(self, run_id: str) -> MatrixRun | None:
        """Reconstruct a `MatrixRun` from storage. None if not found."""
        self._ensure_schema()
        with self._connect() as conn:
            run_row = conn.execute(
                """
                SELECT id, rubric_version, started_at, completed_at
                FROM matrix_runs
                WHERE id = ?
                """,
                (run_id,),
            ).fetchone()
            if run_row is None:
                return None
            payload_rows = conn.execute(
                """
                SELECT payload_json FROM matrix_run_results
                WHERE run_id = ?
                ORDER BY ordinal
                """,
                (run_id,),
            ).fetchall()

        results = [MatrixRunResult.model_validate_json(p[0]) for p in payload_rows]
        return MatrixRun(
            id=run_row[0],
            rubric_version=run_row[1],
            started_at=_from_iso(run_row[2]),
            completed_at=_from_iso(run_row[3]) if run_row[3] else None,
            results=results,
        )

    def list_for_product(self, product: str, limit: int = 20) -> list[MatrixRun]:
        """Most recent runs for a product, newest first.

        Ordered by the DB-side `created_at` (insertion time), not
        `started_at` — see ADR-0001. Empty list if there are no runs
        or the product is unknown.
        """
        if limit < 0:
            raise ValueError("limit must be non-negative")
        self._ensure_schema()
        with self._connect() as conn:
            id_rows = conn.execute(
                """
                SELECT id FROM matrix_runs
                WHERE product = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (product, limit),
            ).fetchall()

        runs: list[MatrixRun] = []
        for (run_id,) in id_rows:
            run = self.get(run_id)
            if run is not None:
                runs.append(run)
        return runs

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self) -> None:
        if self._schema_applied:
            return
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        sql = _INITIAL_MIGRATION.read_text(encoding="utf-8")
        with self._connect() as conn:
            conn.executescript(sql)
        self._schema_applied = True
