"""SQLite repository for judge-queue samples (MFP-75).

Samples are inserted by the matrix engine (MFP-77) when an LLM-judge evaluator
runs. This module handles read and mark operations — the curator reviews each
sample and agrees or disagrees with the judge's decision.

Mirrors `MatrixRunRepository`: lazy `_ensure_schema()`, per-call connections,
`MMFP_DB_PATH` env var resolved by the wiring layer, not by this class.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_MIGRATION = _MIGRATIONS_DIR / "0002_judge_queue.sql"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class JudgeQueueRepository:
    """CRUD for `judge_queue_samples` against a SQLite file.

    Thread-safety: per-call connections; holding the same instance across
    threads is safe (same guarantee as `MatrixRunRepository`).
    """

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._schema_applied = False

    @contextmanager
    def _connect(self):
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        if self._schema_applied:
            return
        sql = _MIGRATION.read_text(encoding="utf-8")
        with self._connect() as conn:
            conn.executescript(sql)
        self._schema_applied = True

    def list_samples(
        self,
        product: str,
        *,
        status: str | None = None,
    ) -> list[dict]:
        """Return all samples for `product`, optionally filtered by status.

        `status='pending'`  → decision = 'pending'
        `status='reviewed'` → decision IN ('agree', 'disagree')
        """
        self._ensure_schema()
        if status == "pending":
            where = "product = ? AND decision = 'pending'"
            params = (product,)
        elif status == "reviewed":
            where = "product = ? AND decision IN ('agree', 'disagree')"
            params = (product,)
        else:
            where = "product = ?"
            params = (product,)

        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM judge_queue_samples WHERE {where} ORDER BY created_at",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def get_sample(self, sample_id: str, product: str) -> dict | None:
        """Return the sample row, or ``None`` if not found."""
        self._ensure_schema()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM judge_queue_samples WHERE id = ? AND product = ?",
                (sample_id, product),
            ).fetchone()
        return dict(row) if row else None

    def mark(
        self,
        sample_id: str,
        product: str,
        decision: str,
        note: str | None = None,
    ) -> dict:
        """Set decision + note + decided_at on a sample.

        Raises ``KeyError`` if no matching sample exists — router converts this to 404.
        """
        self._ensure_schema()
        decided_at = _now_iso()
        with self._connect() as conn:
            result = conn.execute(
                """
                UPDATE judge_queue_samples
                   SET decision = ?, note = ?, decided_at = ?
                 WHERE id = ? AND product = ?
                """,
                (decision, note, decided_at, sample_id, product),
            )
            if result.rowcount == 0:
                raise KeyError(f"sample {sample_id!r} not found for product {product!r}")
            row = conn.execute(
                "SELECT * FROM judge_queue_samples WHERE id = ? AND product = ?",
                (sample_id, product),
            ).fetchone()
        return dict(row)
