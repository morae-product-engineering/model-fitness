"""SQLite repository for DriftSignal (MFP-96).

Append-only writes; reads filter by status; survives a process restart
(the same durability requirement as the matrix-run artefact — both rely
on SQLite persisting to the local filesystem).

DECISION for Wayne (MFP-96): SQLite matches the matrix-run pattern and
reuses the migration seam with zero new abstractions. The trade-off vs the
audit-log / candidate-status blob approach: the deployed Container App
filesystem is ephemeral, so signals stored here will not survive a revision
restart. Mirroring the candidate-status decision, swapping to a blob backend
is a contained change behind this module's interface if persistence across
restarts is required before the slice ships.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from mmfp.models.drift import DriftSignal

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_DRIFT_MIGRATION = _MIGRATIONS_DIR / "0002_drift_signals.sql"


class DriftSignalStore:
    """Append-only SQLite store for DriftSignal artefacts.

    Thread-safety: connections are opened per call; concurrent calls from
    different threads each get their own connection. Holding one instance
    across threads is fine.
    """

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._schema_applied = False

    def append(self, signal: DriftSignal) -> str:
        """Persist a new DriftSignal; returns the store-assigned signal ID.

        The returned ID is required to acknowledge this signal later.
        Append is unconditional — callers are responsible for deduplication
        before calling (the sensor layer, not the store, owns that policy).
        """
        self._ensure_schema()
        signal_id = uuid.uuid4().hex
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO drift_signals
                    (id, product_id, candidate_id, tier_id,
                     baseline_run_id, status, detected_at, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_id,
                    signal.product_id,
                    signal.candidate_id,
                    signal.tier_id,
                    signal.baseline_run_id,
                    signal.status,
                    signal.detected_at.isoformat(),
                    signal.model_dump_json(),
                ),
            )
        return signal_id

    def list_active(
        self,
        *,
        product_id: str,
        candidate_id: str,
    ) -> list[DriftSignal]:
        """Active signals for a (product, candidate) pair, newest first.

        Returns an empty list when no active signals exist — not an error.
        """
        self._ensure_schema()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM drift_signals
                WHERE product_id = ? AND candidate_id = ? AND status = 'active'
                ORDER BY detected_at DESC, created_at DESC
                """,
                (product_id, candidate_id),
            ).fetchall()
        return [DriftSignal.model_validate_json(row[0]) for row in rows]

    def list_active_for_product(
        self,
        *,
        product_id: str,
        candidate_id: str | None = None,
    ) -> list[tuple[str, DriftSignal]]:
        """Active signals for a product, paired with their store IDs, newest first.

        Returns ``(signal_id, DriftSignal)`` pairs so callers can acknowledge
        by ID. Returns an empty list when no active signals exist — not an error.
        Optional ``candidate_id`` narrows to a single candidate.
        """
        self._ensure_schema()
        with self._connect() as conn:
            if candidate_id is not None:
                rows = conn.execute(
                    """
                    SELECT id, payload_json FROM drift_signals
                    WHERE product_id = ? AND candidate_id = ? AND status = 'active'
                    ORDER BY detected_at DESC, created_at DESC
                    """,
                    (product_id, candidate_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, payload_json FROM drift_signals
                    WHERE product_id = ? AND status = 'active'
                    ORDER BY detected_at DESC, created_at DESC
                    """,
                    (product_id,),
                ).fetchall()
        return [(row[0], DriftSignal.model_validate_json(row[1])) for row in rows]


    def acknowledge(self, signal_id: str) -> None:
        """Mark a signal as acknowledged; it will no longer appear in list_active.

        No-op when the signal_id does not exist or is already acknowledged.
        """
        self._ensure_schema()
        with self._connect() as conn:
            conn.execute(
                "UPDATE drift_signals SET status = 'acknowledged' WHERE id = ?",
                (signal_id,),
            )

    # -- internals ----------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self) -> None:
        if self._schema_applied:
            return
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        sql = _DRIFT_MIGRATION.read_text(encoding="utf-8")
        with self._connect() as conn:
            conn.executescript(sql)
        self._schema_applied = True
