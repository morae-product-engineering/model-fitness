"""Tests for judge-queue endpoints (MFP-75).

  GET  /api/products/{product}/judge-queue?status={pending|reviewed}
  POST /api/products/{product}/judge-queue/{sample_id}/mark

Uses FastAPI's TestClient with dependency_overrides to inject a tmp_path
SQLite DB and an in-memory candidate loader.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_products_dir(tmp_path: Path) -> Path:
    product_dir = tmp_path / "products" / "mli"
    product_dir.mkdir(parents=True)
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
    return tmp_path / "products"


def _load_candidates(products_dir: Path, product: str):
    import yaml
    from mmfp.models.candidate import Candidate

    slate_path = products_dir / product / "candidates.yaml"
    if not slate_path.exists():
        raise FileNotFoundError
    raw = yaml.safe_load(slate_path.read_text(encoding="utf-8"))
    return [Candidate.model_validate(c) for c in raw["candidates"]]


def _insert_sample(db_path: Path, sample_id: str, product: str = "mli", decision: str = "pending") -> None:
    from mmfp.persistence.judge_queue_repository import JudgeQueueRepository

    repo = JudgeQueueRepository(db_path)
    repo._ensure_schema()
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO judge_queue_samples
            (id, product, tier_id, example_id, candidate_id, model_output, decision)
        VALUES (?, ?, 'tier_3', 'ex-001', 'c1', 'Some output', ?)
        """,
        (sample_id, product, decision),
    )
    conn.commit()
    conn.close()


def _make_client(tmp_path: Path):
    from mmfp.api import judge_queue as jq_module
    from mmfp.api.main import app
    from mmfp.persistence.judge_queue_repository import JudgeQueueRepository
    from fastapi.testclient import TestClient

    db_path = tmp_path / "test.db"
    products_dir = _make_products_dir(tmp_path)
    repo = JudgeQueueRepository(db_path)

    app.dependency_overrides[jq_module.get_judge_queue_repo] = lambda: repo
    app.dependency_overrides[jq_module.get_candidate_loader] = lambda: (
        lambda product: _load_candidates(products_dir, product)
    )
    client = TestClient(app)
    return client, jq_module, db_path


# ---------------------------------------------------------------------------
# GET tests
# ---------------------------------------------------------------------------


def test_list_samples_empty(tmp_path):
    client, jq_module, _ = _make_client(tmp_path)
    try:
        resp = client.get("/api/products/mli/judge-queue")
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        from mmfp.api.main import app
        app.dependency_overrides.pop(jq_module.get_judge_queue_repo, None)
        app.dependency_overrides.pop(jq_module.get_candidate_loader, None)


def test_list_samples_returns_seeded(tmp_path):
    client, jq_module, db_path = _make_client(tmp_path)
    try:
        _insert_sample(db_path, "s-001")
        resp = client.get("/api/products/mli/judge-queue")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "s-001"
        assert data[0]["decision"] == "pending"
    finally:
        from mmfp.api.main import app
        app.dependency_overrides.pop(jq_module.get_judge_queue_repo, None)
        app.dependency_overrides.pop(jq_module.get_candidate_loader, None)


def test_list_samples_filter_pending(tmp_path):
    client, jq_module, db_path = _make_client(tmp_path)
    try:
        _insert_sample(db_path, "s-pending", decision="pending")
        _insert_sample(db_path, "s-agree", decision="agree")
        resp = client.get("/api/products/mli/judge-queue?status=pending")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "s-pending"
    finally:
        from mmfp.api.main import app
        app.dependency_overrides.pop(jq_module.get_judge_queue_repo, None)
        app.dependency_overrides.pop(jq_module.get_candidate_loader, None)


def test_list_samples_filter_reviewed(tmp_path):
    client, jq_module, db_path = _make_client(tmp_path)
    try:
        _insert_sample(db_path, "s-pending", decision="pending")
        _insert_sample(db_path, "s-agree", decision="agree")
        _insert_sample(db_path, "s-disagree", decision="disagree")
        resp = client.get("/api/products/mli/judge-queue?status=reviewed")
        assert resp.status_code == 200
        data = resp.json()
        ids = {r["id"] for r in data}
        assert ids == {"s-agree", "s-disagree"}
    finally:
        from mmfp.api.main import app
        app.dependency_overrides.pop(jq_module.get_judge_queue_repo, None)
        app.dependency_overrides.pop(jq_module.get_candidate_loader, None)


# ---------------------------------------------------------------------------
# POST mark tests
# ---------------------------------------------------------------------------


def test_mark_agree(tmp_path):
    client, jq_module, db_path = _make_client(tmp_path)
    try:
        _insert_sample(db_path, "s-001")
        resp = client.post(
            "/api/products/mli/judge-queue/s-001/mark",
            json={"decision": "agree"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["decision"] == "agree"
        assert body["decided_at"] is not None
    finally:
        from mmfp.api.main import app
        app.dependency_overrides.pop(jq_module.get_judge_queue_repo, None)
        app.dependency_overrides.pop(jq_module.get_candidate_loader, None)


def test_mark_disagree_with_note(tmp_path):
    client, jq_module, db_path = _make_client(tmp_path)
    try:
        _insert_sample(db_path, "s-001")
        resp = client.post(
            "/api/products/mli/judge-queue/s-001/mark",
            json={"decision": "disagree", "note": "Judge hallucinated the citation."},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["decision"] == "disagree"
        assert body["note"] == "Judge hallucinated the citation."
    finally:
        from mmfp.api.main import app
        app.dependency_overrides.pop(jq_module.get_judge_queue_repo, None)
        app.dependency_overrides.pop(jq_module.get_candidate_loader, None)


def test_mark_unknown_sample(tmp_path):
    client, jq_module, _ = _make_client(tmp_path)
    try:
        resp = client.post(
            "/api/products/mli/judge-queue/no-such-id/mark",
            json={"decision": "agree"},
        )
        assert resp.status_code == 404
    finally:
        from mmfp.api.main import app
        app.dependency_overrides.pop(jq_module.get_judge_queue_repo, None)
        app.dependency_overrides.pop(jq_module.get_candidate_loader, None)


def test_mark_invalid_decision(tmp_path):
    client, jq_module, db_path = _make_client(tmp_path)
    try:
        _insert_sample(db_path, "s-001")
        resp = client.post(
            "/api/products/mli/judge-queue/s-001/mark",
            json={"decision": "maybe"},
        )
        assert resp.status_code == 422
    finally:
        from mmfp.api.main import app
        app.dependency_overrides.pop(jq_module.get_judge_queue_repo, None)
        app.dependency_overrides.pop(jq_module.get_candidate_loader, None)
