"""Low-level durable blob seam (MLI-201).

A byte-level read / write / list-prefix abstraction over a single blob
container, with an Azure managed-identity backend for the deployed environment
and a local-disk backend for dev and tests. This is the plumbing the MLI-365
rubric store (`mmfp/api/rubric_store.py:BlobRubricStore`) hand-rolled inline; the
Slice-5 audit log (`audit_log.py`) builds its append-only, hash-chained record
store on top of this seam rather than re-implementing the Azure wiring.

The seam is deliberately content-agnostic — no YAML, no JSON, no audit
semantics — so a future shared rubric+audit primitive (the "Option B" refactor
deferred on MLI-201) can re-point `BlobRubricStore` at the same seam cheaply.
This module does NOT touch the shipped rubric save path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class BlobAlreadyExists(Exception):
    """Raised by ``write(..., overwrite=False)`` when the name is already taken.

    The immutability guarantee append-only callers rely on: a name collision is
    an error, never a silent overwrite of history.
    """


class BlobSeam(Protocol):
    """Byte-level durable storage over a flat namespace of blob names."""

    def read(self, name: str) -> bytes | None:
        """Return the blob's bytes, or None if it does not exist."""

    def write(self, name: str, data: bytes, *, overwrite: bool) -> None:
        """Write bytes under ``name``. With ``overwrite=False`` an existing
        name raises :class:`BlobAlreadyExists`."""

    def list_names(self, prefix: str) -> list[str]:
        """All blob names starting with ``prefix``, sorted ascending. A bounded
        prefix turns a query into a bounded scan rather than list-everything."""


class DiskBlobSeam:
    """Filesystem-backed seam for local dev and tests. Blob names map to paths
    under ``root``; the on-disk layout mirrors the blob namespace 1:1."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    def _path(self, name: str) -> Path:
        return self._root / name

    def read(self, name: str) -> bytes | None:
        path = self._path(name)
        if not path.exists():
            return None
        return path.read_bytes()

    def write(self, name: str, data: bytes, *, overwrite: bool) -> None:
        path = self._path(name)
        if path.exists() and not overwrite:
            raise BlobAlreadyExists(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def list_names(self, prefix: str) -> list[str]:
        if not self._root.exists():
            return []
        names = [
            p.relative_to(self._root).as_posix()
            for p in self._root.rglob("*")
            if p.is_file()
        ]
        return sorted(n for n in names if n.startswith(prefix))


class AzureBlobSeam:
    """Azure Blob-backed seam, authenticated with the container's managed
    identity. The deployed backend. ``list_names`` uses a server-side
    ``name_starts_with`` filter, so a bounded prefix is a bounded listing."""

    def __init__(self, *, account_url: str, container: str) -> None:
        # Lazy import so the disk backend (and anyone without the Azure SDK
        # installed locally) never pays for these at module import.
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import ContainerClient

        self._container = ContainerClient(
            account_url=account_url,
            container_name=container,
            credential=DefaultAzureCredential(),
        )

    def read(self, name: str) -> bytes | None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            return self._container.download_blob(name).readall()
        except ResourceNotFoundError:
            return None

    def write(self, name: str, data: bytes, *, overwrite: bool) -> None:
        from azure.core.exceptions import ResourceExistsError

        try:
            self._container.upload_blob(name, data, overwrite=overwrite)
        except ResourceExistsError as exc:
            raise BlobAlreadyExists(name) from exc

    def list_names(self, prefix: str) -> list[str]:
        return sorted(b.name for b in self._container.list_blobs(name_starts_with=prefix))
