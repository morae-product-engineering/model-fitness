"""Tests for the durable rubric store (MLI-365).

Covers the contract both backends share (load/save round-trip, RubricNotFound,
audit record) on the disk backend, and the blob-specific behaviour that is the
whole point of the ticket — cold-blob bootstrap from the image and survival of
a revision restart — on ``BlobRubricStore`` with a fake in-memory container
client (no real Azure).

Imports of ``rubric_store`` are deferred into test bodies per CLAUDE.md.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_REFERENCE_RUBRIC_YAML = _REPO_ROOT / "products" / "mli" / "rubric.yaml"


def _products_dir(tmp_path: Path) -> Path:
    mli_dir = tmp_path / "products" / "mli"
    mli_dir.mkdir(parents=True)
    shutil.copy(_REFERENCE_RUBRIC_YAML, mli_dir / "rubric.yaml")
    return tmp_path / "products"


def _audit(product: str = "mli", *, prev: str = "v0.1", new: str = "v0.2"):
    from mmfp.api.rubric_store import AuditRecord

    return AuditRecord(
        product=product,
        previous_version=prev,
        new_version=new,
        note="test",
        steward="Unknown Steward <steward@unknown.local>",
        timestamp="2026-06-02T13:45:01.123456+00:00",
    )


# ---------------------------------------------------------------------------
# Disk backend — shared contract
# ---------------------------------------------------------------------------


def test_disk_store_load_returns_dict_and_version(tmp_path: Path) -> None:
    from mmfp.api.rubric_store import DiskRubricStore

    store = DiskRubricStore(_products_dir(tmp_path))
    raw, version = store.load("mli")
    assert version == "v0.1"
    assert raw["version"] == "v0.1"


def test_disk_store_unknown_product_raises(tmp_path: Path) -> None:
    from mmfp.api.rubric_store import DiskRubricStore, RubricNotFound

    store = DiskRubricStore(_products_dir(tmp_path))
    with pytest.raises(RubricNotFound):
        store.load("does-not-exist")


def test_disk_store_save_round_trips_and_writes_audit(tmp_path: Path) -> None:
    from mmfp.api.rubric_store import DiskRubricStore

    products_dir = _products_dir(tmp_path)
    store = DiskRubricStore(products_dir)

    raw, _ = store.load("mli")
    raw["version"] = "v0.2"
    ref = store.save("mli", rubric_raw=raw, audit=_audit())

    # Reload reflects the saved version.
    reloaded, version = store.load("mli")
    assert version == "v0.2"

    # Audit ref resolves to a real record under the product prefix.
    audit_path = products_dir / ref
    assert audit_path.exists()
    import json

    rec = json.loads(audit_path.read_text())
    assert rec["new_version"] == "v0.2"
    assert rec["steward"] == "Unknown Steward <steward@unknown.local>"


def test_get_rubric_store_defaults_to_disk(tmp_path: Path, monkeypatch) -> None:
    from mmfp.api import rubric_store

    monkeypatch.delenv(rubric_store.BLOB_ACCOUNT_URL_ENV, raising=False)
    monkeypatch.delenv(rubric_store.BLOB_CONTAINER_ENV, raising=False)
    assert isinstance(rubric_store.get_rubric_store(), rubric_store.DiskRubricStore)


# ---------------------------------------------------------------------------
# Blob backend — fake container client
# ---------------------------------------------------------------------------


class _FakeDownload:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def readall(self) -> bytes:
        return self._data


class _FakeContainerClient:
    """In-memory stand-in for azure.storage.blob.ContainerClient. Shared across
    constructions so a 'restart' (new BlobRubricStore) sees prior writes — that
    is exactly the durability property under test."""

    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}

    def download_blob(self, name: str):
        from azure.core.exceptions import ResourceNotFoundError

        if name not in self.blobs:
            raise ResourceNotFoundError(name)
        return _FakeDownload(self.blobs[name])

    def upload_blob(self, name: str, data, overwrite: bool = False) -> None:
        from azure.core.exceptions import ResourceExistsError

        if name in self.blobs and not overwrite:
            raise ResourceExistsError(name)
        self.blobs[name] = data if isinstance(data, bytes) else data.encode("utf-8")


@pytest.fixture
def fake_blob(monkeypatch):
    """Patch BlobRubricStore's azure constructions to use a single shared fake
    container, and stub DefaultAzureCredential. Returns the fake so tests can
    inspect what landed in 'blob storage'."""
    import azure.identity as identity_mod
    import azure.storage.blob as blob_mod

    fake = _FakeContainerClient()
    monkeypatch.setattr(blob_mod, "ContainerClient", lambda **kwargs: fake)
    monkeypatch.setattr(identity_mod, "DefaultAzureCredential", lambda *a, **k: object())
    return fake


def _blob_store(products_dir: Path):
    from mmfp.api.rubric_store import BlobRubricStore

    return BlobRubricStore(
        account_url="https://stmmfpdevuks.blob.core.windows.net",
        container="mmfp-seed",
        products_dir=products_dir,
    )


def test_blob_cold_read_bootstraps_from_image(tmp_path: Path, fake_blob) -> None:
    """First read on a cold blob falls back to the rubric shipped in the image."""
    store = _blob_store(_products_dir(tmp_path))
    raw, version = store.load("mli")
    assert version == "v0.1"
    # Nothing was written to the blob just by reading.
    assert fake_blob.blobs == {}


def test_blob_save_then_read_is_durable_across_restart(tmp_path: Path, fake_blob) -> None:
    """Save bumps to v0.2; a FRESH store instance (simulating a revision
    restart) reads v0.2 from the blob, not the image's v0.1. This is the
    durability criterion that empirically unblocks Slice 4."""
    products_dir = _products_dir(tmp_path)

    store = _blob_store(products_dir)
    raw, _ = store.load("mli")
    raw["version"] = "v0.2"
    ref = store.save("mli", rubric_raw=raw, audit=_audit())
    assert ref.startswith("mli/rubric/audit/") and ref.endswith("-v0.2.json")

    # Simulate a revision restart: brand-new store, same backing blob storage.
    restarted = _blob_store(products_dir)
    raw_after, version_after = restarted.load("mli")
    assert version_after == "v0.2", "saved rubric did not survive the 'restart'"

    # The rubric blob and exactly one immutable audit record are present.
    assert "mli/rubric/rubric.yaml" in fake_blob.blobs
    audit_blobs = [k for k in fake_blob.blobs if k.startswith("mli/rubric/audit/")]
    assert len(audit_blobs) == 1


def test_blob_unknown_product_with_no_bootstrap_raises(tmp_path: Path, fake_blob) -> None:
    from mmfp.api.rubric_store import RubricNotFound

    store = _blob_store(_products_dir(tmp_path))
    with pytest.raises(RubricNotFound):
        store.load("nope")


def test_blob_audit_record_is_immutable(tmp_path: Path, fake_blob) -> None:
    """Audit blobs are uploaded with overwrite=False — a name collision is an
    error, never a silent overwrite of history."""
    from azure.core.exceptions import ResourceExistsError

    store = _blob_store(_products_dir(tmp_path))
    raw, _ = store.load("mli")
    raw["version"] = "v0.2"
    store.save("mli", rubric_raw=raw, audit=_audit())
    # Same timestamp+version → same audit name → must refuse to overwrite.
    with pytest.raises(ResourceExistsError):
        store.save("mli", rubric_raw=raw, audit=_audit())
