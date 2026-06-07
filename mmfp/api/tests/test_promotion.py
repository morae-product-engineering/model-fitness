"""Tests for promote/reject/audit-log endpoints (MLI-202).

Uses FastAPI TestClient with dependency_overrides, injecting:
  - a real SQLite repo (tmp_path) with at least one MatrixRun
  - an in-memory candidate list (two candidates: one tier_1+tier_2, one tier_2)
  - tmp-dir DiskBlobSeam stores for both audit_log and candidate_status

Style follows test_scoreboard.py and test_rubric_write.py.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mmfp.models.candidate import (
    Candidate,
    CandidateBinding,
    CandidateFamily,
    CandidateStatus,
)
from mmfp.models.matrix_run import EvaluatorScore, MatrixRun, MatrixRunResult, SourceField
from mmfp.persistence import MatrixRunRepository

# Deferred imports of new modules per CLAUDE.md — keeps collection clean.

_STARTED_AT = datetime(2026, 6, 2, 12, 0, 0, tzinfo=timezone.utc)
_COMPLETED_AT = datetime(2026, 6, 2, 12, 0, 30, tzinfo=timezone.utc)

# Two candidates used across most tests:
#   MINI: gpt-4.1-mini, tiers [tier_1, tier_2]  (cross-tier candidate)
#   GPT4O: gpt-4o, tiers [tier_2, tier_3]
_MINI_DEPLOYMENT = "gpt-4.1-mini"
_GPT4O_DEPLOYMENT = "gpt-4o"


# ---------------------------------------------------------------------------
# Helpers — candidate / run builders
# ---------------------------------------------------------------------------


def _score(
    *,
    dimension_id: str = "t1.accuracy",
    normalized_score: Decimal = Decimal("75.000"),
) -> EvaluatorScore:
    return EvaluatorScore(
        dimension_id=dimension_id,
        evaluator_id="exact_match",
        raw_value="A",
        normalized_score=normalized_score,
        passed=True,
        source_field=SourceField.CONTENT,
        latency_ms=10,
        cost_usd=Decimal("0.0001"),
        reason="match",
    )


def _result(
    *,
    tier_id: str = "tier_1",
    candidate_id: str = "gpt-4-1-mini",
) -> MatrixRunResult:
    return MatrixRunResult(
        tier_id=tier_id,
        candidate_id=candidate_id,
        dataset_id="ds-t1",
        example_id="ex1",
        score=_score(),
    )


def _run(*, run_id: str = "run-abc") -> MatrixRun:
    return MatrixRun(
        id=run_id,
        rubric_version="v0.1",
        started_at=_STARTED_AT,
        completed_at=_COMPLETED_AT,
        results=[
            _result(tier_id="tier_1", candidate_id="gpt-4-1-mini"),
            _result(tier_id="tier_2", candidate_id="gpt-4-1-mini"),
            _result(tier_id="tier_2", candidate_id="gpt-4o"),
        ],
    )


def _mini_candidate() -> Candidate:
    return Candidate(
        id="gpt-4-1-mini",
        display_name="GPT-4.1 mini",
        family=CandidateFamily.CHAT,
        max_tokens=1024,
        context_window=1_000_000,
        tiers=["tier_1", "tier_2"],
        binding=CandidateBinding(
            provider="azure_foundry",
            endpoint="https://example.cognitiveservices.azure.com",
            deployment=_MINI_DEPLOYMENT,
            api_version="2024-12-01-preview",
            auth_method="api_key_header",
            key_vault_secret_name="sk-fake-test-key-xxx",
        ),
    )


def _gpt4o_candidate() -> Candidate:
    return Candidate(
        id="gpt-4o",
        display_name="GPT-4o",
        family=CandidateFamily.CHAT,
        max_tokens=1024,
        context_window=128_000,
        tiers=["tier_2", "tier_3"],
        binding=CandidateBinding(
            provider="azure_foundry",
            endpoint="https://example.cognitiveservices.azure.com",
            deployment=_GPT4O_DEPLOYMENT,
            api_version="2024-12-01-preview",
            auth_method="api_key_header",
            key_vault_secret_name="sk-fake-test-key-xxx",
        ),
    )


# ---------------------------------------------------------------------------
# Fixture: TestClient with overrides
# ---------------------------------------------------------------------------


def _make_client(
    tmp_path: Path,
    *,
    candidates: list[Candidate] | None = None,
    run: MatrixRun | None = None,
    product: str = "mli",
    raise_server_exceptions: bool = True,
    extra_overrides: dict | None = None,
) -> tuple[TestClient, MatrixRunRepository, Any, Any]:
    """Build a TestClient with all promotion-endpoint dependencies overridden.

    Returns (client, repo, audit_repo, status_store).
    """
    from mmfp.api import promotion, scoreboard
    from mmfp.api.main import app
    from mmfp.persistence.audit_log import AuditLogRepository
    from mmfp.persistence.blob_seam import DiskBlobSeam
    from mmfp.persistence.candidate_status import CandidateStatusStore

    if candidates is None:
        candidates = [_mini_candidate(), _gpt4o_candidate()]

    repo = MatrixRunRepository(tmp_path / "test.db")
    if run is not None:
        repo.save(run, product=product)

    audit_repo = AuditLogRepository(DiskBlobSeam(tmp_path / "audit"))
    status_store = CandidateStatusStore(DiskBlobSeam(tmp_path / "status"))

    def _override_repo():
        return repo

    def _override_loader() -> Callable[[str], list[Candidate]]:
        def _load(p: str) -> list[Candidate]:
            if p != product:
                raise FileNotFoundError(f"no slate for {p}")
            return candidates

        return _load

    def _override_audit():
        return audit_repo

    def _override_status():
        return status_store

    app.dependency_overrides[scoreboard.get_repository] = _override_repo
    app.dependency_overrides[scoreboard.get_candidate_loader] = _override_loader
    app.dependency_overrides[promotion.get_audit_log_repository] = _override_audit
    app.dependency_overrides[promotion.get_candidate_status_store] = _override_status
    # Scoreboard also needs the status store override so the overlay test works
    app.dependency_overrides[scoreboard.get_candidate_status_store] = _override_status

    if extra_overrides:
        app.dependency_overrides.update(extra_overrides)

    client = TestClient(app, raise_server_exceptions=raise_server_exceptions)
    return client, repo, audit_repo, status_store


@pytest.fixture(autouse=True)
def _clear_overrides():
    """Prevent dependency_overrides leaking between tests."""
    yield
    from mmfp.api.main import app

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Promote primary
# ---------------------------------------------------------------------------


def test_promote_primary_returns_200_with_correct_fields(tmp_path: Path) -> None:
    client, _, audit_repo, status_store = _make_client(tmp_path, run=_run())

    resp = client.post(
        f"/api/products/mli/candidates/{_MINI_DEPLOYMENT}/promote",
        json={"tier_id": "tier_1", "role": "primary", "rationale": "Best accuracy"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["product"] == "mli"
    assert data["tier_id"] == "tier_1"
    assert data["candidate_deployment"] == _MINI_DEPLOYMENT
    assert data["previous_status"] == "under_evaluation"
    assert data["new_status"] == "approved_primary"
    assert data["version"] == 1
    assert data["audit_ref"]  # non-empty UUID hex
    assert isinstance(data["audit_sequence"], int)

    # Status store updated
    rec = status_store.get(product="mli", tier_id="tier_1", candidate=_MINI_DEPLOYMENT)
    assert rec is not None
    assert rec.status == CandidateStatus.APPROVED_PRIMARY
    assert rec.version == 1

    # Audit entry present
    entries = audit_repo.list(product="mli")
    assert len(entries) == 1
    assert entries[0].action.value == "promote_primary"
    assert entries[0].new_status == CandidateStatus.APPROVED_PRIMARY


# ---------------------------------------------------------------------------
# Promote fallback
# ---------------------------------------------------------------------------


def test_promote_fallback_returns_approved_fallback(tmp_path: Path) -> None:
    client, _, audit_repo, _ = _make_client(tmp_path, run=_run())

    resp = client.post(
        f"/api/products/mli/candidates/{_MINI_DEPLOYMENT}/promote",
        json={"tier_id": "tier_2", "role": "fallback", "rationale": "Good fallback"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["new_status"] == "approved_fallback"

    entries = audit_repo.list(product="mli")
    assert entries[0].action.value == "promote_fallback"
    assert entries[0].new_status == CandidateStatus.APPROVED_FALLBACK


# ---------------------------------------------------------------------------
# Reject
# ---------------------------------------------------------------------------


def test_reject_returns_rejected_status(tmp_path: Path) -> None:
    client, _, audit_repo, status_store = _make_client(tmp_path, run=_run())

    resp = client.post(
        f"/api/products/mli/candidates/{_GPT4O_DEPLOYMENT}/reject",
        json={"tier_id": "tier_2", "rationale": "Fails on structured output"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["new_status"] == "rejected"

    rec = status_store.get(product="mli", tier_id="tier_2", candidate=_GPT4O_DEPLOYMENT)
    assert rec is not None
    assert rec.status == CandidateStatus.REJECTED

    entries = audit_repo.list(product="mli")
    assert entries[0].action.value == "reject"


# ---------------------------------------------------------------------------
# Empty/missing rationale → 422 with CORS header
# ---------------------------------------------------------------------------


def test_empty_rationale_returns_422_with_cors_header(tmp_path: Path) -> None:
    """min_length=1 on rationale → FastAPI 422 with a ``detail`` list.

    Also confirms the CORS header is present — the MLI-365 lesson: 422 flows
    through CORSMiddleware and gets the header.
    """
    client, _, _, _ = _make_client(tmp_path, run=_run())

    resp = client.post(
        f"/api/products/mli/candidates/{_MINI_DEPLOYMENT}/promote",
        json={"tier_id": "tier_1", "role": "primary", "rationale": ""},
        headers={"Origin": "http://localhost:3000"},
    )
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert isinstance(detail, list)
    assert any("rationale" in str(e) for e in detail)
    # CORS header present
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_missing_rationale_returns_422(tmp_path: Path) -> None:
    """Omitting rationale entirely → 422."""
    client, _, _, _ = _make_client(tmp_path, run=_run())
    resp = client.post(
        f"/api/products/mli/candidates/{_MINI_DEPLOYMENT}/promote",
        json={"tier_id": "tier_1", "role": "primary"},  # no rationale key
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Idempotency: same promote twice → TWO audit entries, stable status, v++ each time
# ---------------------------------------------------------------------------


def test_same_promote_twice_generates_two_audit_entries(tmp_path: Path) -> None:
    """Each call to promote is a fresh decision recorded as a new audit entry.
    The audit log is append-only and does NOT deduplicate by intent — a steward
    promoting the same candidate twice is two recorded decisions. Final status
    is stable (APPROVED_PRIMARY), version increments 1 → 2.
    """
    client, _, audit_repo, status_store = _make_client(tmp_path, run=_run())

    for _ in range(2):
        resp = client.post(
            f"/api/products/mli/candidates/{_MINI_DEPLOYMENT}/promote",
            json={"tier_id": "tier_1", "role": "primary", "rationale": "Still best"},
        )
        assert resp.status_code == 200, resp.text

    entries = audit_repo.list(product="mli")
    assert len(entries) == 2, "Expected two audit entries, one per call"
    assert all(e.action.value == "promote_primary" for e in entries)

    rec = status_store.get(product="mli", tier_id="tier_1", candidate=_MINI_DEPLOYMENT)
    assert rec is not None
    assert rec.status == CandidateStatus.APPROVED_PRIMARY
    assert rec.version == 2


# ---------------------------------------------------------------------------
# Audit-first: audit entry stands when status write fails
# ---------------------------------------------------------------------------


def test_status_persist_failure_returns_500_with_cors_and_audit_entry_stands(
    tmp_path: Path,
) -> None:
    """When status_store.set raises a generic Exception the endpoint returns
    500 WITH a CORS header (MLI-365 lesson). The audit entry committed before
    the failure still stands in the audit repo.
    """
    from mmfp.api import promotion as promo_module
    from mmfp.api.main import app
    from mmfp.persistence.audit_log import AuditLogRepository
    from mmfp.persistence.blob_seam import DiskBlobSeam
    from mmfp.persistence.candidate_status import CandidateStatusStore

    audit_repo = AuditLogRepository(DiskBlobSeam(tmp_path / "audit"))

    class _FailingStatusStore(CandidateStatusStore):
        def set(self, **kwargs):  # type: ignore[override]
            raise RuntimeError("blob unreachable")

    failing_store = _FailingStatusStore(DiskBlobSeam(tmp_path / "status-fail"))

    from mmfp.api import scoreboard

    repo = MatrixRunRepository(tmp_path / "test.db")
    repo.save(_run(), product="mli")

    candidates = [_mini_candidate(), _gpt4o_candidate()]

    def _override_repo():
        return repo

    def _override_loader():
        def _load(p):
            return candidates if p == "mli" else (_ for _ in ()).throw(FileNotFoundError())

        return _load

    def _override_audit():
        return audit_repo

    def _override_status():
        return failing_store

    app.dependency_overrides[scoreboard.get_repository] = _override_repo
    app.dependency_overrides[scoreboard.get_candidate_loader] = _override_loader
    app.dependency_overrides[promo_module.get_audit_log_repository] = _override_audit
    app.dependency_overrides[promo_module.get_candidate_status_store] = _override_status
    app.dependency_overrides[scoreboard.get_candidate_status_store] = _override_status

    client = TestClient(app, raise_server_exceptions=False)

    resp = client.post(
        f"/api/products/mli/candidates/{_MINI_DEPLOYMENT}/promote",
        json={"tier_id": "tier_1", "role": "primary", "rationale": "Test"},
        headers={"Origin": "http://localhost:3000"},
    )
    assert resp.status_code == 500, resp.text
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "failed to persist" in resp.json().get("detail", "")

    # Audit entry committed before the failure → stands in the audit repo
    entries = audit_repo.list(product="mli")
    assert len(entries) == 1, "Audit entry must stand even when status write fails"


def test_status_version_conflict_returns_409_with_cors_and_audit_entry_stands(
    tmp_path: Path,
) -> None:
    """When status_store.set raises CandidateStatusVersionConflict the endpoint
    returns 409 WITH a CORS header. The audit entry still stands.
    """
    from mmfp.api import promotion as promo_module
    from mmfp.api.main import app
    from mmfp.persistence.audit_log import AuditLogRepository
    from mmfp.persistence.blob_seam import DiskBlobSeam
    from mmfp.persistence.candidate_status import (
        CandidateStatusStore,
        CandidateStatusVersionConflict,
    )

    audit_repo = AuditLogRepository(DiskBlobSeam(tmp_path / "audit"))

    class _ConflictingStatusStore(CandidateStatusStore):
        def set(self, **kwargs):  # type: ignore[override]
            raise CandidateStatusVersionConflict(expected=0, actual=1)

    conflicting_store = _ConflictingStatusStore(DiskBlobSeam(tmp_path / "status-conflict"))

    from mmfp.api import scoreboard

    repo = MatrixRunRepository(tmp_path / "test.db")
    repo.save(_run(), product="mli")
    candidates = [_mini_candidate(), _gpt4o_candidate()]

    def _override_repo():
        return repo

    def _override_loader():
        def _load(p):
            return candidates if p == "mli" else (_ for _ in ()).throw(FileNotFoundError())

        return _load

    def _override_audit():
        return audit_repo

    def _override_status():
        return conflicting_store

    app.dependency_overrides[scoreboard.get_repository] = _override_repo
    app.dependency_overrides[scoreboard.get_candidate_loader] = _override_loader
    app.dependency_overrides[promo_module.get_audit_log_repository] = _override_audit
    app.dependency_overrides[promo_module.get_candidate_status_store] = _override_status
    app.dependency_overrides[scoreboard.get_candidate_status_store] = _override_status

    client = TestClient(app, raise_server_exceptions=False)

    resp = client.post(
        f"/api/products/mli/candidates/{_MINI_DEPLOYMENT}/promote",
        json={"tier_id": "tier_1", "role": "primary", "rationale": "Race test"},
        headers={"Origin": "http://localhost:3000"},
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body.get("error") == "status_version_conflict"
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"

    # Audit entry stands
    entries = audit_repo.list(product="mli")
    assert len(entries) == 1, "Audit entry must stand even on version conflict"


# ---------------------------------------------------------------------------
# Per-tier isolation
# ---------------------------------------------------------------------------


def test_promote_in_tier_2_does_not_affect_tier_1(tmp_path: Path) -> None:
    """Promoting gpt-4.1-mini in tier_2 leaves its tier_1 status at seed value
    (under_evaluation) — no cross-tier leakage.
    """
    client, _, _, status_store = _make_client(tmp_path, run=_run())

    resp = client.post(
        f"/api/products/mli/candidates/{_MINI_DEPLOYMENT}/promote",
        json={"tier_id": "tier_2", "role": "primary", "rationale": "Good at T2"},
    )
    assert resp.status_code == 200, resp.text

    # tier_2 promoted
    t2_rec = status_store.get(product="mli", tier_id="tier_2", candidate=_MINI_DEPLOYMENT)
    assert t2_rec is not None
    assert t2_rec.status == CandidateStatus.APPROVED_PRIMARY

    # tier_1 untouched (still seed = None in the status store)
    t1_rec = status_store.get(product="mli", tier_id="tier_1", candidate=_MINI_DEPLOYMENT)
    assert t1_rec is None  # no override written for tier_1

    # Scoreboard also shows under_evaluation for tier_1
    resp_sb = client.get("/api/products/mli/scoreboard")
    assert resp_sb.status_code == 200
    tiers = {t["tier_id"]: t for t in resp_sb.json()["tiers"]}
    t1_cands = tiers["tier_1"]["candidates"]
    mini_t1 = next((c for c in t1_cands if c["deployment"] == _MINI_DEPLOYMENT), None)
    if mini_t1 is not None:
        assert mini_t1["status"] == "under_evaluation"


# ---------------------------------------------------------------------------
# tier_id not in candidate.tiers → 422
# ---------------------------------------------------------------------------


def test_promote_in_tier_not_in_candidate_tiers_returns_422(tmp_path: Path) -> None:
    """gpt-4.1-mini is only in [tier_1, tier_2]; promoting it in tier_3 → 422."""
    client, _, _, _ = _make_client(tmp_path, run=_run())

    resp = client.post(
        f"/api/products/mli/candidates/{_MINI_DEPLOYMENT}/promote",
        json={"tier_id": "tier_3", "role": "primary", "rationale": "Wrong tier"},
    )
    assert resp.status_code == 422, resp.text
    # Body must have detail explaining the valid tiers
    detail = resp.json().get("detail", "")
    assert "tier_3" in str(detail)


# ---------------------------------------------------------------------------
# No MatrixRun for product → 409
# ---------------------------------------------------------------------------


def test_no_matrix_run_returns_409(tmp_path: Path) -> None:
    """No scored run → structured 409 (not 404 / 500)."""
    client, _, _, _ = _make_client(tmp_path, run=None)  # no run saved

    resp = client.post(
        f"/api/products/mli/candidates/{_MINI_DEPLOYMENT}/promote",
        json={"tier_id": "tier_1", "role": "primary", "rationale": "Premature"},
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body.get("error") == "no_matrix_run"


# ---------------------------------------------------------------------------
# GET audit-log — filtering
# ---------------------------------------------------------------------------


def test_get_audit_log_returns_all_entries(tmp_path: Path) -> None:
    client, _, audit_repo, _ = _make_client(tmp_path, run=_run())

    # Two promotions for different candidates
    client.post(
        f"/api/products/mli/candidates/{_MINI_DEPLOYMENT}/promote",
        json={"tier_id": "tier_1", "role": "primary", "rationale": "R1"},
    )
    client.post(
        f"/api/products/mli/candidates/{_GPT4O_DEPLOYMENT}/reject",
        json={"tier_id": "tier_2", "rationale": "R2"},
    )

    resp = client.get("/api/products/mli/audit-log")
    assert resp.status_code == 200
    data = resp.json()
    assert data["product"] == "mli"
    assert len(data["entries"]) == 2


def test_get_audit_log_filter_by_candidate(tmp_path: Path) -> None:
    client, _, _, _ = _make_client(tmp_path, run=_run())

    client.post(
        f"/api/products/mli/candidates/{_MINI_DEPLOYMENT}/promote",
        json={"tier_id": "tier_1", "role": "primary", "rationale": "R1"},
    )
    client.post(
        f"/api/products/mli/candidates/{_GPT4O_DEPLOYMENT}/reject",
        json={"tier_id": "tier_2", "rationale": "R2"},
    )

    resp = client.get(f"/api/products/mli/audit-log?candidate={_MINI_DEPLOYMENT}")
    assert resp.status_code == 200
    entries = resp.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["candidate_deployment"] == _MINI_DEPLOYMENT


def test_get_audit_log_filter_by_tier(tmp_path: Path) -> None:
    client, _, _, _ = _make_client(tmp_path, run=_run())

    client.post(
        f"/api/products/mli/candidates/{_MINI_DEPLOYMENT}/promote",
        json={"tier_id": "tier_1", "role": "primary", "rationale": "T1 promo"},
    )
    client.post(
        f"/api/products/mli/candidates/{_MINI_DEPLOYMENT}/promote",
        json={"tier_id": "tier_2", "role": "fallback", "rationale": "T2 promo"},
    )

    resp = client.get("/api/products/mli/audit-log?tier=tier_1")
    assert resp.status_code == 200
    entries = resp.json()["entries"]
    assert all(e["tier_id"] == "tier_1" for e in entries)
    assert len(entries) == 1


def test_get_audit_log_filter_by_since(tmp_path: Path) -> None:
    """since filters to entries with timestamp >= since."""
    from mmfp.api import promotion as promo_module
    from mmfp.api import scoreboard
    from mmfp.api.main import app
    from mmfp.persistence.audit_log import AuditLogRepository
    from mmfp.persistence.blob_seam import DiskBlobSeam
    from mmfp.persistence.candidate_status import CandidateStatusStore

    # Use a controlled clock to put entries at known timestamps
    t1 = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 6, 2, 10, 0, 0, tzinfo=timezone.utc)
    timestamps = iter([t1, t2])
    frozen_clock = lambda: next(timestamps)  # noqa: E731

    audit_repo = AuditLogRepository(DiskBlobSeam(tmp_path / "audit"), clock=frozen_clock)
    status_store = CandidateStatusStore(DiskBlobSeam(tmp_path / "status"))

    repo = MatrixRunRepository(tmp_path / "test.db")
    repo.save(_run(), product="mli")
    candidates = [_mini_candidate(), _gpt4o_candidate()]

    def _override_repo():
        return repo

    def _override_loader():
        def _load(p):
            return candidates if p == "mli" else (_ for _ in ()).throw(FileNotFoundError())

        return _load

    def _override_audit():
        return audit_repo

    def _override_status():
        return status_store

    app.dependency_overrides[scoreboard.get_repository] = _override_repo
    app.dependency_overrides[scoreboard.get_candidate_loader] = _override_loader
    app.dependency_overrides[promo_module.get_audit_log_repository] = _override_audit
    app.dependency_overrides[promo_module.get_candidate_status_store] = _override_status
    app.dependency_overrides[scoreboard.get_candidate_status_store] = _override_status

    client = TestClient(app)

    # First entry at t1, second at t2
    client.post(
        f"/api/products/mli/candidates/{_MINI_DEPLOYMENT}/promote",
        json={"tier_id": "tier_1", "role": "primary", "rationale": "Entry at t1"},
    )
    client.post(
        f"/api/products/mli/candidates/{_MINI_DEPLOYMENT}/promote",
        json={"tier_id": "tier_2", "role": "fallback", "rationale": "Entry at t2"},
    )

    # since=t2 → only the second entry.
    # Use UTC without offset (no '+00:00') — the '+' in a query string is
    # decoded as a space by FastAPI's datetime parser, which causes 422.
    # A naive UTC string is accepted and treated as UTC by the endpoint's
    # since_utc normalisation.
    since_str = t2.strftime("%Y-%m-%dT%H:%M:%S")
    resp = client.get(f"/api/products/mli/audit-log?since={since_str}")
    assert resp.status_code == 200
    entries = resp.json()["entries"]
    assert len(entries) == 1


def test_get_audit_log_filter_by_limit(tmp_path: Path) -> None:
    """limit=1 returns only the newest entry (entries are newest-first)."""
    client, _, _, _ = _make_client(tmp_path, run=_run())

    for i in range(3):
        client.post(
            f"/api/products/mli/candidates/{_MINI_DEPLOYMENT}/promote",
            json={"tier_id": "tier_1", "role": "primary", "rationale": f"Round {i}"},
        )

    resp = client.get("/api/products/mli/audit-log?limit=1")
    assert resp.status_code == 200
    entries = resp.json()["entries"]
    assert len(entries) == 1


def test_get_audit_log_bad_tier_returns_422(tmp_path: Path) -> None:
    """Invalid TierId value → FastAPI 422 (automatic from type annotation)."""
    client, _, _, _ = _make_client(tmp_path, run=_run())
    resp = client.get("/api/products/mli/audit-log?tier=tier_99")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Scoreboard status overlay (MLI-202 AC)
# ---------------------------------------------------------------------------


def test_scoreboard_reflects_promoted_status(tmp_path: Path) -> None:
    """After promoting gpt-4.1-mini in tier_1, the scoreboard shows
    approved_primary for that (tier, candidate) pair.
    """
    client, _, _, _ = _make_client(tmp_path, run=_run())

    # Before: under_evaluation
    resp_before = client.get("/api/products/mli/scoreboard")
    assert resp_before.status_code == 200
    tiers_before = {t["tier_id"]: t for t in resp_before.json()["tiers"]}
    t1_cands = tiers_before["tier_1"]["candidates"]
    mini_before = next((c for c in t1_cands if c["deployment"] == _MINI_DEPLOYMENT), None)
    if mini_before is not None:
        assert mini_before["status"] == "under_evaluation"

    # Promote
    resp = client.post(
        f"/api/products/mli/candidates/{_MINI_DEPLOYMENT}/promote",
        json={"tier_id": "tier_1", "role": "primary", "rationale": "Best in class"},
    )
    assert resp.status_code == 200

    # After: approved_primary in tier_1
    resp_after = client.get("/api/products/mli/scoreboard")
    assert resp_after.status_code == 200
    tiers_after = {t["tier_id"]: t for t in resp_after.json()["tiers"]}
    t1_cands_after = tiers_after["tier_1"]["candidates"]
    mini_after = next((c for c in t1_cands_after if c["deployment"] == _MINI_DEPLOYMENT), None)
    assert mini_after is not None
    assert mini_after["status"] == "approved_primary"


# ---------------------------------------------------------------------------
# OpenAPI — all three new paths exposed
# ---------------------------------------------------------------------------


def test_openapi_exposes_promote_reject_audit_log_paths(tmp_path: Path) -> None:
    """All three new routes appear in the OpenAPI schema."""
    client, _, _, _ = _make_client(tmp_path)

    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]

    promote_key = "/api/products/{product}/candidates/{deployment}/promote"
    reject_key = "/api/products/{product}/candidates/{deployment}/reject"
    audit_key = "/api/products/{product}/audit-log"

    assert promote_key in paths, f"promote path missing; paths={list(paths)}"
    assert reject_key in paths, f"reject path missing; paths={list(paths)}"
    assert audit_key in paths, f"audit-log path missing; paths={list(paths)}"

    # Each write path has a POST; the audit-log has a GET
    assert "post" in paths[promote_key]
    assert "post" in paths[reject_key]
    assert "get" in paths[audit_key]


# ---------------------------------------------------------------------------
# Unknown product / unknown candidate
# ---------------------------------------------------------------------------


def test_unknown_product_returns_404(tmp_path: Path) -> None:
    client, _, _, _ = _make_client(tmp_path, run=_run())
    resp = client.post(
        "/api/products/does-not-exist/candidates/gpt-4.1-mini/promote",
        json={"tier_id": "tier_1", "role": "primary", "rationale": "R"},
    )
    assert resp.status_code == 404


def test_unknown_candidate_returns_404(tmp_path: Path) -> None:
    client, _, _, _ = _make_client(tmp_path, run=_run())
    resp = client.post(
        "/api/products/mli/candidates/no-such-model/promote",
        json={"tier_id": "tier_1", "role": "primary", "rationale": "R"},
    )
    assert resp.status_code == 404
