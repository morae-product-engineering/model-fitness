"""Startup-time SQLite seed download for the API container (MLI-177).

The CI ``baseline-matrix`` workflow runs the matrix against real Foundry
deployments, produces a ``MatrixRun`` persisted to a local SQLite file,
uploads that file to Azure Blob Storage, and writes a read-only SAS URL
into the dev Container App's ``MMFP_SEED_BLOB_URL`` env var. The Container
App auto-restarts on env-var change; on startup the API calls
:func:`download_seed_if_configured` to fetch that blob into
:envvar:`MMFP_DB_PATH` *before* uvicorn starts serving requests.

Non-fatal by design: any failure (var unset, HTTP error, write error)
logs a warning and returns. The API then serves whatever DB state exists
locally — typically empty on first boot, so ``/api/products/.../scoreboard``
will 404 until a successful seed lands. This is the right trade-off for
R1: a broken seed must not take the API down.

Atomic write: stream to ``<db>.seed-tmp`` then :func:`os.replace` so an
in-flight ``MatrixRunRepository`` query can't observe a half-written file.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

SEED_BLOB_URL_ENV = "MMFP_SEED_BLOB_URL"
DB_PATH_ENV = "MMFP_DB_PATH"
DEFAULT_DB_PATH = "data/mmfp.db"
DOWNLOAD_TIMEOUT_S = 60.0


def download_seed_if_configured() -> None:
    """Download the seed blob into ``MMFP_DB_PATH`` if ``MMFP_SEED_BLOB_URL`` is set.

    Idempotent re-runs are fine: each call overwrites the target file.
    All failure modes are swallowed with a warning log; the caller does
    not need a try/except.
    """
    url = os.environ.get(SEED_BLOB_URL_ENV, "").strip()
    if not url:
        logger.info("Seed download skipped — %s not set", SEED_BLOB_URL_ENV)
        return

    db_path = Path(os.environ.get(DB_PATH_ENV, DEFAULT_DB_PATH))
    tmp_path = db_path.with_suffix(db_path.suffix + ".seed-tmp")

    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream("GET", url, timeout=DOWNLOAD_TIMEOUT_S) as response:
            response.raise_for_status()
            with tmp_path.open("wb") as fh:
                for chunk in response.iter_bytes():
                    fh.write(chunk)
        os.replace(tmp_path, db_path)
        logger.info(
            "Seed DB downloaded",
            extra={"db_path": str(db_path), "bytes": db_path.stat().st_size},
        )
    except Exception as exc:  # noqa: BLE001 — startup boundary; never crash the API
        # Log URL host, not the full URL — SAS tokens include a signed query
        # string that should not appear in logs.
        host = httpx.URL(url).host if url else "<unset>"
        logger.warning(
            "Seed download failed — continuing with existing DB state: %s (%s)",
            type(exc).__name__,
            host,
        )
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
