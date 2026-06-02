"""Tests for PUT /api/products/{product}/rubric (MLI-273, MLI-365).

The endpoint validates the steward's edited rubric, bumps the version, and
persists the new rubric + an immutable audit record to a durable store
(``rubric_store``). MLI-365 replaced the git-commit-as-audit-log design: there
is no git repo on the deployed container, so the audit trail is now an explicit
``AuditRecord`` written to the store. These tests run against ``DiskRubricStore``
over a tmp dir — the disk backend mirrors the blob backend's contract, so the
read->validate->write->audit lifecycle is exercised end-to-end without Azure.
(Blob-specific behaviour — managed-identity client, cold-blob bootstrap,
restart durability — is covered in ``test_rubric_store.py``.)

Module-level imports of rubric_write are deferred into test bodies per CLAUDE.md
(pytest collection must succeed even if the module doesn't exist yet).
"""

from __future__ import annotations

import concurrent.futures
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

# Source of truth for a known-good rubric payload — read once at collection
# time, mutated per test.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_REFERENCE_RUBRIC_YAML = _REPO_ROOT / "products" / "mli" / "rubric.yaml"


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_products_dir(tmp_path: Path) -> Path:
    """A tmp products dir with products/mli/rubric.yaml. No git — the deployed
    container isn't a repo, and the store no longer needs one."""
    mli_dir = tmp_path / "products" / "mli"
    mli_dir.mkdir(parents=True)
    shutil.copy(_REFERENCE_RUBRIC_YAML, mli_dir / "rubric.yaml")
    return tmp_path / "products"


def _load_rubric_dict(products_dir: Path, product: str = "mli") -> dict[str, Any]:
    """Read a product's rubric YAML as a plain dict."""
    path = products_dir / product / "rubric.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _audit_records(products_dir: Path, product: str = "mli") -> list[dict[str, Any]]:
    """All audit records the disk store has written for a product, oldest first."""
    audit_dir = products_dir / product / "rubric" / "audit"
    if not audit_dir.is_dir():
        return []
    return [json.loads(p.read_text()) for p in sorted(audit_dir.glob("*.json"))]


def _make_client(products_dir: Path, *, raise_server_exceptions: bool = True) -> TestClient:
    """Mount the rubric router with a DiskRubricStore bound to products_dir."""
    from mmfp.api import rubric_write  # deferred import
    from mmfp.api.main import app
    from mmfp.api.rubric_store import DiskRubricStore

    app.dependency_overrides[rubric_write.get_rubric_store] = lambda: DiskRubricStore(
        products_dir
    )
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


@pytest.fixture
def products_dir(tmp_path: Path) -> Path:
    return _make_products_dir(tmp_path)


@pytest.fixture(autouse=True)
def _clear_overrides() -> None:
    """Make sure dependency_overrides doesn't leak between tests."""
    yield
    from mmfp.api.main import app

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_happy_path_persists_rubric_audit_and_bumps_version(products_dir: Path) -> None:
    """PUT a valid rubric with the right expected_version → 200, rubric rewritten,
    version bumped, one audit record written."""
    client = _make_client(products_dir)

    body = _load_rubric_dict(products_dir)
    payload = {"rubric": body, "expected_version": "v0.1", "note": "lower latency weight"}

    resp = client.put("/api/products/mli/rubric", json=payload)
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert data["previous_version"] == "v0.1"
    assert data["new_version"] == "v0.2"
    # audit_ref points at the immutable record the store just wrote.
    assert data["audit_ref"].startswith("mli/rubric/audit/")
    assert data["audit_ref"].endswith("-v0.2.json")

    # Stored rubric has the bumped version.
    assert _load_rubric_dict(products_dir)["version"] == "v0.2"

    # Exactly one audit record, carrying the version delta + note + steward.
    records = _audit_records(products_dir)
    assert len(records) == 1
    rec = records[0]
    assert rec["previous_version"] == "v0.1"
    assert rec["new_version"] == "v0.2"
    assert rec["note"] == "lower latency weight"
    assert rec["steward"] == "Unknown Steward <steward@unknown.local>"
    assert rec["timestamp"]  # ISO 8601 string present


def test_no_note_records_null_note(products_dir: Path) -> None:
    """Omitting `note` → audit record's note is null (no synthesised message)."""
    client = _make_client(products_dir)
    body = _load_rubric_dict(products_dir)

    resp = client.put(
        "/api/products/mli/rubric",
        json={"rubric": body, "expected_version": "v0.1"},
    )
    assert resp.status_code == 200, resp.text

    records = _audit_records(products_dir)
    assert len(records) == 1
    assert records[0]["note"] is None


# ---------------------------------------------------------------------------
# Validation (422)
# ---------------------------------------------------------------------------


def test_invalid_rubric_returns_422_with_structured_body(products_dir: Path) -> None:
    """Pydantic validator rejects the payload → 422, structured detail body,
    rubric unchanged, no audit record."""
    client = _make_client(products_dir)
    body = _load_rubric_dict(products_dir)
    # Trip the active-weight sum validator (MLI-269): drop tier_1 active weights.
    for tier in body["tiers"]:
        if tier["id"] == "tier_1":
            for dim in tier["dimensions"]:
                dim["weight"] = 0

    resp = client.put(
        "/api/products/mli/rubric",
        json={"rubric": body, "expected_version": "v0.1"},
    )
    assert resp.status_code == 422, resp.text

    detail = resp.json()["detail"]
    # Structured error body: a list of {loc, msg, type} dicts. Pin the shape +
    # an identifying substring, not exact Pydantic wording.
    assert isinstance(detail, list) and detail
    assert all("msg" in e and "loc" in e for e in detail)
    assert any("active dimension weight" in (e.get("msg") or "") for e in detail)

    # Rubric unchanged; no audit record written.
    assert _load_rubric_dict(products_dir)["version"] == "v0.1"
    assert _audit_records(products_dir) == []


def test_missing_rubric_in_payload_returns_422(products_dir: Path) -> None:
    """Empty body / wrong shape → 422 from FastAPI's own validation."""
    client = _make_client(products_dir)
    resp = client.put("/api/products/mli/rubric", json={})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Concurrency (409)
# ---------------------------------------------------------------------------


def test_version_mismatch_returns_409_with_current_version(products_dir: Path) -> None:
    """expected_version doesn't match the store → 409, body carries
    current_version, rubric unchanged, no audit record."""
    client = _make_client(products_dir)
    body = _load_rubric_dict(products_dir)

    resp = client.put(
        "/api/products/mli/rubric",
        json={"rubric": body, "expected_version": "v9.9", "note": "stale write"},
    )
    assert resp.status_code == 409, resp.text

    data = resp.json()
    assert data["current_version"] == "v0.1"
    assert data["expected_version"] == "v9.9"

    assert _load_rubric_dict(products_dir)["version"] == "v0.1"
    assert _audit_records(products_dir) == []


# ---------------------------------------------------------------------------
# Actor identity → audit record (reconciled placeholder, MLI-365)
# ---------------------------------------------------------------------------


def test_steward_header_recorded_in_audit_record(products_dir: Path) -> None:
    """X-Steward-Identity is recorded as the audit record's steward field."""
    client = _make_client(products_dir)
    body = _load_rubric_dict(products_dir)

    resp = client.put(
        "/api/products/mli/rubric",
        json={"rubric": body, "expected_version": "v0.1", "note": "tweak"},
        headers={"X-Steward-Identity": "Wayne Palmer <wayne.palmer@morae.com>"},
    )
    assert resp.status_code == 200, resp.text

    records = _audit_records(products_dir)
    assert records[0]["steward"] == "Wayne Palmer <wayne.palmer@morae.com>"


def test_missing_steward_header_uses_single_placeholder(products_dir: Path) -> None:
    """No X-Steward-Identity → the single reconciled placeholder (MLI-365)."""
    client = _make_client(products_dir)
    body = _load_rubric_dict(products_dir)

    resp = client.put(
        "/api/products/mli/rubric",
        json={"rubric": body, "expected_version": "v0.1"},
    )
    assert resp.status_code == 200, resp.text

    records = _audit_records(products_dir)
    # The ONE placeholder identity across the stack — the UI sends the same.
    assert records[0]["steward"] == "Unknown Steward <steward@unknown.local>"


# ---------------------------------------------------------------------------
# Unknown product
# ---------------------------------------------------------------------------


def test_unknown_product_returns_404(products_dir: Path) -> None:
    """No rubric under products/<slug>/ → 404."""
    client = _make_client(products_dir)
    body = _load_rubric_dict(products_dir)

    resp = client.put(
        "/api/products/does-not-exist/rubric",
        json={"rubric": body, "expected_version": "v0.1"},
    )
    assert resp.status_code == 404


def test_path_traversal_in_product_slug_rejected(products_dir: Path) -> None:
    """`product` must match a safe slug pattern; reject anything else."""
    client = _make_client(products_dir)
    body = _load_rubric_dict(products_dir)

    resp = client.put(
        "/api/products/..%2fetc/rubric",
        json={"rubric": body, "expected_version": "v0.1"},
    )
    # FastAPI canonicalises the path; this either 404s (no such product) or
    # 400s on slug validation. Either is fine — what matters is we never write
    # outside the store's product prefix.
    assert resp.status_code in (400, 404)


# ---------------------------------------------------------------------------
# Persistence-failure path returns a CORS-carrying structured error (MLI-365)
# ---------------------------------------------------------------------------


def test_persistence_failure_returns_structured_500_with_cors_header(products_dir: Path) -> None:
    """A store whose save() fails must yield a structured 500 WITH a CORS header
    — not an unhandled raise.

    This is the regression class the deployed save 500 came from (MLI-197 /
    MLI-365): an unhandled exception in the save path produces FastAPI's bare
    500, generated above CORSMiddleware, with no Access-Control-Allow-Origin →
    the browser reports "Failed to fetch" instead of the real error. The write
    endpoint catches persistence failures and raises an HTTPException, which
    flows back through CORSMiddleware and gets the header.
    """
    from mmfp.api import rubric_write
    from mmfp.api.main import app
    from mmfp.api.rubric_store import DiskRubricStore

    class _FailingStore(DiskRubricStore):
        def save(self, product, *, rubric_raw, audit):  # type: ignore[override]
            raise RuntimeError("blob unreachable")

    app.dependency_overrides[rubric_write.get_rubric_store] = lambda: _FailingStore(
        products_dir
    )
    # raise_server_exceptions=False so an UNHANDLED 500 would surface as a 500
    # response (no CORS header) rather than re-raising — the test still
    # distinguishes "handled with CORS" from "unhandled".
    client = TestClient(app, raise_server_exceptions=False)

    body = _load_rubric_dict(products_dir)
    resp = client.put(
        "/api/products/mli/rubric",
        json={"rubric": body, "expected_version": "v0.1", "note": "x"},
        headers={"Origin": "http://localhost:3000"},
    )

    assert resp.status_code == 500, resp.text
    assert isinstance(resp.json().get("detail"), str)
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


# ---------------------------------------------------------------------------
# Concurrency serialisation (AC4, MLI-194)
# ---------------------------------------------------------------------------


def test_concurrent_writes_serialise_one_winner(products_dir: Path) -> None:
    """N concurrent PUTs, all claiming the same expected_version, serialise to
    exactly one winner.

    Without the per-product lock (MLI-194) multiple writers pass the
    `expected_version` 409 check before any of them persists, so several land
    200s. The lock makes the read->check->write->audit section atomic per
    replica, so the second writer onward sees the winner's bumped version and
    gets 409. (Cross-replica concurrency is the blob-ETag fast-follow.)
    """
    n = 8
    body = _load_rubric_dict(products_dir)

    def _worker() -> tuple[int, dict[str, Any]]:
        client = _make_client(products_dir)
        resp = client.put(
            "/api/products/mli/rubric",
            json={"rubric": body, "expected_version": "v0.1", "note": "concurrent"},
        )
        return resp.status_code, resp.json()

    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
        results = [f.result() for f in [pool.submit(_worker) for _ in range(n)]]

    statuses = [status for status, _ in results]
    winners = [data for status, data in results if status == 200]
    conflicts = [data for status, data in results if status == 409]

    # Exactly one winner, the rest clean 409s — no 500s, no extra 200s.
    assert statuses.count(200) == 1, results
    assert statuses.count(409) == n - 1, results
    assert len(winners) + len(conflicts) == n, results

    assert winners[0]["new_version"] == "v0.2"
    assert all(c["current_version"] == "v0.2" for c in conflicts), conflicts

    # Exactly one audit record landed — no double-write, no partial state.
    assert len(_audit_records(products_dir)) == 1

    # Stored rubric loads cleanly and reflects the single bump (no corruption).
    assert _load_rubric_dict(products_dir)["version"] == "v0.2"
