"""Tests for drift-signals API endpoints (MFP-97).

Uses FastAPI TestClient with dependency_overrides, injecting a real
DriftSignalStore backed by a tmp_path SQLite file.

Routes under test:
  GET  /api/products/{product}/drift-signals
  POST /api/products/{product}/drift-signals/{signal_id}/acknowledge
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# Deferred imports per CLAUDE.md — keeps collection clean if module is absent.


def _make_signal(
    *,
    product_id: str = "mli",
    candidate_id: str = "kimi-k2-6",
    tier_id: str = "tier_1",
    baseline_run_id: str = "run-abc",
    baseline_score: Decimal = Decimal("80"),
    observed_score: Decimal = Decimal("50"),
    delta: Decimal = Decimal("-30"),
    severity: str = "high",
    summary: str = "kimi-k2-6 dropped 30 points on tier_1 vs baseline",
):
    from mmfp.models.drift import DriftSignal

    return DriftSignal(
        product_id=product_id,
        candidate_id=candidate_id,
        tier_id=tier_id,
        baseline_run_id=baseline_run_id,
        baseline_score=baseline_score,
        observed_score=observed_score,
        delta=delta,
        severity=severity,
        detected_at=datetime(2026, 6, 9, 12, 0, tzinfo=timezone.utc),
        summary=summary,
    )


@pytest.fixture()
def client(tmp_path: Path):
    """TestClient with DriftSignalStore overridden to use a tmp SQLite db."""
    from mmfp.api.main import app
    from mmfp.api import drift as drift_module
    from mmfp.persistence.drift_store import DriftSignalStore

    store = DriftSignalStore(tmp_path / "drift.db")

    app.dependency_overrides[drift_module.get_drift_store] = lambda: store
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def seeded_client(tmp_path: Path):
    """Client with two active signals plus one acknowledged, one other product."""
    from mmfp.api.main import app
    from mmfp.api import drift as drift_module
    from mmfp.persistence.drift_store import DriftSignalStore

    store = DriftSignalStore(tmp_path / "drift.db")
    id_a = store.append(_make_signal(candidate_id="kimi-k2-6", tier_id="tier_1"))
    id_b = store.append(_make_signal(candidate_id="gpt-4o", tier_id="tier_2"))
    id_c = store.append(_make_signal(candidate_id="kimi-k2-6", tier_id="tier_2"))
    # acknowledged — must not appear in active results
    store.acknowledge(id_c)
    # different product — must not bleed through
    store.append(_make_signal(product_id="other-product", candidate_id="kimi-k2-6"))

    app.dependency_overrides[drift_module.get_drift_store] = lambda: store
    yield TestClient(app), id_a, id_b
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /api/products/{product}/drift-signals
# ---------------------------------------------------------------------------


class TestGetDriftSignals:
    def test_returns_active_signals_for_product(self, seeded_client):
        client, id_a, id_b = seeded_client
        resp = client.get("/api/products/mli/drift-signals")
        assert resp.status_code == 200
        body = resp.json()
        assert body["product"] == "mli"
        signal_ids = {s["signal_id"] for s in body["signals"]}
        assert id_a in signal_ids
        assert id_b in signal_ids

    def test_does_not_include_acknowledged_signals(self, seeded_client):
        client, id_a, id_b = seeded_client
        resp = client.get("/api/products/mli/drift-signals")
        assert resp.status_code == 200
        body = resp.json()
        # Only two active signals remain (id_c was acknowledged in fixture)
        assert len(body["signals"]) == 2

    def test_does_not_include_other_product_signals(self, seeded_client):
        client, _, _ = seeded_client
        resp = client.get("/api/products/mli/drift-signals")
        assert resp.status_code == 200
        body = resp.json()
        assert all(s["product_id"] == "mli" for s in body["signals"])

    def test_filters_by_candidate_id(self, seeded_client):
        client, id_a, id_b = seeded_client
        resp = client.get("/api/products/mli/drift-signals?candidate_id=kimi-k2-6")
        assert resp.status_code == 200
        body = resp.json()
        signal_ids = {s["signal_id"] for s in body["signals"]}
        assert id_a in signal_ids
        assert id_b not in signal_ids  # gpt-4o excluded

    def test_empty_product_returns_empty_list(self, client):
        resp = client.get("/api/products/mli/drift-signals")
        assert resp.status_code == 200
        body = resp.json()
        assert body["product"] == "mli"
        assert body["signals"] == []

    def test_signal_shape_matches_schema(self, seeded_client):
        client, id_a, _ = seeded_client
        resp = client.get("/api/products/mli/drift-signals")
        assert resp.status_code == 200
        signals = resp.json()["signals"]
        # Find the signal we know exists
        sig = next(s for s in signals if s["signal_id"] == id_a)
        assert sig["product_id"] == "mli"
        assert sig["candidate_id"] == "kimi-k2-6"
        assert sig["tier_id"] == "tier_1"
        assert sig["status"] == "active"
        assert "severity" in sig
        assert "detected_at" in sig
        assert "summary" in sig


# ---------------------------------------------------------------------------
# POST /api/products/{product}/drift-signals/{signal_id}/acknowledge
# ---------------------------------------------------------------------------


class TestAcknowledge:
    def test_acknowledge_marks_signal(self, seeded_client):
        client, id_a, _ = seeded_client
        resp = client.post(f"/api/products/mli/drift-signals/{id_a}/acknowledge")
        assert resp.status_code == 200
        body = resp.json()
        assert body["signal_id"] == id_a
        assert body["acknowledged"] is True

        # Signal no longer appears in the active list
        list_resp = client.get("/api/products/mli/drift-signals")
        remaining_ids = {s["signal_id"] for s in list_resp.json()["signals"]}
        assert id_a not in remaining_ids

    def test_acknowledge_is_idempotent(self, seeded_client):
        client, id_a, _ = seeded_client
        resp1 = client.post(f"/api/products/mli/drift-signals/{id_a}/acknowledge")
        resp2 = client.post(f"/api/products/mli/drift-signals/{id_a}/acknowledge")
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp2.json()["acknowledged"] is True

    def test_acknowledge_unknown_signal_id_is_no_op(self, client):
        # ASSUMES: store.acknowledge is a no-op for unknown IDs (idempotency).
        resp = client.post("/api/products/mli/drift-signals/nonexistent-id/acknowledge")
        assert resp.status_code == 200
        assert resp.json()["acknowledged"] is True
