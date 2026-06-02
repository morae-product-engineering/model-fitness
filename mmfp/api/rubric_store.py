"""Durable rubric persistence — read + write backing store (MLI-365).

Replaces the git-commit-as-audit-log design (MLI-273) that was incompatible
with the deployed environment: the API runs in an ephemeral, non-git Azure
Container App, so the original save path 500'd on `git rev-parse` and, even
where git worked locally, the write landed on a non-durable filesystem and was
lost on revision restart.

This module is the single seam through which the rubric-editing loop (read,
preview "current", write) reaches durable storage. Two backends:

  * ``DiskRubricStore`` — reads/writes ``${MMFP_PRODUCTS_DIR}/<product>/rubric.yaml``
    and writes audit records next to it. Used for local dev and unit tests;
    keeps every reader consistent on one filesystem with no Azure dependency.

  * ``BlobRubricStore`` — reads/writes the rubric YAML and append-only audit
    records in Azure Blob Storage via the container's managed identity
    (``DefaultAzureCredential``). Used in the deployed environment. The rubric
    blob is authoritative; on a cold container (blob absent) it bootstraps from
    the ``rubric.yaml`` shipped in the image, then the first write makes the
    blob the source of truth. This is what makes a saved rubric survive a
    revision restart.

Backend selection (``get_rubric_store``): blob when both
``MMFP_RUBRIC_BLOB_ACCOUNT_URL`` and ``MMFP_RUBRIC_BLOB_CONTAINER`` are set,
disk otherwise.

Audit record (the thing git history used to give for free): one immutable JSON
blob per save under ``<product>/rubric/audit/<timestamp>-<version>.json``,
holding the version delta, note, steward identity, and timestamp. See
``AuditRecord``.

Concurrency note (MLI-194 / MLI-365): the per-product in-process lock in
``rubric_write`` still serialises writes within a replica, correct only while
the dev Container App is pinned ``minReplicas=maxReplicas=1``. Cross-replica
optimistic concurrency via blob ETag / If-Match is a documented FAST-FOLLOW,
not implemented here.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Protocol

import yaml
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Env vars selecting + configuring the blob backend. Account URL + container
# both required to switch on blob persistence; absent → disk backend.
BLOB_ACCOUNT_URL_ENV = "MMFP_RUBRIC_BLOB_ACCOUNT_URL"
BLOB_CONTAINER_ENV = "MMFP_RUBRIC_BLOB_CONTAINER"


class RubricNotFound(Exception):
    """Raised by a store when a product has no rubric in durable storage and no
    bootstrap rubric on disk. Mapped to 404 by the endpoints."""


class AuditRecord(BaseModel):
    """The audit trail entry persisted alongside each rubric write.

    Carries exactly what the git commit used to record — version delta, note,
    actor identity, timestamp — as an explicit, queryable record rather than a
    commit message + author parsed back out of git. ``steward`` is the single
    reconciled placeholder identity until SSO lands (see
    ``rubric_write.PLACEHOLDER_STEWARD``).
    """

    product: str
    previous_version: str
    new_version: str
    note: str | None
    steward: str
    timestamp: str  # ISO 8601, UTC (e.g. "2026-06-02T13:45:01.123456+00:00")
    schema_version: int = 1


def _audit_blob_name(product: str, audit: AuditRecord) -> str:
    """``<product>/rubric/audit/<compact-ts>-<version>.json``.

    Compact timestamp (no colons) so the name is safe as both a blob name and a
    filesystem path; lexicographically sortable so a prefix listing is in
    chronological order.
    """
    compact = audit.timestamp.replace(":", "").replace("-", "").replace(".", "")
    return f"{product}/rubric/audit/{compact}-{audit.new_version}.json"


class RubricStore(Protocol):
    """Read + write seam for the durable rubric and its audit trail."""

    def load(self, product: str) -> tuple[dict[str, Any], str]:
        """Return ``(raw_rubric_dict, version)`` for the current rubric.

        Raises :class:`RubricNotFound` if the product has no rubric.
        """

    def save(
        self, product: str, *, rubric_raw: dict[str, Any], audit: AuditRecord
    ) -> str:
        """Persist the new rubric + audit record durably. Return an audit ref
        (the audit record's storage name) for the response/logs."""


# ---------------------------------------------------------------------------
# Disk backend (local dev + tests)
# ---------------------------------------------------------------------------


class DiskRubricStore:
    """Filesystem-backed store. The rubric lives at the same path the rest of
    the API reads in local dev, so all readers stay consistent on one disk."""

    def __init__(self, products_dir: Path) -> None:
        self._products_dir = products_dir

    def _rubric_path(self, product: str) -> Path:
        return self._products_dir / product / "rubric.yaml"

    def load(self, product: str) -> tuple[dict[str, Any], str]:
        path = self._rubric_path(product)
        if not path.exists():
            raise RubricNotFound(product)
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return raw, raw.get("version")

    def save(
        self, product: str, *, rubric_raw: dict[str, Any], audit: AuditRecord
    ) -> str:
        path = self._rubric_path(product)
        path.write_text(
            yaml.safe_dump(rubric_raw, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        # Audit records under a sibling dir so they don't pollute the product
        # config tree the loader globs.
        ref = _audit_blob_name(product, audit)
        audit_path = self._products_dir / ref
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(audit.model_dump_json(indent=2), encoding="utf-8")
        return ref


# ---------------------------------------------------------------------------
# Blob backend (deployed)
# ---------------------------------------------------------------------------


class BlobRubricStore:
    """Azure Blob-backed store, authenticated with the container's managed
    identity. Authoritative for the rubric; bootstraps from the image's
    ``rubric.yaml`` on a cold blob so a fresh deploy reads the seeded rubric and
    the first write makes the blob the source of truth.

    The grant is scoped to the ``mmfp-seed`` container (MLI-365); rubric state
    lives under the ``<product>/rubric/`` prefix, distinct from the seed DB at
    ``<product>/mmfp.db``.
    """

    def __init__(
        self,
        *,
        account_url: str,
        container: str,
        products_dir: Path,
    ) -> None:
        # Lazy import so the disk backend (and anyone who hasn't installed the
        # Azure SDK locally) never pays for these at module import.
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import ContainerClient

        self._products_dir = products_dir
        self._container = ContainerClient(
            account_url=account_url,
            container_name=container,
            credential=DefaultAzureCredential(),
        )

    @staticmethod
    def _rubric_blob(product: str) -> str:
        return f"{product}/rubric/rubric.yaml"

    def _bootstrap_from_disk(self, product: str) -> tuple[dict[str, Any], str]:
        disk = self._products_dir / product / "rubric.yaml"
        if not disk.exists():
            raise RubricNotFound(product)
        raw = yaml.safe_load(disk.read_text(encoding="utf-8"))
        logger.info("rubric.store.bootstrap_from_disk", extra={"product": product})
        return raw, raw.get("version")

    def load(self, product: str) -> tuple[dict[str, Any], str]:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            data = self._container.download_blob(self._rubric_blob(product)).readall()
        except ResourceNotFoundError:
            # Cold blob: fall back to the rubric shipped in the image.
            return self._bootstrap_from_disk(product)
        raw = yaml.safe_load(data)
        return raw, raw.get("version")

    def save(
        self, product: str, *, rubric_raw: dict[str, Any], audit: AuditRecord
    ) -> str:
        yaml_bytes = yaml.safe_dump(
            rubric_raw, sort_keys=False, allow_unicode=True
        ).encode("utf-8")
        # overwrite=True: the rubric blob is current-state (mutable).
        self._container.upload_blob(
            self._rubric_blob(product), yaml_bytes, overwrite=True
        )
        # overwrite=False: audit records are immutable and uniquely named; a
        # name collision (same timestamp+version) is a genuine error, not a
        # silent overwrite of history.
        ref = _audit_blob_name(product, audit)
        self._container.upload_blob(
            ref, audit.model_dump_json().encode("utf-8"), overwrite=False
        )
        return ref


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


def get_rubric_store() -> RubricStore:
    """Pick the backend from the environment: blob when configured, disk
    otherwise. FastAPI dependency for the read / write / preview endpoints."""
    products_dir = Path(os.environ.get("MMFP_PRODUCTS_DIR", "products"))
    account_url = os.environ.get(BLOB_ACCOUNT_URL_ENV, "").strip()
    container = os.environ.get(BLOB_CONTAINER_ENV, "").strip()
    if account_url and container:
        return BlobRubricStore(
            account_url=account_url, container=container, products_dir=products_dir
        )
    return DiskRubricStore(products_dir)
