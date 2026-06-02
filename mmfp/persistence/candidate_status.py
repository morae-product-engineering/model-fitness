"""Per-tier candidate status store — mutable current-state record (MLI-202).

Each record is keyed ``(product, tier_id, candidate_deployment)`` and holds the
current promotion/rejection status for that combination. This is the write path
moved OFF ephemeral ``candidates.yaml`` to durable storage, per the MLI-199
architectural-reality comment #2 requirement.

Key design decisions baked in here:

  * **Mutable current-state (overwrite=True), NOT append-only.** This store is
    the single source of truth for *what the status is right now*. The
    per-tier history (every action ever taken, why, by whom) is the concern of
    the append-only audit log (``audit_log.py`` / MLI-201). A consumer who
    needs "what is gpt-4-1-mini's status in tier_2 today" reads this store; a
    consumer who needs the audit trail reads the other.

  * **Blob name:** ``<product>/candidate-status/<tier_id>/<candidate>.json``.
    One blob per (product, tier_id, candidate) triple — a direct lookup with no
    prefix-scan needed, because the dominant access pattern for this store is
    "get the current status for exactly this key", not time-ordered enumeration.

  * **Optimistic concurrency via ``expected_version``.**  Each record carries a
    monotonic ``version`` int. Writers supply ``expected_version``; the store
    reads the stored record, checks stored_version == expected_version, then
    writes version = expected_version + 1 and a new ``updated_at``.
    ``CandidateStatusVersionConflict`` is raised on a mismatch. This is the
    same last-write-loses handshake MLI-365 established for rubric writes.

  * **In-process ``threading.Lock`` per product** serialises the read-check-
    write critical section. Correct within a single replica only — the deployed
    API must stay pinned ``minReplicas=maxReplicas=1``. Cross-replica safety
    via blob ETag / If-Match is the documented fast-follow. ASSUMES the dev
    Container App is pinned minReplicas=maxReplicas=1.

  * **Durability grounds:** status overrides survive a Container App revision
    restart. The deployed filesystem is ephemeral; a status written to disk on
    the local filesystem would vanish on restart, forcing a re-promote after
    every deploy. This is a data-integrity requirement, not a compliance framing
    (the SOC-2 framing was dropped in the MLI-199 2026-06-02 input — the audit
    log is the SOC-2 artefact; this store just needs to not lose writes).

Backend selection (``get_candidate_status_store``): blob when both
``MMFP_STATUS_BLOB_ACCOUNT_URL`` and ``MMFP_STATUS_BLOB_CONTAINER`` are set;
disk otherwise — EXCEPT that a missing durable config in the deployed env
(detected via ``CONTAINER_APP_NAME``) is a hard error, never a silent fall-back
to ephemeral disk (the MLI-365 footgun).

The status store can REUSE the MLI-201 audit container (distinct
``candidate-status/`` prefix vs ``promotion-audit/``), so no new Azure
container or MI grant is needed — just 2 env vars pointed at the same
account/container.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from typing import Callable

from pydantic import BaseModel, Field

from mmfp.models._common import MMFP_MODEL_CONFIG, UTCDatetime
from mmfp.models.candidate import CandidateStatus, TierId
from mmfp.persistence.blob_seam import AzureBlobSeam, BlobSeam, DiskBlobSeam

logger = logging.getLogger(__name__)

__all__ = [
    "CandidateStatusConfigError",
    "CandidateStatusRecord",
    "CandidateStatusStore",
    "CandidateStatusVersionConflict",
    "get_candidate_status_store",
]

# Env vars selecting + configuring the status container.
# These can point at the same account/container as the audit log (distinct
# ``candidate-status/`` prefix keeps them apart) — no new container or MI grant
# is strictly needed.
ACCOUNT_URL_ENV = "MMFP_STATUS_BLOB_ACCOUNT_URL"
CONTAINER_ENV = "MMFP_STATUS_BLOB_CONTAINER"
LOCAL_DIR_ENV = "MMFP_STATUS_LOCAL_DIR"
# Azure Container Apps sets this in every revision; its presence means "deployed".
DEPLOY_MARKER_ENV = "CONTAINER_APP_NAME"
_DEFAULT_LOCAL_DIR = "data/candidate-status"

_STATUS_PREFIX = "candidate-status"


class CandidateStatusConfigError(RuntimeError):
    """Durable status storage is required (deployed env) but unconfigured."""


class CandidateStatusVersionConflict(RuntimeError):
    """Raised when ``expected_version`` doesn't match the stored version.

    Args:
        expected: the version the caller expected.
        actual: the version found in the store (or 0 when no record exists).
    """

    def __init__(self, *, expected: int, actual: int) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"candidate status version conflict: expected {expected}, found {actual}"
        )


class CandidateStatusRecord(BaseModel):
    """Current promotion/rejection state for one (product, tier_id, candidate) triple.

    ``version`` is the optimistic-concurrency token: readers hand it back on
    the next write as ``expected_version``. Starts at 1 on first write (0 is the
    sentinel "no record stored yet").

    ``rationale`` is NOT stored here — rationale's system of record is the audit
    log (MLI-199 decision B). A denormalised latest-rationale cache on this record
    is explicitly deferred to MLI-205.
    """

    model_config = MMFP_MODEL_CONFIG

    product: str
    tier_id: TierId
    candidate_deployment: str = Field(min_length=1)
    status: CandidateStatus
    version: int = Field(ge=1, description="Optimistic-concurrency token; 1 on first write")
    updated_at: UTCDatetime


def _blob_name(product: str, tier_id: TierId, candidate: str) -> str:
    """One blob per (product, tier_id, candidate) — direct lookup, no prefix scan."""
    return f"{product}/{_STATUS_PREFIX}/{tier_id}/{candidate}.json"


class CandidateStatusStore:
    """Mutable current-state store for per-tier candidate status.

    ``get`` returns ``None`` when no override has been written (caller falls
    back to the seed status from candidates.yaml). ``set`` writes version 1 on
    the first call; subsequent calls expect the current version and increment.

    Thread-safety: a per-product in-process lock serialises the read-check-write
    critical section. Correct within a single replica only; cross-replica safety
    via blob ETag / If-Match is the named fast-follow (see module docstring).
    ASSUMES the dev Container App is pinned minReplicas=maxReplicas=1.
    """

    def __init__(
        self, seam: BlobSeam, *, clock: Callable[[], datetime] | None = None
    ) -> None:
        self._seam = seam
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def get(
        self, *, product: str, tier_id: TierId, candidate: str
    ) -> CandidateStatusRecord | None:
        """Return the stored status record, or None when no override exists.

        None is the correct sentinel for "candidate is still at its seed status
        from candidates.yaml" — callers fall back to ``candidate.status`` when
        this returns None.
        """
        data = self._seam.read(_blob_name(product, tier_id, candidate))
        if data is None:
            return None
        return CandidateStatusRecord.model_validate_json(data)

    def set(
        self,
        *,
        product: str,
        tier_id: TierId,
        candidate: str,
        status: CandidateStatus,
        expected_version: int,
    ) -> CandidateStatusRecord:
        """Write the new status, guarded by an optimistic-concurrency check.

        Reads the stored record inside the per-product lock, validates
        ``stored_version == expected_version`` (0 when no record exists), then
        writes a new record with ``version = expected_version + 1``.

        Raises:
            CandidateStatusVersionConflict: if the stored version differs from
                ``expected_version``. The caller (the promote/reject endpoint)
                should surface this as a 409 — the audit entry for the change
                has already been committed as recorded intent.
        """
        with self._lock_for(product):
            existing = self.get(product=product, tier_id=tier_id, candidate=candidate)
            stored_version = existing.version if existing else 0
            if stored_version != expected_version:
                raise CandidateStatusVersionConflict(
                    expected=expected_version, actual=stored_version
                )
            new_record = CandidateStatusRecord(
                product=product,
                tier_id=tier_id,
                candidate_deployment=candidate,
                status=status,
                version=expected_version + 1,
                updated_at=self._clock(),
            )
            self._seam.write(
                _blob_name(product, tier_id, candidate),
                new_record.model_dump_json().encode("utf-8"),
                overwrite=True,  # current-state store: always overwrites the prior record
            )
            logger.info(
                "candidate_status.set",
                extra={
                    "product": product,
                    "tier_id": tier_id,
                    "candidate": candidate,
                    "status": status.value if hasattr(status, "value") else str(status),
                    "version": new_record.version,
                },
            )
            return new_record

    # -- internals ----------------------------------------------------------

    def _lock_for(self, product: str) -> threading.Lock:
        with self._locks_guard:
            lock = self._locks.get(product)
            if lock is None:
                lock = threading.Lock()
                self._locks[product] = lock
            return lock


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


def get_candidate_status_store(
    *, clock: Callable[[], datetime] | None = None
) -> CandidateStatusStore:
    """Pick the backend from the environment: blob when configured, disk
    otherwise — but fail loud rather than silently use ephemeral disk when the
    durable config is absent in the deployed environment (the MLI-365 footgun).

    The status store can REUSE the audit container (``MMFP_STATUS_BLOB_ACCOUNT_URL``
    and ``MMFP_STATUS_BLOB_CONTAINER`` can point at the same account/container as
    ``MMFP_AUDIT_BLOB_ACCOUNT_URL`` / ``MMFP_AUDIT_BLOB_CONTAINER``). The
    ``candidate-status/`` prefix keeps the two namespaces apart.
    """
    account_url = os.environ.get(ACCOUNT_URL_ENV, "").strip()
    container = os.environ.get(CONTAINER_ENV, "").strip()
    if account_url and container:
        return CandidateStatusStore(
            AzureBlobSeam(account_url=account_url, container=container), clock=clock
        )
    if os.environ.get(DEPLOY_MARKER_ENV):
        raise CandidateStatusConfigError(
            "Durable candidate-status storage is not configured in the deployed "
            f"environment: set {ACCOUNT_URL_ENV} and {CONTAINER_ENV} on the "
            "Container App. Refusing to fall back to ephemeral local disk — a "
            "status override that vanishes on revision restart would silently "
            "revert a promotion decision."
        )
    local_dir = os.environ.get(LOCAL_DIR_ENV, _DEFAULT_LOCAL_DIR)
    return CandidateStatusStore(DiskBlobSeam(local_dir), clock=clock)
