"""Unit tests for the candidate-status audit log (MLI-201).

Covers the append-only contract, the hash-chain tamper-evidence, the bounded
prefix-scan access pattern that re-frames the old EXPLAIN-QUERY-PLAN AC, and the
fail-loud backend selection. The disk backend runs against `tmp_path`; the blob
backend uses a fake in-memory container client (no real Azure), the same
technique as the MLI-365 rubric-store tests.

Imports of `audit_log` / `blob_seam` are deferred into test bodies per CLAUDE.md.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from mmfp.models.audit import PLACEHOLDER_ACTOR, AuditAction, StatusChange
from mmfp.models.candidate import CandidateStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _change(
    *,
    action: AuditAction = AuditAction.PROMOTE_PRIMARY,
    tier_id: str = "tier_1",
    candidate: str = "gpt-4o",
    previous: CandidateStatus = CandidateStatus.UNDER_EVALUATION,
    new: CandidateStatus = CandidateStatus.APPROVED_PRIMARY,
    rationale: str = "Best synthesis quality on R1 dataset",
    rubric_version: str = "v0.1",
    run_id: str = "b2ae2a68",
) -> StatusChange:
    return StatusChange(
        action=action,
        tier_id=tier_id,
        candidate_deployment=candidate,
        previous_status=previous,
        new_status=new,
        rationale=rationale,
        rubric_version_at_time=rubric_version,
        run_id_at_time=run_id,
    )


def _disk_repo(tmp_path: Path, *, clock=None):
    from mmfp.persistence.audit_log import AuditLogRepository
    from mmfp.persistence.blob_seam import DiskBlobSeam

    return AuditLogRepository(DiskBlobSeam(tmp_path / "audit"), clock=clock)


class _RecordingSeam:
    """Wraps a seam and records the prefixes passed to `list_names`, so a test
    can assert a query issued bounded prefixes rather than a product-wide scan."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.list_prefixes: list[str] = []

    def read(self, name: str):
        return self._inner.read(name)

    def write(self, name: str, data: bytes, *, overwrite: bool) -> None:
        self._inner.write(name, data, overwrite=overwrite)

    def list_names(self, prefix: str):
        self.list_prefixes.append(prefix)
        return self._inner.list_names(prefix)


# ---------------------------------------------------------------------------
# append + chain
# ---------------------------------------------------------------------------


def test_append_assigns_server_fields_and_genesis_chain(tmp_path: Path) -> None:
    repo = _disk_repo(tmp_path)
    entry = repo.append(_change(), product="mli")

    assert entry.id  # server-assigned
    assert entry.sequence == 0
    assert entry.timestamp.tzinfo is not None
    assert entry.prev_hash == "0" * 64  # genesis
    assert entry.entry_hash and entry.entry_hash != "0" * 64
    assert entry.actor == PLACEHOLDER_ACTOR  # one reconciled placeholder


def test_append_chains_each_entry_to_its_predecessor(tmp_path: Path) -> None:
    repo = _disk_repo(tmp_path)
    first = repo.append(_change(candidate="gpt-4o"), product="mli")
    second = repo.append(_change(candidate="kimi-k2-6"), product="mli")

    assert second.sequence == first.sequence + 1
    assert second.prev_hash == first.entry_hash


def test_sequence_breaks_ties_when_timestamps_collide(tmp_path: Path) -> None:
    """`timestamp` is server-side; if two entries share a millisecond, the
    monotonic `sequence` is the tie-breaker that keeps ordering total."""
    frozen = datetime(2026, 6, 2, 12, 0, 0, tzinfo=timezone.utc)
    repo = _disk_repo(tmp_path, clock=lambda: frozen)

    a = repo.append(_change(candidate="gpt-4o"), product="mli")
    b = repo.append(_change(candidate="kimi-k2-6"), product="mli")

    assert a.timestamp == b.timestamp
    assert (a.sequence, b.sequence) == (0, 1)
    listed = repo.list(product="mli", newest_first=False)
    assert [e.sequence for e in listed] == [0, 1]


def test_products_have_independent_chains(tmp_path: Path) -> None:
    repo = _disk_repo(tmp_path)
    repo.append(_change(), product="mli")
    other = repo.append(_change(), product="other")
    assert other.sequence == 0
    assert other.prev_hash == "0" * 64


# ---------------------------------------------------------------------------
# list — filters and ordering
# ---------------------------------------------------------------------------


def test_list_newest_first_by_default(tmp_path: Path) -> None:
    base = datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc)
    stamps = iter([base, base.replace(minute=1), base.replace(minute=2)])
    repo = _disk_repo(tmp_path, clock=lambda: next(stamps))
    for cand in ("a", "b", "c"):
        repo.append(_change(candidate=cand), product="mli")

    listed = repo.list(product="mli")
    assert [e.candidate_deployment for e in listed] == ["c", "b", "a"]


def test_list_filters_by_candidate_and_tier(tmp_path: Path) -> None:
    repo = _disk_repo(tmp_path)
    repo.append(_change(tier_id="tier_1", candidate="gpt-4o"), product="mli")
    repo.append(_change(tier_id="tier_2", candidate="gpt-4o"), product="mli")
    repo.append(_change(tier_id="tier_1", candidate="kimi-k2-6"), product="mli")

    by_candidate = repo.list(product="mli", candidate="gpt-4o")
    assert {e.tier_id for e in by_candidate} == {"tier_1", "tier_2"}
    assert all(e.candidate_deployment == "gpt-4o" for e in by_candidate)

    by_tier = repo.list(product="mli", tier_id="tier_1")
    assert {e.candidate_deployment for e in by_tier} == {"gpt-4o", "kimi-k2-6"}

    both = repo.list(product="mli", tier_id="tier_2", candidate="gpt-4o")
    assert len(both) == 1


def test_list_respects_limit(tmp_path: Path) -> None:
    base = datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc)
    stamps = iter([base.replace(minute=i) for i in range(5)])
    repo = _disk_repo(tmp_path, clock=lambda: next(stamps))
    for i in range(5):
        repo.append(_change(candidate=f"c{i}"), product="mli")

    top = repo.list(product="mli", limit=2)
    assert [e.candidate_deployment for e in top] == ["c4", "c3"]


def test_list_rejects_negative_limit(tmp_path: Path) -> None:
    repo = _disk_repo(tmp_path)
    with pytest.raises(ValueError, match="limit"):
        repo.list(product="mli", limit=-1)


# ---------------------------------------------------------------------------
# Access pattern — the EXPLAIN-QUERY-PLAN re-frame (MLI-201)
# ---------------------------------------------------------------------------


def test_candidate_query_is_a_bounded_prefix_scan_not_list_everything(
    tmp_path: Path,
) -> None:
    """The dominant History query (filter by candidate) must issue
    candidate-scoped prefixes — at most one per tier — never the product root.
    This is the access-pattern assertion that replaces `EXPLAIN QUERY PLAN`."""
    from mmfp.persistence.audit_log import AuditLogRepository
    from mmfp.persistence.blob_seam import DiskBlobSeam

    recording = _RecordingSeam(DiskBlobSeam(tmp_path / "audit"))
    repo = AuditLogRepository(recording)
    repo.append(_change(tier_id="tier_1", candidate="gpt-4o"), product="mli")

    recording.list_prefixes.clear()
    repo.list(product="mli", candidate="gpt-4o")

    product_root = "mli/promotion-audit/"
    assert product_root not in recording.list_prefixes
    assert recording.list_prefixes == [
        "mli/promotion-audit/tier_1/gpt-4o/",
        "mli/promotion-audit/tier_2/gpt-4o/",
        "mli/promotion-audit/tier_3/gpt-4o/",
    ]


def test_tier_query_is_a_single_bounded_prefix(tmp_path: Path) -> None:
    from mmfp.persistence.audit_log import AuditLogRepository
    from mmfp.persistence.blob_seam import DiskBlobSeam

    recording = _RecordingSeam(DiskBlobSeam(tmp_path / "audit"))
    repo = AuditLogRepository(recording)
    repo.append(_change(tier_id="tier_1", candidate="gpt-4o"), product="mli")

    recording.list_prefixes.clear()
    repo.list(product="mli", tier_id="tier_1")

    assert recording.list_prefixes == ["mli/promotion-audit/tier_1/"]


# ---------------------------------------------------------------------------
# Append-only / immutability
# ---------------------------------------------------------------------------


def test_repository_exposes_no_update_or_delete(tmp_path: Path) -> None:
    """Append-only by API surface: there is no mutating operation to call."""
    repo = _disk_repo(tmp_path)
    public = {name for name in dir(repo) if not name.startswith("_")}
    assert public == {"append", "list", "verify_chain"}


def test_entry_blobs_are_written_immutably(tmp_path: Path) -> None:
    """Entry blobs use overwrite=False — re-writing an existing name is a clear
    error, never a silent overwrite of history."""
    from mmfp.persistence.blob_seam import BlobAlreadyExists, DiskBlobSeam

    seam = DiskBlobSeam(tmp_path / "audit")
    seam.write("mli/promotion-audit/tier_1/gpt-4o/x.json", b"{}", overwrite=False)
    with pytest.raises(BlobAlreadyExists):
        seam.write("mli/promotion-audit/tier_1/gpt-4o/x.json", b"{}", overwrite=False)


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_idempotent_reappend_does_not_double_write(tmp_path: Path) -> None:
    repo = _disk_repo(tmp_path)
    first = repo.append(_change(), product="mli", idempotency_key="promo-001")
    again = repo.append(_change(), product="mli", idempotency_key="promo-001")

    assert again.id == first.id
    assert again.sequence == first.sequence
    # Exactly one entry persisted — the retry was a no-op.
    assert len(repo.list(product="mli")) == 1


def test_distinct_idempotency_keys_each_write(tmp_path: Path) -> None:
    repo = _disk_repo(tmp_path)
    repo.append(_change(), product="mli", idempotency_key="k1")
    repo.append(_change(candidate="kimi-k2-6"), product="mli", idempotency_key="k2")
    assert len(repo.list(product="mli")) == 2


# ---------------------------------------------------------------------------
# Hash-chain verification
# ---------------------------------------------------------------------------


def test_verify_chain_passes_for_an_untouched_log(tmp_path: Path) -> None:
    repo = _disk_repo(tmp_path)
    for cand in ("a", "b", "c"):
        repo.append(_change(candidate=cand), product="mli")

    result = repo.verify_chain(product="mli")
    assert result.ok is True
    assert result.entries_verified == 3
    assert result.broken_at_sequence is None


def test_verify_chain_passes_on_empty_log(tmp_path: Path) -> None:
    repo = _disk_repo(tmp_path)
    result = repo.verify_chain(product="mli")
    assert result.ok is True
    assert result.entries_verified == 0


def test_verify_chain_detects_a_tampered_record(tmp_path: Path) -> None:
    """Rewrite a stored entry's rationale behind the repository's back; the
    recomputed content hash no longer matches and the chain fails at that
    record."""
    import json

    from mmfp.persistence.blob_seam import DiskBlobSeam

    seam = DiskBlobSeam(tmp_path / "audit")
    from mmfp.persistence.audit_log import AuditLogRepository

    repo = AuditLogRepository(seam)
    repo.append(_change(candidate="a"), product="mli")
    target = repo.append(_change(candidate="b"), product="mli")
    repo.append(_change(candidate="c"), product="mli")

    # Locate the middle entry's blob and corrupt its rationale, keeping the
    # stored entry_hash — exactly what an after-the-fact editor would do.
    names = seam.list_names("mli/promotion-audit/")
    target_name = next(n for n in names if target.id in n)
    raw = json.loads(seam.read(target_name))
    raw["rationale"] = "tampered after the fact"
    seam.write(target_name, json.dumps(raw).encode("utf-8"), overwrite=True)

    result = repo.verify_chain(product="mli")
    assert result.ok is False
    assert result.broken_at_sequence == target.sequence
    assert "content" in (result.detail or "")


# ---------------------------------------------------------------------------
# Backend selection — fail loud, never silent ephemeral disk
# ---------------------------------------------------------------------------


def test_get_repository_uses_disk_locally(tmp_path: Path, monkeypatch) -> None:
    from mmfp.persistence import audit_log
    from mmfp.persistence.blob_seam import DiskBlobSeam

    monkeypatch.delenv(audit_log.ACCOUNT_URL_ENV, raising=False)
    monkeypatch.delenv(audit_log.CONTAINER_ENV, raising=False)
    monkeypatch.delenv(audit_log.DEPLOY_MARKER_ENV, raising=False)
    monkeypatch.setenv(audit_log.LOCAL_DIR_ENV, str(tmp_path / "audit"))

    repo = audit_log.get_audit_log_repository()
    assert isinstance(repo._seam, DiskBlobSeam)


def test_get_repository_fails_loud_when_deployed_without_durable_config(
    monkeypatch,
) -> None:
    """The MLI-365 footgun, refused: in the deployed env (CONTAINER_APP_NAME
    set) a missing blob config is a hard error, not a silent ephemeral disk."""
    from mmfp.persistence import audit_log

    monkeypatch.delenv(audit_log.ACCOUNT_URL_ENV, raising=False)
    monkeypatch.delenv(audit_log.CONTAINER_ENV, raising=False)
    monkeypatch.setenv(audit_log.DEPLOY_MARKER_ENV, "ca-mmfp-api-dev")

    with pytest.raises(audit_log.AuditLogConfigError, match="not configured"):
        audit_log.get_audit_log_repository()


def test_get_repository_selects_blob_when_configured(monkeypatch) -> None:
    # Stub the Azure constructions so no SDK auth/network happens.
    import azure.identity as identity_mod
    import azure.storage.blob as blob_mod

    from mmfp.persistence import audit_log
    from mmfp.persistence.blob_seam import AzureBlobSeam

    monkeypatch.setattr(blob_mod, "ContainerClient", lambda **kwargs: object())
    monkeypatch.setattr(identity_mod, "DefaultAzureCredential", lambda *a, **k: object())
    monkeypatch.setenv(
        audit_log.ACCOUNT_URL_ENV, "https://stmmfpdevuks.blob.core.windows.net"
    )
    monkeypatch.setenv(audit_log.CONTAINER_ENV, "mmfp-audit")

    repo = audit_log.get_audit_log_repository()
    assert isinstance(repo._seam, AzureBlobSeam)


# ---------------------------------------------------------------------------
# Blob backend — durability across a revision restart (fake container client)
# ---------------------------------------------------------------------------


class _FakeDownload:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def readall(self) -> bytes:
        return self._data


class _FakeBlobProps:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeContainerClient:
    """In-memory ContainerClient. Shared across constructions so a 'restart'
    (new seam/repo) sees prior writes — the durability property under test."""

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

    def list_blobs(self, name_starts_with: str = ""):
        return [_FakeBlobProps(n) for n in self.blobs if n.startswith(name_starts_with)]


@pytest.fixture
def fake_blob(monkeypatch):
    import azure.identity as identity_mod
    import azure.storage.blob as blob_mod

    fake = _FakeContainerClient()
    monkeypatch.setattr(blob_mod, "ContainerClient", lambda **kwargs: fake)
    monkeypatch.setattr(identity_mod, "DefaultAzureCredential", lambda *a, **k: object())
    return fake


def _blob_repo():
    from mmfp.persistence.audit_log import AuditLogRepository
    from mmfp.persistence.blob_seam import AzureBlobSeam

    return AuditLogRepository(
        AzureBlobSeam(
            account_url="https://stmmfpdevuks.blob.core.windows.net",
            container="mmfp-audit",
        )
    )


def test_blob_append_survives_restart_and_chain_verifies(fake_blob) -> None:
    repo = _blob_repo()
    repo.append(_change(candidate="gpt-4o"), product="mli")
    repo.append(_change(candidate="kimi-k2-6"), product="mli")

    # Simulate a revision restart: a brand-new repo/seam over the same backing
    # blobs. The audit trail is still there and still verifies.
    restarted = _blob_repo()
    listed = restarted.list(product="mli")
    assert {e.candidate_deployment for e in listed} == {"gpt-4o", "kimi-k2-6"}
    assert restarted.verify_chain(product="mli").ok is True


def test_blob_entries_land_under_the_dedicated_container_prefix(fake_blob) -> None:
    """Records live on the dedicated audit container under the product /
    promotion-audit / tier / candidate prefix — distinct from the rubric
    store's mmfp-seed layout."""
    repo = _blob_repo()
    repo.append(_change(tier_id="tier_1", candidate="gpt-4o"), product="mli")

    keys = list(fake_blob.blobs)
    assert any(
        k.startswith("mli/promotion-audit/tier_1/gpt-4o/") and k.endswith(".json")
        for k in keys
    )
