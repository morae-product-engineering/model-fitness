"""Unit tests for the per-tier candidate status store (MLI-202).

Covers get/set lifecycle, optimistic-concurrency conflict, per-key isolation,
and the fail-loud backend selection (deployed-but-unconfigured → error).
Imports are deferred into test bodies per CLAUDE.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mmfp.models.candidate import CandidateStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _disk_store(tmp_path: Path, *, clock=None):
    from mmfp.persistence.blob_seam import DiskBlobSeam
    from mmfp.persistence.candidate_status import CandidateStatusStore

    return CandidateStatusStore(DiskBlobSeam(tmp_path / "status"), clock=clock)


# ---------------------------------------------------------------------------
# get — absent key
# ---------------------------------------------------------------------------


def test_get_returns_none_when_no_record_stored(tmp_path: Path) -> None:
    """No record written → get returns None (caller falls back to seed status)."""
    store = _disk_store(tmp_path)
    result = store.get(product="mli", tier_id="tier_1", candidate="gpt-4o")
    assert result is None


# ---------------------------------------------------------------------------
# set → get lifecycle
# ---------------------------------------------------------------------------


def test_set_writes_version_1_on_first_call(tmp_path: Path) -> None:
    store = _disk_store(tmp_path)
    record = store.set(
        product="mli",
        tier_id="tier_1",
        candidate="gpt-4o",
        status=CandidateStatus.APPROVED_PRIMARY,
        expected_version=0,
    )
    assert record.version == 1
    assert record.status == CandidateStatus.APPROVED_PRIMARY
    assert record.product == "mli"
    assert record.tier_id == "tier_1"
    assert record.candidate_deployment == "gpt-4o"
    assert record.updated_at.tzinfo is not None


def test_set_writes_version_2_on_second_call(tmp_path: Path) -> None:
    store = _disk_store(tmp_path)
    store.set(
        product="mli",
        tier_id="tier_1",
        candidate="gpt-4o",
        status=CandidateStatus.APPROVED_PRIMARY,
        expected_version=0,
    )
    record2 = store.set(
        product="mli",
        tier_id="tier_1",
        candidate="gpt-4o",
        status=CandidateStatus.REJECTED,
        expected_version=1,
    )
    assert record2.version == 2
    assert record2.status == CandidateStatus.REJECTED

    # get reflects the latest write
    fetched = store.get(product="mli", tier_id="tier_1", candidate="gpt-4o")
    assert fetched is not None
    assert fetched.version == 2
    assert fetched.status == CandidateStatus.REJECTED


# ---------------------------------------------------------------------------
# Optimistic-concurrency conflict
# ---------------------------------------------------------------------------


def test_set_with_stale_expected_version_raises_conflict(tmp_path: Path) -> None:
    from mmfp.persistence.candidate_status import CandidateStatusVersionConflict

    store = _disk_store(tmp_path)
    store.set(
        product="mli",
        tier_id="tier_1",
        candidate="gpt-4o",
        status=CandidateStatus.APPROVED_PRIMARY,
        expected_version=0,
    )
    # Caller still thinks version=0 (stale) — should conflict
    with pytest.raises(CandidateStatusVersionConflict) as exc_info:
        store.set(
            product="mli",
            tier_id="tier_1",
            candidate="gpt-4o",
            status=CandidateStatus.REJECTED,
            expected_version=0,
        )
    err = exc_info.value
    assert err.expected == 0
    assert err.actual == 1


def test_conflict_on_absent_record_when_expected_version_nonzero(tmp_path: Path) -> None:
    """Caller expects version=1 but no record exists (actual=0) → conflict."""
    from mmfp.persistence.candidate_status import CandidateStatusVersionConflict

    store = _disk_store(tmp_path)
    with pytest.raises(CandidateStatusVersionConflict) as exc_info:
        store.set(
            product="mli",
            tier_id="tier_1",
            candidate="gpt-4o",
            status=CandidateStatus.APPROVED_PRIMARY,
            expected_version=1,  # wrong — no record exists (version 0)
        )
    err = exc_info.value
    assert err.expected == 1
    assert err.actual == 0


# ---------------------------------------------------------------------------
# Per-key isolation
# ---------------------------------------------------------------------------


def test_writing_one_tier_leaves_another_absent(tmp_path: Path) -> None:
    """Writing (tier_2, gpt-4o) does not affect (tier_1, gpt-4o)."""
    store = _disk_store(tmp_path)
    store.set(
        product="mli",
        tier_id="tier_2",
        candidate="gpt-4o",
        status=CandidateStatus.APPROVED_PRIMARY,
        expected_version=0,
    )
    assert store.get(product="mli", tier_id="tier_1", candidate="gpt-4o") is None


def test_writing_one_candidate_leaves_another_absent(tmp_path: Path) -> None:
    """Writing (tier_1, gpt-4o) does not affect (tier_1, kimi-k2-6)."""
    store = _disk_store(tmp_path)
    store.set(
        product="mli",
        tier_id="tier_1",
        candidate="gpt-4o",
        status=CandidateStatus.APPROVED_PRIMARY,
        expected_version=0,
    )
    assert store.get(product="mli", tier_id="tier_1", candidate="kimi-k2-6") is None


def test_per_product_isolation(tmp_path: Path) -> None:
    """Different products share no status records."""
    store = _disk_store(tmp_path)
    store.set(
        product="mli",
        tier_id="tier_1",
        candidate="gpt-4o",
        status=CandidateStatus.APPROVED_PRIMARY,
        expected_version=0,
    )
    assert store.get(product="other", tier_id="tier_1", candidate="gpt-4o") is None


# ---------------------------------------------------------------------------
# Backend selection — fail loud, never silent ephemeral disk
# ---------------------------------------------------------------------------


def test_get_candidate_status_store_uses_disk_locally(tmp_path: Path, monkeypatch) -> None:
    from mmfp.persistence.blob_seam import DiskBlobSeam
    from mmfp.persistence.candidate_status import (
        ACCOUNT_URL_ENV,
        CONTAINER_ENV,
        DEPLOY_MARKER_ENV,
        LOCAL_DIR_ENV,
        get_candidate_status_store,
    )

    monkeypatch.delenv(ACCOUNT_URL_ENV, raising=False)
    monkeypatch.delenv(CONTAINER_ENV, raising=False)
    monkeypatch.delenv(DEPLOY_MARKER_ENV, raising=False)
    monkeypatch.setenv(LOCAL_DIR_ENV, str(tmp_path / "status"))

    store = get_candidate_status_store()
    assert isinstance(store._seam, DiskBlobSeam)


def test_get_candidate_status_store_fails_loud_when_deployed_without_durable_config(
    monkeypatch,
) -> None:
    """The MLI-365 footgun, refused for the status store: deployed env without
    blob config raises CandidateStatusConfigError, never silently uses disk."""
    from mmfp.persistence.candidate_status import (
        ACCOUNT_URL_ENV,
        CONTAINER_ENV,
        DEPLOY_MARKER_ENV,
        CandidateStatusConfigError,
        get_candidate_status_store,
    )

    monkeypatch.delenv(ACCOUNT_URL_ENV, raising=False)
    monkeypatch.delenv(CONTAINER_ENV, raising=False)
    monkeypatch.setenv(DEPLOY_MARKER_ENV, "ca-mmfp-api-dev")

    with pytest.raises(CandidateStatusConfigError, match="not configured"):
        get_candidate_status_store()


def test_get_candidate_status_store_selects_blob_when_configured(monkeypatch) -> None:
    import azure.identity as identity_mod
    import azure.storage.blob as blob_mod

    from mmfp.persistence.blob_seam import AzureBlobSeam
    from mmfp.persistence.candidate_status import (
        ACCOUNT_URL_ENV,
        CONTAINER_ENV,
        get_candidate_status_store,
    )

    monkeypatch.setattr(blob_mod, "ContainerClient", lambda **kwargs: object())
    monkeypatch.setattr(identity_mod, "DefaultAzureCredential", lambda *a, **k: object())
    monkeypatch.setenv(ACCOUNT_URL_ENV, "https://stmmfpdevuks.blob.core.windows.net")
    monkeypatch.setenv(CONTAINER_ENV, "mmfp-audit")

    store = get_candidate_status_store()
    assert isinstance(store._seam, AzureBlobSeam)
