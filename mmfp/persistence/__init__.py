"""Persistence layer for MMFP artefacts (MLI-258).

R1 stack is SQLite via stdlib `sqlite3` for the matrix-run artefact; the
repository pattern here is the precedent every other persisted model follows.

The Slice-5 audit log (MLI-201) reuses the *module shape* but a durable Azure
Blob backing store rather than SQLite — the deployed Container App filesystem is
ephemeral, so the audit trail must survive a revision restart (the MLI-365
lesson) to stay complete and tamper-evident. It lives in `audit_log.py` on the
low-level seam in `blob_seam.py`.
See MFP-ADR-004 (Confluence: Architecture Decision Records) for the
matrix-run design rationale.
"""

from mmfp.persistence.audit_log import (
    AuditLogConfigError,
    AuditLogRepository,
    get_audit_log_repository,
)
from mmfp.persistence.candidate_status import (
    CandidateStatusConfigError,
    CandidateStatusStore,
    CandidateStatusVersionConflict,
    get_candidate_status_store,
)
from mmfp.persistence.matrix_run_repository import MatrixRunRepository

__all__ = [
    "AuditLogConfigError",
    "AuditLogRepository",
    "CandidateStatusConfigError",
    "CandidateStatusStore",
    "CandidateStatusVersionConflict",
    "MatrixRunRepository",
    "get_audit_log_repository",
    "get_candidate_status_store",
]
