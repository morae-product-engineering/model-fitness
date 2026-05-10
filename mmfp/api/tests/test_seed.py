"""Tests for the API startup seed-download hook (MLI-177)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from mmfp.api import seed


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch, tmp_path):
    """Each test starts with no seed env vars and a tmp DB path."""
    monkeypatch.delenv(seed.SEED_BLOB_URL_ENV, raising=False)
    monkeypatch.setenv(seed.DB_PATH_ENV, str(tmp_path / "mmfp.db"))


def _install_transport(monkeypatch, handler):
    """Route every httpx.stream call through a MockTransport handler."""
    transport = httpx.MockTransport(handler)

    def fake_stream(method, url, **kwargs):
        client = httpx.Client(transport=transport)
        return client.stream(method, url, **kwargs)

    monkeypatch.setattr(seed.httpx, "stream", fake_stream)


def test_no_op_when_env_var_unset(monkeypatch, tmp_path, caplog):
    """No url → no download, no error, no file created."""
    db_path = Path(tmp_path / "mmfp.db")
    with caplog.at_level("INFO", logger=seed.__name__):
        seed.download_seed_if_configured()
    assert not db_path.exists()
    assert any("Seed download skipped" in r.message for r in caplog.records)


def test_no_op_when_env_var_empty(monkeypatch, tmp_path):
    """Empty / whitespace-only url is treated identical to unset."""
    monkeypatch.setenv(seed.SEED_BLOB_URL_ENV, "   ")
    seed.download_seed_if_configured()
    assert not Path(tmp_path / "mmfp.db").exists()


def test_downloads_blob_to_db_path(monkeypatch, tmp_path):
    """Happy path: 200 OK → bytes land at MMFP_DB_PATH."""
    payload = b"SQLite format 3\x00" + b"\x00" * 4096
    monkeypatch.setenv(
        seed.SEED_BLOB_URL_ENV,
        "https://example.blob.core.windows.net/seed/mmfp.db?sv=fake",
    )
    _install_transport(
        monkeypatch,
        lambda request: httpx.Response(200, content=payload),
    )

    seed.download_seed_if_configured()

    db_path = Path(tmp_path / "mmfp.db")
    assert db_path.read_bytes() == payload
    # Atomic-rename leaves no stragglers.
    assert not (tmp_path / "mmfp.db.seed-tmp").exists()


def test_creates_parent_directory(monkeypatch, tmp_path):
    """Parent of MMFP_DB_PATH is created if missing — fresh container case."""
    nested = tmp_path / "nested" / "deeper" / "mmfp.db"
    monkeypatch.setenv(seed.DB_PATH_ENV, str(nested))
    monkeypatch.setenv(
        seed.SEED_BLOB_URL_ENV,
        "https://example.blob.core.windows.net/seed/mmfp.db?sv=fake",
    )
    _install_transport(
        monkeypatch,
        lambda request: httpx.Response(200, content=b"db-bytes"),
    )

    seed.download_seed_if_configured()

    assert nested.read_bytes() == b"db-bytes"


def test_http_error_is_non_fatal_and_leaves_existing_db_untouched(
    monkeypatch, tmp_path, caplog
):
    """403/404/quota errors must not raise — API stays up on existing state.

    The dev workflow may be mid-rotation (SAS expired, blob deleted, etc.)
    and the API should continue serving the previous seed (or empty DB)
    rather than crash-looping the Container App.
    """
    db_path = Path(tmp_path / "mmfp.db")
    db_path.write_bytes(b"previous-seed")

    monkeypatch.setenv(
        seed.SEED_BLOB_URL_ENV,
        "https://example.blob.core.windows.net/seed/mmfp.db?sv=fake",
    )
    _install_transport(
        monkeypatch,
        lambda request: httpx.Response(403, text="AuthenticationFailed"),
    )

    with caplog.at_level("WARNING", logger=seed.__name__):
        seed.download_seed_if_configured()  # must not raise

    # Existing DB content is preserved — atomic rename means the failed
    # download never overwrote it.
    assert db_path.read_bytes() == b"previous-seed"
    assert any("Seed download failed" in r.message for r in caplog.records)
    assert not (tmp_path / "mmfp.db.seed-tmp").exists()


def test_connection_error_is_non_fatal(monkeypatch, tmp_path, caplog):
    """Network failures during the stream are swallowed and logged."""
    monkeypatch.setenv(
        seed.SEED_BLOB_URL_ENV,
        "https://example.blob.core.windows.net/seed/mmfp.db?sv=fake",
    )

    def explode(request):
        raise httpx.ConnectError("dns no", request=request)

    _install_transport(monkeypatch, explode)

    with caplog.at_level("WARNING", logger=seed.__name__):
        seed.download_seed_if_configured()  # must not raise

    assert any("Seed download failed" in r.message for r in caplog.records)


def test_warning_log_redacts_sas_query_string(monkeypatch, tmp_path, caplog):
    """Failure logs must not echo the SAS token (`?sv=...&sig=...`)."""
    secret_sig = "sig=hunter2-extremely-secret-token"
    monkeypatch.setenv(
        seed.SEED_BLOB_URL_ENV,
        f"https://example.blob.core.windows.net/seed/mmfp.db?sv=fake&{secret_sig}",
    )
    _install_transport(
        monkeypatch,
        lambda request: httpx.Response(500, text="boom"),
    )

    with caplog.at_level("WARNING", logger=seed.__name__):
        seed.download_seed_if_configured()

    combined = " ".join(r.message for r in caplog.records)
    assert "sig=" not in combined
    assert "hunter2" not in combined
