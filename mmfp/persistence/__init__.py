"""Persistence layer for MMFP artefacts (MLI-258).

R1 stack is SQLite via stdlib `sqlite3`; the repository pattern here is
the precedent every other persisted model (audit log MLI-201, datasets
in Slice 6) is expected to follow. See ADRs/0001-sqlite-persistence.md
for the design rationale.
"""

from mmfp.persistence.matrix_run_repository import MatrixRunRepository

__all__ = ["MatrixRunRepository"]
