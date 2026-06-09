"""Tests for dataset endpoints (MFP-75).

  GET  /api/products/{product}/datasets/{tier_id}
  POST /api/products/{product}/datasets/{tier_id}/examples

Uses FastAPI's TestClient with dependency_overrides to inject a tmp_path
products directory rather than the real `products/` tree.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_products_dir(tmp_path: Path, *, with_dataset: bool = True) -> Path:
    """Create a minimal products dir with one product and optional dataset."""
    product_dir = tmp_path / "products" / "mli"
    product_dir.mkdir(parents=True)

    # Minimal candidates.yaml so the product is valid.
    (product_dir / "candidates.yaml").write_text(
        "candidates:\n"
        "  - id: c1\n"
        "    display_name: C1\n"
        "    family: chat\n"
        "    max_tokens: 100\n"
        "    context_window: 4096\n"
        "    tiers: [tier_3]\n"
        "    status: under_evaluation\n"
        "    binding:\n"
        "      provider: azure_foundry\n"
        "      endpoint: https://example.cognitiveservices.azure.com\n"
        "      deployment: dep-c1\n"
        "      api_version: '2024-12-01-preview'\n"
        "      auth_method: api_key_header\n"
        "      key_vault_secret_name: fake-key\n",
        encoding="utf-8",
    )

    if with_dataset:
        datasets_dir = product_dir / "datasets"
        datasets_dir.mkdir()
        seed = {"id": "ex-001", "input": "Hello?", "expected": "Hi", "tags": []}
        (datasets_dir / "tier_3.jsonl").write_text(
            json.dumps(seed) + "\n", encoding="utf-8"
        )

    return tmp_path / "products"


def _make_client(products_dir: Path):
    # Deferred imports so collection succeeds before the module exists (CLAUDE.md).
    from mmfp.api import datasets as ds_module
    from mmfp.api.main import app
    from fastapi.testclient import TestClient

    app.dependency_overrides[ds_module.get_products_dir] = lambda: products_dir
    app.dependency_overrides[ds_module.get_candidate_loader] = lambda: (
        lambda product: _load_candidates(products_dir, product)
    )
    client = TestClient(app)
    return client, ds_module


def _load_candidates(products_dir: Path, product: str):
    import yaml
    from mmfp.models.candidate import Candidate

    slate_path = products_dir / product / "candidates.yaml"
    if not slate_path.exists():
        raise FileNotFoundError
    raw = yaml.safe_load(slate_path.read_text(encoding="utf-8"))
    return [Candidate.model_validate(c) for c in raw["candidates"]]


# ---------------------------------------------------------------------------
# GET tests
# ---------------------------------------------------------------------------


def test_get_examples_returns_all(tmp_path):
    products_dir = _make_products_dir(tmp_path, with_dataset=True)
    client, ds_module = _make_client(products_dir)
    try:
        resp = client.get("/api/products/mli/datasets/tier_3")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "ex-001"
    finally:
        from mmfp.api.main import app
        app.dependency_overrides.pop(ds_module.get_products_dir, None)
        app.dependency_overrides.pop(ds_module.get_candidate_loader, None)


def test_get_examples_unknown_product(tmp_path):
    products_dir = _make_products_dir(tmp_path, with_dataset=True)
    client, ds_module = _make_client(products_dir)
    try:
        resp = client.get("/api/products/no-such-product/datasets/tier_3")
        assert resp.status_code == 404
    finally:
        from mmfp.api.main import app
        app.dependency_overrides.pop(ds_module.get_products_dir, None)
        app.dependency_overrides.pop(ds_module.get_candidate_loader, None)


def test_get_examples_unknown_tier(tmp_path):
    products_dir = _make_products_dir(tmp_path, with_dataset=True)
    client, ds_module = _make_client(products_dir)
    try:
        resp = client.get("/api/products/mli/datasets/tier_99")
        assert resp.status_code == 404
    finally:
        from mmfp.api.main import app
        app.dependency_overrides.pop(ds_module.get_products_dir, None)
        app.dependency_overrides.pop(ds_module.get_candidate_loader, None)


def test_get_examples_no_dataset_file(tmp_path):
    products_dir = _make_products_dir(tmp_path, with_dataset=False)
    client, ds_module = _make_client(products_dir)
    try:
        resp = client.get("/api/products/mli/datasets/tier_3")
        assert resp.status_code == 404
    finally:
        from mmfp.api.main import app
        app.dependency_overrides.pop(ds_module.get_products_dir, None)
        app.dependency_overrides.pop(ds_module.get_candidate_loader, None)


# ---------------------------------------------------------------------------
# POST tests
# ---------------------------------------------------------------------------


def test_add_example_appends(tmp_path):
    products_dir = _make_products_dir(tmp_path, with_dataset=True)
    client, ds_module = _make_client(products_dir)
    try:
        payload = {
            "id": "ex-new",
            "input": "Summarise this.",
            "expected": {"answer": "ok"},
            "tags": ["synthesis"],
        }
        resp = client.post("/api/products/mli/datasets/tier_3/examples", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] == "ex-new"

        # Confirm the line was physically appended to the file.
        lines = (
            (products_dir / "mli" / "datasets" / "tier_3.jsonl")
            .read_text(encoding="utf-8")
            .strip()
            .splitlines()
        )
        assert len(lines) == 2
        appended = json.loads(lines[1])
        assert appended["id"] == "ex-new"
    finally:
        from mmfp.api.main import app
        app.dependency_overrides.pop(ds_module.get_products_dir, None)
        app.dependency_overrides.pop(ds_module.get_candidate_loader, None)


def test_add_example_auto_id(tmp_path):
    products_dir = _make_products_dir(tmp_path, with_dataset=True)
    client, ds_module = _make_client(products_dir)
    try:
        payload = {"input": "What is 2+2?", "expected": "4"}
        resp = client.post("/api/products/mli/datasets/tier_3/examples", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"]  # server assigned a non-empty id
    finally:
        from mmfp.api.main import app
        app.dependency_overrides.pop(ds_module.get_products_dir, None)
        app.dependency_overrides.pop(ds_module.get_candidate_loader, None)


def test_add_example_missing_required(tmp_path):
    products_dir = _make_products_dir(tmp_path, with_dataset=True)
    client, ds_module = _make_client(products_dir)
    try:
        # `input` is required; omitting it should trigger Pydantic validation → 422.
        resp = client.post(
            "/api/products/mli/datasets/tier_3/examples", json={"expected": "x"}
        )
        assert resp.status_code == 422
    finally:
        from mmfp.api.main import app
        app.dependency_overrides.pop(ds_module.get_products_dir, None)
        app.dependency_overrides.pop(ds_module.get_candidate_loader, None)


def test_add_example_unknown_product(tmp_path):
    products_dir = _make_products_dir(tmp_path, with_dataset=True)
    client, ds_module = _make_client(products_dir)
    try:
        payload = {"input": "Hi", "expected": "Hello"}
        resp = client.post(
            "/api/products/ghost/datasets/tier_3/examples", json=payload
        )
        assert resp.status_code == 404
    finally:
        from mmfp.api.main import app
        app.dependency_overrides.pop(ds_module.get_products_dir, None)
        app.dependency_overrides.pop(ds_module.get_candidate_loader, None)
