"""Unit tests for DriftSignalStore (MFP-96).

Tests use real SQLite files under `tmp_path`; no mocks for the DB.
DriftSignal instances are constructed in-memory — keeps tests focused on
the persistence boundary, not signal generation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from mmfp.models.drift import DriftSignal
from mmfp.persistence.drift_store import DriftSignalStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _signal(
    *,
    product_id: str = "mli",
    candidate_id: str = "kimi-k2-6",
    tier_id: str = "tier_1",
    baseline_run_id: str = "run-abc",
    baseline_score: Decimal = Decimal("80"),
    observed_score: Decimal = Decimal("50"),
    delta: Decimal = Decimal("-30"),
    severity: str = "high",
    detected_at: datetime | None = None,
    summary: str = "kimi-k2-6 dropped 30 points on tier_1 vs baseline",
) -> DriftSignal:
    return DriftSignal(
        product_id=product_id,
        candidate_id=candidate_id,
        tier_id=tier_id,
        baseline_run_id=baseline_run_id,
        baseline_score=baseline_score,
        observed_score=observed_score,
        delta=delta,
        severity=severity,
        detected_at=detected_at or datetime(2026, 6, 9, 12, 0, tzinfo=timezone.utc),
        summary=summary,
    )


@pytest.fixture
def store(tmp_path: Path) -> DriftSignalStore:
    return DriftSignalStore(tmp_path / "mmfp.db")


# ---------------------------------------------------------------------------
# append + list_active
# ---------------------------------------------------------------------------


def test_append_then_list_active_returns_signal(store: DriftSignalStore) -> None:
    signal = _signal()
    store.append(signal)

    active = store.list_active(product_id="mli", candidate_id="kimi-k2-6")

    assert len(active) == 1
    assert active[0] == signal


def test_append_returns_unique_ids(store: DriftSignalStore) -> None:
    id1 = store.append(_signal())
    id2 = store.append(_signal())

    assert id1 != id2


def test_list_active_returns_empty_when_none_exist(store: DriftSignalStore) -> None:
    assert store.list_active(product_id="mli", candidate_id="kimi-k2-6") == []


def test_list_active_filters_by_product(store: DriftSignalStore) -> None:
    store.append(_signal(product_id="mli"))
    store.append(_signal(product_id="other"))

    mli = store.list_active(product_id="mli", candidate_id="kimi-k2-6")
    other = store.list_active(product_id="other", candidate_id="kimi-k2-6")

    assert len(mli) == 1
    assert len(other) == 1
    assert mli[0].product_id == "mli"
    assert other[0].product_id == "other"


def test_list_active_filters_by_candidate(store: DriftSignalStore) -> None:
    store.append(_signal(candidate_id="model-a"))
    store.append(_signal(candidate_id="model-b"))

    a = store.list_active(product_id="mli", candidate_id="model-a")
    b = store.list_active(product_id="mli", candidate_id="model-b")

    assert len(a) == 1
    assert len(b) == 1
    assert a[0].candidate_id == "model-a"
    assert b[0].candidate_id == "model-b"


def test_list_active_returns_newest_first(store: DriftSignalStore) -> None:
    older = _signal(detected_at=datetime(2026, 6, 9, 10, 0, tzinfo=timezone.utc))
    newer = _signal(detected_at=datetime(2026, 6, 9, 12, 0, tzinfo=timezone.utc))

    store.append(older)
    store.append(newer)

    active = store.list_active(product_id="mli", candidate_id="kimi-k2-6")

    assert active[0].detected_at > active[1].detected_at


# ---------------------------------------------------------------------------
# acknowledge
# ---------------------------------------------------------------------------


def test_acknowledge_removes_signal_from_active_list(store: DriftSignalStore) -> None:
    signal_id = store.append(_signal())

    store.acknowledge(signal_id)

    assert store.list_active(product_id="mli", candidate_id="kimi-k2-6") == []


def test_acknowledge_only_removes_the_targeted_signal(store: DriftSignalStore) -> None:
    id1 = store.append(_signal())
    id2 = store.append(_signal())  # noqa: F841 — kept to confirm it stays active

    store.acknowledge(id1)

    active = store.list_active(product_id="mli", candidate_id="kimi-k2-6")
    assert len(active) == 1


def test_acknowledge_is_a_no_op_for_unknown_id(store: DriftSignalStore) -> None:
    store.append(_signal())

    store.acknowledge("does-not-exist")  # must not raise

    assert len(store.list_active(product_id="mli", candidate_id="kimi-k2-6")) == 1


def test_acknowledge_is_idempotent(store: DriftSignalStore) -> None:
    signal_id = store.append(_signal())
    store.acknowledge(signal_id)

    store.acknowledge(signal_id)  # second call must not raise

    assert store.list_active(product_id="mli", candidate_id="kimi-k2-6") == []


# ---------------------------------------------------------------------------
# Durability — survives a fresh store instance against the same DB file
# ---------------------------------------------------------------------------


def test_signal_survives_fresh_store_instance(tmp_path: Path) -> None:
    db = tmp_path / "mmfp.db"
    signal = _signal()

    DriftSignalStore(db).append(signal)

    active = DriftSignalStore(db).list_active(product_id="mli", candidate_id="kimi-k2-6")
    assert len(active) == 1
    assert active[0] == signal


def test_acknowledge_survives_fresh_store_instance(tmp_path: Path) -> None:
    db = tmp_path / "mmfp.db"

    signal_id = DriftSignalStore(db).append(_signal())
    DriftSignalStore(db).acknowledge(signal_id)

    active = DriftSignalStore(db).list_active(product_id="mli", candidate_id="kimi-k2-6")
    assert active == []


# ---------------------------------------------------------------------------
# Schema / migration
# ---------------------------------------------------------------------------


def test_schema_applies_idempotently(tmp_path: Path) -> None:
    db = tmp_path / "mmfp.db"
    store_a = DriftSignalStore(db)
    store_a.append(_signal())

    store_b = DriftSignalStore(db)
    active = store_b.list_active(product_id="mli", candidate_id="kimi-k2-6")
    assert len(active) == 1


def test_schema_creates_parent_directory(tmp_path: Path) -> None:
    db = tmp_path / "nested" / "more" / "mmfp.db"
    DriftSignalStore(db).append(_signal())
    assert db.exists()


# ---------------------------------------------------------------------------
# Round-trip fidelity
# ---------------------------------------------------------------------------


def test_decimal_fields_round_trip(store: DriftSignalStore) -> None:
    signal = _signal(
        baseline_score=Decimal("79.500"),
        observed_score=Decimal("49.750"),
        delta=Decimal("-29.750"),
    )
    store.append(signal)

    active = store.list_active(product_id="mli", candidate_id="kimi-k2-6")

    assert active[0].baseline_score == Decimal("79.500")
    assert active[0].observed_score == Decimal("49.750")
    assert active[0].delta == Decimal("-29.750")


def test_datetime_round_trip_preserves_microseconds(store: DriftSignalStore) -> None:
    ts = datetime(2026, 6, 9, 12, 0, 0, 123456, tzinfo=timezone.utc)
    signal = _signal(detected_at=ts)
    store.append(signal)

    active = store.list_active(product_id="mli", candidate_id="kimi-k2-6")

    assert active[0].detected_at == ts
