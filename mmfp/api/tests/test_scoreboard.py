"""Tests for GET /api/products/{product}/scoreboard (MLI-174).

Uses FastAPI's TestClient with app.dependency_overrides to inject a real
SQLite repo (tmp_path) and an in-memory candidate loader. All acceptance
criteria from the MLI-174 sub-task are covered here.

Test helpers follow the style of mmfp/persistence/tests/test_matrix_run_repository.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable

from fastapi.testclient import TestClient

from mmfp.models.candidate import (
    Candidate,
    CandidateBinding,
    CandidateFamily,
    CandidateStatus,
)
from mmfp.models.matrix_run import EvaluatorScore, MatrixRun, MatrixRunResult, SourceField
from mmfp.persistence import MatrixRunRepository

# Imports of the new scoreboard module are deferred into test bodies below.
# Module-level import would fail collection before MLI-174 implementation
# lands (per CLAUDE.md "Defer imports of not-yet-existent symbols").


# ---------------------------------------------------------------------------
# Helpers — mirrors the _score / _result / _run pattern in the repo tests
# ---------------------------------------------------------------------------

_STARTED_AT = datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc)
_COMPLETED_AT = datetime(2026, 5, 10, 12, 0, 30, tzinfo=timezone.utc)


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
    candidate_id: str = "c1",
    example_id: str = "ex1",
    dimension_id: str = "t1.accuracy",
    normalized_score: Decimal = Decimal("75.000"),
) -> MatrixRunResult:
    return MatrixRunResult(
        tier_id=tier_id,
        candidate_id=candidate_id,
        dataset_id="ds-t1",
        example_id=example_id,
        score=_score(dimension_id=dimension_id, normalized_score=normalized_score),
    )


def _run(
    *,
    run_id: str = "run-abc",
    results: list[MatrixRunResult] | None = None,
) -> MatrixRun:
    return MatrixRun(
        id=run_id,
        rubric_version="v0.1",
        started_at=_STARTED_AT,
        completed_at=_COMPLETED_AT,
        results=results if results is not None else [],
    )


def _candidate(
    *,
    cid: str = "c1",
    display_name: str = "Candidate One",
    family: CandidateFamily = CandidateFamily.CHAT,
    tiers: list[str] | None = None,
    status: CandidateStatus = CandidateStatus.UNDER_EVALUATION,
) -> Candidate:
    return Candidate(
        id=cid,
        display_name=display_name,
        family=family,
        max_tokens=1024,
        tiers=tiers or ["tier_1"],
        status=status,
        binding=CandidateBinding(
            provider="azure_foundry",
            endpoint="https://example.cognitiveservices.azure.com",
            deployment=f"deploy-{cid}",
            api_version="2024-12-01-preview",
            auth_method="api_key_header",
            key_vault_secret_name="fake-secret",
        ),
    )


# ---------------------------------------------------------------------------
# Fixture: TestClient with overrides
# ---------------------------------------------------------------------------


def _make_client(
    tmp_path: Path,
    candidates: list[Candidate],
    runs: list[tuple[MatrixRun, str]],  # (run, product)
) -> tuple[TestClient, MatrixRunRepository]:
    """Build a TestClient with dependency overrides injected.

    Returns the client and the repo so tests can inspect state directly.
    The candidate loader always returns the provided list regardless of
    product name — tests that need product isolation can use separate clients.
    """
    # Deferred import so collection succeeds before the module exists (CLAUDE.md).
    from mmfp.api import scoreboard
    from mmfp.api.main import app

    repo = MatrixRunRepository(tmp_path / "test.db")
    for run, product in runs:
        repo.save(run, product=product)

    def _override_repo() -> MatrixRunRepository:
        return repo

    def _override_loader() -> Callable[[str], list[Candidate]]:
        def _loader(product: str) -> list[Candidate]:  # noqa: ARG001
            return candidates

        return _loader

    app.dependency_overrides[scoreboard.get_repository] = _override_repo
    app.dependency_overrides[scoreboard.get_candidate_loader] = _override_loader

    client = TestClient(app, raise_server_exceptions=True)
    return client, repo


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


def test_happy_path_returns_200_with_correct_structure(tmp_path: Path) -> None:
    """happy path — repo has a run for mli, slate has 2 candidates."""
    from mmfp.api.main import app

    c1 = _candidate(cid="c1", tiers=["tier_1"])
    c2 = _candidate(cid="c2", tiers=["tier_2", "tier_3"])
    run = _run(
        run_id="run-happy",
        results=[
            _result(tier_id="tier_1", candidate_id="c1"),
            _result(tier_id="tier_2", candidate_id="c2"),
            _result(tier_id="tier_3", candidate_id="c2"),
        ],
    )

    client, _ = _make_client(tmp_path, [c1, c2], [(run, "mli")])
    try:
        resp = client.get("/api/products/mli/scoreboard")
        assert resp.status_code == 200
        body = resp.json()

        assert body["run_id"] == "run-happy"
        assert body["rubric_version"] == "v0.1"
        assert body["product"] == "mli"

        tiers = body["tiers"]
        assert len(tiers) == 3
        tier_ids = [t["tier_id"] for t in tiers]
        assert tier_ids == ["tier_1", "tier_2", "tier_3"]

        # tier_1 has c1
        t1_cands = tiers[0]["candidates"]
        assert len(t1_cands) == 1
        c = t1_cands[0]
        assert c["candidate_id"] == "c1"
        assert c["display_name"] == "Candidate One"
        assert c["family"] == "chat"
        assert c["deployment"] == "deploy-c1"
        assert c["status"] == "under_evaluation"
        # weighted_score > 0 (we seeded 75.000)
        assert Decimal(c["weighted_score"]) > Decimal("0")
    finally:
        app.dependency_overrides.clear()


def test_happy_path_decimal_rendered_as_string(tmp_path: Path) -> None:
    """Decimal precision — weighted_score must be a JSON string, not a number."""
    from mmfp.api.main import app

    c1 = _candidate(cid="c1", tiers=["tier_1"])
    run = _run(
        run_id="run-decimal",
        results=[_result(tier_id="tier_1", candidate_id="c1", normalized_score=Decimal("50.000"))],
    )

    client, _ = _make_client(tmp_path, [c1], [(run, "mli")])
    try:
        resp = client.get("/api/products/mli/scoreboard")
        assert resp.status_code == 200

        import json as _json

        raw = _json.loads(resp.text)
        t1_cands = raw["tiers"][0]["candidates"]
        assert len(t1_cands) == 1
        # In the raw JSON, the value must be a string token, not a number.
        # We re-parse the raw text to confirm the JSON type.
        raw_text = resp.text
        # The serialised value appears as a quoted string in the JSON.
        assert '"50.000"' in raw_text or '"weighted_score": "' in raw_text
        # Double-check: parsed value is str, not int/float.
        assert isinstance(t1_cands[0]["weighted_score"], str)
    finally:
        app.dependency_overrides.clear()


def test_per_dimension_populated(tmp_path: Path) -> None:
    """per_dimension populated — at least one candidate has dimension means."""
    from mmfp.api.main import app

    c1 = _candidate(cid="c1", tiers=["tier_1"])
    run = _run(
        run_id="run-perdim",
        results=[_result(tier_id="tier_1", candidate_id="c1", dimension_id="t1.accuracy")],
    )

    client, _ = _make_client(tmp_path, [c1], [(run, "mli")])
    try:
        resp = client.get("/api/products/mli/scoreboard")
        assert resp.status_code == 200
        t1_cands = resp.json()["tiers"][0]["candidates"]
        assert len(t1_cands) == 1
        per_dim = t1_cands[0]["per_dimension"]
        assert "t1.accuracy" in per_dim
        assert Decimal(per_dim["t1.accuracy"]) > Decimal("0")
    finally:
        app.dependency_overrides.clear()


def test_empty_tier_appears_with_empty_candidates_list(tmp_path: Path) -> None:
    """Empty tier — run has tier_1 results only; t2/t3 appear with candidates: []."""
    from mmfp.api.main import app

    c1 = _candidate(cid="c1", tiers=["tier_1"])
    run = _run(
        run_id="run-empty-tiers",
        results=[_result(tier_id="tier_1", candidate_id="c1")],
    )

    client, _ = _make_client(tmp_path, [c1], [(run, "mli")])
    try:
        resp = client.get("/api/products/mli/scoreboard")
        assert resp.status_code == 200
        tiers = resp.json()["tiers"]
        # All three tiers present
        assert len(tiers) == 3
        by_id = {t["tier_id"]: t for t in tiers}
        assert by_id["tier_2"]["candidates"] == []
        assert by_id["tier_3"]["candidates"] == []
    finally:
        app.dependency_overrides.clear()


def test_404_no_runs_for_product(tmp_path: Path) -> None:
    """404 — slate exists but no runs for product."""
    from mmfp.api import scoreboard
    from mmfp.api.main import app

    repo = MatrixRunRepository(tmp_path / "empty.db")

    def _override_repo() -> MatrixRunRepository:
        return repo

    def _override_loader() -> Callable[[str], list[Candidate]]:
        def _loader(product: str) -> list[Candidate]:  # noqa: ARG001
            # Slate exists (doesn't raise FileNotFoundError)
            return [_candidate()]

        return _loader

    app.dependency_overrides[scoreboard.get_repository] = _override_repo
    app.dependency_overrides[scoreboard.get_candidate_loader] = _override_loader

    client = TestClient(app)
    try:
        resp = client.get("/api/products/mli/scoreboard")
        assert resp.status_code == 404
        assert "mli" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_404_unknown_product(tmp_path: Path) -> None:
    """404 — candidate slate file doesn't exist for product."""
    from mmfp.api import scoreboard
    from mmfp.api.main import app

    repo = MatrixRunRepository(tmp_path / "nofile.db")

    def _override_repo() -> MatrixRunRepository:
        return repo

    def _override_loader() -> Callable[[str], list[Candidate]]:
        def _loader(product: str) -> list[Candidate]:
            raise FileNotFoundError(f"no slate for {product}")

        return _loader

    app.dependency_overrides[scoreboard.get_repository] = _override_repo
    app.dependency_overrides[scoreboard.get_candidate_loader] = _override_loader

    client = TestClient(app)
    try:
        resp = client.get("/api/products/unknown-product/scoreboard")
        assert resp.status_code == 404
        assert "unknown-product" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_scorecard_sorted_desc_by_weighted_score(tmp_path: Path) -> None:
    """Multiple candidates in a tier — response is sorted desc by weighted_score."""
    from mmfp.api.main import app

    c1 = _candidate(cid="c1", tiers=["tier_1"])
    c2 = _candidate(cid="c2", display_name="Candidate Two", tiers=["tier_1"])
    # c1 gets score 90, c2 gets score 50 — c1 must appear first
    run = _run(
        run_id="run-sort",
        results=[
            _result(
                tier_id="tier_1",
                candidate_id="c1",
                normalized_score=Decimal("90.000"),
            ),
            _result(
                tier_id="tier_1",
                candidate_id="c2",
                normalized_score=Decimal("50.000"),
            ),
        ],
    )

    client, _ = _make_client(tmp_path, [c1, c2], [(run, "mli")])
    try:
        resp = client.get("/api/products/mli/scoreboard")
        assert resp.status_code == 200
        t1_cands = resp.json()["tiers"][0]["candidates"]
        assert len(t1_cands) == 2
        scores = [Decimal(c["weighted_score"]) for c in t1_cands]
        assert scores[0] >= scores[1], "Expected descending order by weighted_score"
        assert t1_cands[0]["candidate_id"] == "c1"
    finally:
        app.dependency_overrides.clear()


def test_candidate_not_in_slate_falls_back_gracefully(tmp_path: Path) -> None:
    """Candidate in run but not in slate — endpoint 200; fallback fields applied."""
    from mmfp.api.main import app

    # Slate has c1 only; run references c1 and ghost-c
    c1 = _candidate(cid="c1", tiers=["tier_1"])
    run = _run(
        run_id="run-ghost",
        results=[
            _result(tier_id="tier_1", candidate_id="c1"),
            _result(tier_id="tier_1", candidate_id="ghost-c"),
        ],
    )

    client, _ = _make_client(tmp_path, [c1], [(run, "mli")])
    try:
        resp = client.get("/api/products/mli/scoreboard")
        assert resp.status_code == 200
        t1_cands = resp.json()["tiers"][0]["candidates"]
        ids = {c["candidate_id"] for c in t1_cands}
        assert "ghost-c" in ids, "Scored candidate not in slate must still appear"
        ghost = next(c for c in t1_cands if c["candidate_id"] == "ghost-c")
        assert ghost["display_name"] == "ghost-c"
        assert ghost["deployment"] == "(unknown)"
    finally:
        app.dependency_overrides.clear()


def test_openapi_smoke_scoreboard_in_paths(tmp_path: Path) -> None:
    """OpenAPI smoke — endpoint appears in paths with a typed 200 response."""
    # Importing main registers the router; we need scoreboard imported first.
    from mmfp.api import scoreboard  # noqa: F401
    from mmfp.api.main import app

    client = TestClient(app)
    resp = client.get("/openapi.json")
    assert resp.status_code == 200

    schema = resp.json()
    path_key = "/api/products/{product}/scoreboard"
    assert path_key in schema["paths"], (
        f"Expected '{path_key}' in OpenAPI paths; got: {list(schema['paths'].keys())}"
    )
    get_op = schema["paths"][path_key]["get"]
    assert "200" in get_op["responses"], "Expected a 200 response defined"
    # The 200 response must reference a schema (fully-typed, not just {})
    response_200 = get_op["responses"]["200"]
    assert "content" in response_200, "200 response must carry a content schema"
    schema_ref = (
        response_200["content"].get("application/json", {}).get("schema", {})
    )
    assert schema_ref, "200 response application/json must have a schema"
