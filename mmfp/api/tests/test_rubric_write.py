"""Tests for PUT /api/products/{product}/rubric (MLI-273).

The endpoint writes the steward's edited rubric to disk, commits via git,
and bumps the rubric version. Tests run against a real temporary git repo
so the commit-then-version-bump lifecycle is exercised end-to-end — Git is
the audit trail (per MLI-273 brief + the MLI-267 governance-posture note),
not SQLite, so the commit *is* the assertion surface.

Module-level imports of the new rubric_write module are deferred into test
bodies (per CLAUDE.md — pytest collection must succeed if the module
doesn't exist yet).
"""

from __future__ import annotations

import concurrent.futures
import shutil
import subprocess
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
# Helpers
# ---------------------------------------------------------------------------


def _run_git(*args: str, cwd: Path) -> str:
    """Run a git command in cwd and return stdout. Raises if non-zero exit."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _init_repo_with_rubric(tmp_path: Path) -> Path:
    """Set up a tmp git repo with products/mli/rubric.yaml committed.

    Returns the products-dir path the endpoint should consume.
    """
    repo = tmp_path / "repo"
    products_dir = repo / "products"
    mli_dir = products_dir / "mli"
    mli_dir.mkdir(parents=True)

    shutil.copy(_REFERENCE_RUBRIC_YAML, mli_dir / "rubric.yaml")

    _run_git("init", "-q", "-b", "main", cwd=repo)
    # Local git identity so commits succeed in CI sandboxes that have no
    # global user.name / user.email configured.
    _run_git("config", "user.email", "ci@example.com", cwd=repo)
    _run_git("config", "user.name", "CI", cwd=repo)
    _run_git("add", "products/mli/rubric.yaml", cwd=repo)
    _run_git("commit", "-q", "-m", "initial rubric", cwd=repo)

    return products_dir


def _load_rubric_dict(products_dir: Path, product: str = "mli") -> dict[str, Any]:
    """Read a product's rubric YAML as a plain dict."""
    path = products_dir / product / "rubric.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _make_client(products_dir: Path) -> TestClient:
    """Mount the rubric router with the products dir override applied."""
    from mmfp.api import rubric_write  # deferred import
    from mmfp.api.main import app

    def _override_products_dir() -> Path:
        return products_dir

    app.dependency_overrides[rubric_write.get_products_dir] = _override_products_dir
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def products_dir(tmp_path: Path) -> Path:
    return _init_repo_with_rubric(tmp_path)


@pytest.fixture(autouse=True)
def _clear_overrides() -> None:
    """Make sure dependency_overrides doesn't leak between tests."""
    yield
    from mmfp.api.main import app

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_happy_path_writes_yaml_commits_and_bumps_version(products_dir: Path) -> None:
    """PUT a valid rubric with the right expected_version → 200, YAML rewritten,
    version bumped, one new commit on HEAD."""
    client = _make_client(products_dir)

    body = _load_rubric_dict(products_dir)
    payload = {"rubric": body, "expected_version": "v0.1", "note": "lower latency weight"}

    resp = client.put("/api/products/mli/rubric", json=payload)
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert data["previous_version"] == "v0.1"
    assert data["new_version"] == "v0.2"
    assert isinstance(data["commit_sha"], str) and len(data["commit_sha"]) >= 7

    # YAML on disk has the bumped version.
    on_disk = _load_rubric_dict(products_dir)
    assert on_disk["version"] == "v0.2"

    # One new commit on HEAD, message matches the spec.
    log = _run_git(
        "log", "-n", "1", "--pretty=%s", cwd=products_dir.parent
    ).strip()
    assert log == "rubric: lower latency weight [v0.1->v0.2]"


def test_no_note_uses_default_message(products_dir: Path) -> None:
    """Omitting `note` → commit message uses `weight adjustment` per the spec."""
    client = _make_client(products_dir)
    body = _load_rubric_dict(products_dir)

    resp = client.put(
        "/api/products/mli/rubric",
        json={"rubric": body, "expected_version": "v0.1"},
    )
    assert resp.status_code == 200, resp.text

    log = _run_git("log", "-n", "1", "--pretty=%s", cwd=products_dir.parent).strip()
    assert log == "rubric: weight adjustment [v0.1->v0.2]"


# ---------------------------------------------------------------------------
# Validation (422)
# ---------------------------------------------------------------------------


def test_invalid_rubric_returns_422_with_structured_body(products_dir: Path) -> None:
    """Pydantic validator rejects the payload → 422, structured detail body,
    YAML unchanged, no new commit."""
    client = _make_client(products_dir)
    body = _load_rubric_dict(products_dir)
    # Trip the active-weight sum validator from MLI-269: drop one tier's
    # active dimensions to zero.
    for tier in body["tiers"]:
        if tier["id"] == "tier_1":
            for dim in tier["dimensions"]:
                dim["weight"] = 0

    sha_before = _run_git("rev-parse", "HEAD", cwd=products_dir.parent).strip()

    resp = client.put(
        "/api/products/mli/rubric",
        json={"rubric": body, "expected_version": "v0.1"},
    )
    assert resp.status_code == 422, resp.text

    detail = resp.json()["detail"]
    # Structured error body: a list of {loc, msg, type} dicts surfaced from
    # Pydantic's ValidationError. Don't pin exact messages — Pydantic's
    # wording shifts between minors. Pin the *shape* and an identifying
    # substring instead.
    assert isinstance(detail, list) and detail
    assert all("msg" in e and "loc" in e for e in detail)
    assert any("active dimension weight" in (e.get("msg") or "") for e in detail)

    # YAML unchanged; no new commit.
    assert _load_rubric_dict(products_dir)["version"] == "v0.1"
    assert _run_git("rev-parse", "HEAD", cwd=products_dir.parent).strip() == sha_before


def test_missing_rubric_in_payload_returns_422(products_dir: Path) -> None:
    """Empty body / wrong shape → 422 from FastAPI's own validation."""
    client = _make_client(products_dir)
    resp = client.put("/api/products/mli/rubric", json={})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Concurrency (409)
# ---------------------------------------------------------------------------


def test_version_mismatch_returns_409_with_current_version(products_dir: Path) -> None:
    """expected_version doesn't match HEAD → 409, body carries current_version,
    YAML unchanged, no new commit."""
    client = _make_client(products_dir)
    body = _load_rubric_dict(products_dir)
    sha_before = _run_git("rev-parse", "HEAD", cwd=products_dir.parent).strip()

    resp = client.put(
        "/api/products/mli/rubric",
        json={"rubric": body, "expected_version": "v9.9", "note": "stale write"},
    )
    assert resp.status_code == 409, resp.text

    data = resp.json()
    assert data["current_version"] == "v0.1"
    assert data["expected_version"] == "v9.9"

    assert _load_rubric_dict(products_dir)["version"] == "v0.1"
    assert _run_git("rev-parse", "HEAD", cwd=products_dir.parent).strip() == sha_before


# ---------------------------------------------------------------------------
# Actor identity → git author
# ---------------------------------------------------------------------------


def test_steward_header_recorded_as_git_author(products_dir: Path) -> None:
    """X-Steward-Identity is recorded as the commit author."""
    client = _make_client(products_dir)
    body = _load_rubric_dict(products_dir)

    resp = client.put(
        "/api/products/mli/rubric",
        json={"rubric": body, "expected_version": "v0.1", "note": "tweak"},
        headers={"X-Steward-Identity": "Wayne Palmer <wayne.palmer@morae.com>"},
    )
    assert resp.status_code == 200, resp.text

    author = _run_git("log", "-n", "1", "--pretty=%an <%ae>", cwd=products_dir.parent).strip()
    assert author == "Wayne Palmer <wayne.palmer@morae.com>"


def test_missing_steward_header_uses_placeholder(products_dir: Path) -> None:
    """No X-Steward-Identity → commit author is the documented placeholder."""
    client = _make_client(products_dir)
    body = _load_rubric_dict(products_dir)

    resp = client.put(
        "/api/products/mli/rubric",
        json={"rubric": body, "expected_version": "v0.1"},
    )
    assert resp.status_code == 200, resp.text

    author = _run_git("log", "-n", "1", "--pretty=%an <%ae>", cwd=products_dir.parent).strip()
    # Placeholder identity — exact value is documented in the architectural-
    # input posted to MLI-267 (sub-task MLI-273).
    assert author == "Unknown Steward <steward@unknown.local>"


# ---------------------------------------------------------------------------
# Unknown product
# ---------------------------------------------------------------------------


def test_unknown_product_returns_404(products_dir: Path) -> None:
    """No rubric.yaml under products/<slug>/ → 404."""
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
    # 400s on slug validation. Either is fine — what matters is we never
    # write outside products_dir.
    assert resp.status_code in (400, 404)


# ---------------------------------------------------------------------------
# Persistence-failure path returns a CORS-carrying structured error (MLI-365)
# ---------------------------------------------------------------------------


def test_persistence_failure_returns_structured_500_with_cors_header(tmp_path: Path) -> None:
    """A products dir that is NOT a git repo must yield a structured 500 WITH a
    CORS header — not an unhandled raise.

    This is the regression the deployed save 500 came from (MLI-197 / MLI-365):
    `_resolve_repo_root` sat outside any try/except, so on the non-git container
    it raised an unhandled RuntimeError -> FastAPI's bare 500, generated above
    CORSMiddleware, carries no Access-Control-Allow-Origin -> the browser reports
    "Failed to fetch" instead of the real error. The fix wraps the persistence
    section so the failure becomes an HTTPException, which flows back through
    CORSMiddleware and gets the header.
    """
    # products dir with a valid rubric.yaml but deliberately NOT inside a git repo.
    mli_dir = tmp_path / "products" / "mli"
    mli_dir.mkdir(parents=True)
    shutil.copy(_REFERENCE_RUBRIC_YAML, mli_dir / "rubric.yaml")
    products_dir = tmp_path / "products"

    # raise_server_exceptions=False so an UNHANDLED 500 would surface as a 500
    # response (with no CORS header) rather than re-raising into the test — i.e.
    # the test still distinguishes "handled with CORS" from "unhandled".
    from mmfp.api import rubric_write  # deferred import
    from mmfp.api.main import app

    app.dependency_overrides[rubric_write.get_products_dir] = lambda: products_dir
    client = TestClient(app, raise_server_exceptions=False)

    body = _load_rubric_dict(products_dir)
    resp = client.put(
        "/api/products/mli/rubric",
        json={"rubric": body, "expected_version": "v0.1", "note": "x"},
        headers={"Origin": "http://localhost:3000"},
    )

    assert resp.status_code == 500, resp.text
    # Structured JSON body, not an opaque/empty error.
    assert isinstance(resp.json().get("detail"), str)
    # The header the browser needs to surface the real error instead of
    # "Failed to fetch".
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


# ---------------------------------------------------------------------------
# Concurrency serialisation (AC4, MLI-194)
# ---------------------------------------------------------------------------


def test_concurrent_writes_serialise_one_winner(products_dir: Path) -> None:
    """N concurrent PUTs, all claiming the same expected_version, serialise to
    exactly one winner.

    Without the per-product lock (Change 1, MLI-194) this test FAILs: multiple
    writers pass the `expected_version` 409 check before any of them commits,
    so several land 200s and/or a `git index.lock` collision surfaces as a 500.
    The lock makes the read->check->write->commit section atomic per replica,
    so the second writer onward sees the winner's bumped version and gets 409.
    """
    n = 8
    body = _load_rubric_dict(products_dir)

    sha_before = _run_git("rev-parse", "HEAD", cwd=products_dir.parent).strip()

    def _worker() -> tuple[int, dict[str, Any]]:
        # Each worker uses its own TestClient against the same tmp repo. The
        # dependency override is idempotent, so re-applying it per worker is
        # safe and sidesteps any httpx-client cross-thread sharing question.
        client = _make_client(products_dir)
        resp = client.put(
            "/api/products/mli/rubric",
            json={"rubric": body, "expected_version": "v0.1", "note": "concurrent"},
        )
        return resp.status_code, resp.json()

    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
        futures = [pool.submit(_worker) for _ in range(n)]
        results = [f.result() for f in futures]

    statuses = [status for status, _ in results]
    winners = [data for status, data in results if status == 200]
    conflicts = [data for status, data in results if status == 409]

    # Exactly one winner, the rest are clean 409s — no 500s, no extra 200s.
    assert statuses.count(200) == 1, results
    assert statuses.count(409) == n - 1, results
    assert len(winners) + len(conflicts) == n, results

    # The winner bumped v0.1 -> v0.2; every loser saw the bumped current_version.
    assert winners[0]["new_version"] == "v0.2"
    assert all(c["current_version"] == "v0.2" for c in conflicts), conflicts

    # Exactly one new commit landed — no double-commit, no partial state.
    sha_after = _run_git("rev-parse", "HEAD", cwd=products_dir.parent).strip()
    count_before = int(
        _run_git("rev-list", "--count", sha_before, cwd=products_dir.parent).strip()
    )
    count_after = int(
        _run_git("rev-list", "--count", sha_after, cwd=products_dir.parent).strip()
    )
    assert count_after - count_before == 1, (count_before, count_after)

    # On-disk YAML loads cleanly and reflects the single bump (no corruption).
    on_disk = _load_rubric_dict(products_dir)
    assert on_disk["version"] == "v0.2"
