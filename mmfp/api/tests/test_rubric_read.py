"""Tests for GET /api/products/{product}/rubric (MLI-195, MLI-365).

Mirrors the harness used in test_rubric_write.py: dependency override for
``get_rubric_store`` (MLI-365 — reads go through the durable store, not directly
off disk), real rubric loaded from the repository's products/mli directory,
FastAPI TestClient.

Import of ``rubric_read`` is deferred into test bodies and helpers per
CLAUDE.md — a module-level import that fails at collection time (before -m
filtering) would break the whole pipeline.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Source of truth for a known-good rubric: the real products/mli/rubric.yaml.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_REFERENCE_RUBRIC_YAML = _REPO_ROOT / "products" / "mli" / "rubric.yaml"


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_client(products_dir: Path) -> TestClient:
    """Mount the rubric_read router with a DiskRubricStore bound to products_dir."""
    from mmfp.api import rubric_read  # deferred import
    from mmfp.api.main import app
    from mmfp.api.rubric_store import DiskRubricStore

    app.dependency_overrides[rubric_read.get_rubric_store] = lambda: DiskRubricStore(
        products_dir
    )
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def products_dir(tmp_path: Path) -> Path:
    """Tmp products dir with a copy of products/mli/rubric.yaml."""
    import shutil

    mli_dir = tmp_path / "products" / "mli"
    mli_dir.mkdir(parents=True)
    shutil.copy(_REFERENCE_RUBRIC_YAML, mli_dir / "rubric.yaml")
    return tmp_path / "products"


@pytest.fixture(autouse=True)
def _clear_overrides() -> None:
    """Prevent dependency_overrides leaking between tests."""
    yield
    from mmfp.api.main import app

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_200_returns_full_rubric_dict_and_version(products_dir: Path) -> None:
    """GET /api/products/mli/rubric → 200 with version, product, and full rubric.

    Asserts:
    - HTTP 200.
    - ``product`` and ``version`` fields are correct.
    - The returned ``rubric`` dict re-validates through ``Rubric.model_validate``
      so the Editor can POST it straight back to preview-impact or PUT.
    - Representative active dimension weight is present (tier_3 latency_p95 == 10
      per the v0.1 rubric shipped in products/mli/rubric.yaml).
    - Top-level structural keys ``schema_version``, ``gates``, ``judge`` are
      present (the Editor needs them for a verbatim round-trip).
    """
    from mmfp.models.rubric import Rubric

    client = _make_client(products_dir)
    resp = client.get("/api/products/mli/rubric")
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert data["product"] == "mli"
    assert data["version"] == "v0.1"

    rubric_dict = data["rubric"]

    # Round-trip: the dict must re-validate through Rubric without error.
    revalidated = Rubric.model_validate(rubric_dict)
    assert revalidated.version == "v0.1"

    # Structural keys that the Editor needs for a verbatim round-trip.
    assert "schema_version" in rubric_dict
    assert "gates" in rubric_dict
    assert "judge" in rubric_dict

    # Spot-check a representative active dimension weight in tier_3.
    tier_3 = next(t for t in rubric_dict["tiers"] if t["id"] == "tier_3")
    latency_dim = next(
        (d for d in tier_3["dimensions"] if d["id"] == "latency_p95"),
        None,
    )
    assert latency_dim is not None, "latency_p95 dimension missing from tier_3"
    # Weight may arrive as a string (Decimal serialisation) or int/float.
    assert float(latency_dim["weight"]) == 10, latency_dim


def test_404_on_unknown_product(products_dir: Path) -> None:
    """GET /api/products/does-not-exist/rubric → 404."""
    client = _make_client(products_dir)
    resp = client.get("/api/products/does-not-exist/rubric")
    assert resp.status_code == 404, resp.text
    assert "does-not-exist" in resp.json()["detail"]
