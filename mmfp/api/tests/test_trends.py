"""Tests for GET /api/products/{product}/trends (MLI-184).

Style mirrors test_scoreboard.py: FastAPI TestClient + dependency_overrides
to inject a real SQLite repo (tmp_path) and an in-memory candidate loader.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
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

# Imports of the new trends module are deferred into test bodies.

_RUN_ANCHOR = datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc)


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
    run_id: str,
    offset_days: int,
    results: list[MatrixRunResult],
) -> MatrixRun:
    started = _RUN_ANCHOR - timedelta(days=offset_days)
    return MatrixRun(
        id=run_id,
        rubric_version="v0.1",
        started_at=started,
        completed_at=started + timedelta(seconds=30),
        results=results,
    )


def _candidate(
    *,
    cid: str = "c1",
    display_name: str = "Candidate One",
    family: CandidateFamily = CandidateFamily.CHAT,
    tiers: list[str] | None = None,
    deployment: str | None = None,
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
            deployment=deployment or f"deploy-{cid}",
            api_version="2024-12-01-preview",
            auth_method="api_key_header",
            key_vault_secret_name="fake-secret",
        ),
    )


def _make_client(
    tmp_path: Path,
    candidates: list[Candidate],
    runs_in_save_order: list[tuple[MatrixRun, str]],
) -> tuple[TestClient, MatrixRunRepository]:
    """Build a TestClient with repo + candidate-loader overrides.

    Runs are saved in the order given; `list_for_product` orders by
    `created_at DESC`, so save them oldest-to-newest for a clean
    chronological history.
    """
    from mmfp.api import scoreboard, trends
    from mmfp.api.main import app

    db_path = tmp_path / "test.db"
    repo = MatrixRunRepository(db_path)
    # Back-date created_at to started_at so list_for_product ordering is
    # deterministic regardless of insert timing. Mirrors seed_dev_runs.py.
    for run, product in runs_in_save_order:
        repo.save(run, product=product)
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE matrix_runs SET created_at = ? WHERE id = ?",
                (run.started_at.isoformat(), run.id),
            )

    app.dependency_overrides[scoreboard.get_repository] = lambda: repo
    app.dependency_overrides[scoreboard.get_candidate_loader] = (
        lambda: (lambda product: candidates)  # noqa: ARG005
    )
    # trends.py reuses scoreboard's providers, but in case it ever swaps,
    # override here too — explicit beats implicit.
    if hasattr(trends, "get_repository"):
        app.dependency_overrides[trends.get_repository] = lambda: repo
    if hasattr(trends, "get_candidate_loader"):
        app.dependency_overrides[trends.get_candidate_loader] = (
            lambda: (lambda product: candidates)  # noqa: ARG005
        )

    return TestClient(app, raise_server_exceptions=True), repo


def test_trends_happy_path(tmp_path: Path) -> None:
    """Two candidates, three runs — both candidates appear with three points each."""
    from mmfp.api.main import app

    c1 = _candidate(cid="c1", tiers=["tier_1"])
    c2 = _candidate(cid="c2", display_name="Candidate Two", tiers=["tier_1"])
    runs = [
        _run(
            run_id="run-old",
            offset_days=28,
            results=[
                _result(candidate_id="c1", normalized_score=Decimal("60.000")),
                _result(candidate_id="c2", normalized_score=Decimal("40.000")),
            ],
        ),
        _run(
            run_id="run-mid",
            offset_days=14,
            results=[
                _result(candidate_id="c1", normalized_score=Decimal("70.000")),
                _result(candidate_id="c2", normalized_score=Decimal("50.000")),
            ],
        ),
        _run(
            run_id="run-new",
            offset_days=0,
            results=[
                _result(candidate_id="c1", normalized_score=Decimal("80.000")),
                _result(candidate_id="c2", normalized_score=Decimal("55.000")),
            ],
        ),
    ]

    client, _ = _make_client(tmp_path, [c1, c2], [(r, "mli") for r in runs])
    try:
        resp = client.get("/api/products/mli/trends?tier=tier_1")
        assert resp.status_code == 200
        body = resp.json()

        assert body["product"] == "mli"
        assert body["tier_id"] == "tier_1"
        # Runs ordered newest first (matches list_for_product convention).
        run_ids = [r["run_id"] for r in body["runs"]]
        assert run_ids == ["run-new", "run-mid", "run-old"]

        cands = body["candidates"]
        assert len(cands) == 2
        # Sorted by latest run's weighted score, desc — c1 (80) before c2 (55).
        assert [c["candidate_id"] for c in cands] == ["c1", "c2"]

        c1_out = cands[0]
        assert c1_out["display_name"] == "Candidate One"
        assert c1_out["deployment"] == "deploy-c1"
        # Three points, run-aligned with `runs` (newest first).
        assert [p["run_id"] for p in c1_out["points"]] == ["run-new", "run-mid", "run-old"]
        assert Decimal(c1_out["points"][0]["weighted_score"]) == Decimal("80.000")
    finally:
        app.dependency_overrides.clear()


def test_trends_default_runs_is_ten_and_respects_param(tmp_path: Path) -> None:
    """Default n=10; ?runs=2 returns the latest 2."""
    from mmfp.api.main import app

    c1 = _candidate(cid="c1", tiers=["tier_1"])
    # Twelve runs, descending offset (oldest first as saved).
    runs = [
        _run(
            run_id=f"run-{i:02d}",
            offset_days=11 - i,
            results=[_result(candidate_id="c1", normalized_score=Decimal("50.000"))],
        )
        for i in range(12)
    ]

    client, _ = _make_client(tmp_path, [c1], [(r, "mli") for r in runs])
    try:
        resp_default = client.get("/api/products/mli/trends?tier=tier_1")
        assert resp_default.status_code == 200
        assert len(resp_default.json()["runs"]) == 10

        resp_two = client.get("/api/products/mli/trends?tier=tier_1&runs=2")
        assert resp_two.status_code == 200
        body = resp_two.json()
        assert len(body["runs"]) == 2
        # Latest two — run-11, run-10.
        assert [r["run_id"] for r in body["runs"]] == ["run-11", "run-10"]
        # Each candidate's points must align with the same run window.
        assert len(body["candidates"][0]["points"]) == 2
    finally:
        app.dependency_overrides.clear()


def test_trends_runs_more_than_available(tmp_path: Path) -> None:
    """runs=100 against 3 runs — returns 3, no error."""
    from mmfp.api.main import app

    c1 = _candidate(cid="c1", tiers=["tier_1"])
    runs = [
        _run(
            run_id=f"run-{i}",
            offset_days=10 - i,
            results=[_result(candidate_id="c1")],
        )
        for i in range(3)
    ]

    client, _ = _make_client(tmp_path, [c1], [(r, "mli") for r in runs])
    try:
        resp = client.get("/api/products/mli/trends?tier=tier_1&runs=100")
        assert resp.status_code == 200
        assert len(resp.json()["runs"]) == 3
        assert len(resp.json()["candidates"][0]["points"]) == 3
    finally:
        app.dependency_overrides.clear()


def test_trends_decimal_rendered_as_string(tmp_path: Path) -> None:
    """weighted_score serialised as JSON string, not number."""
    from mmfp.api.main import app

    c1 = _candidate(cid="c1", tiers=["tier_1"])
    run = _run(
        run_id="run-decimal",
        offset_days=0,
        results=[_result(candidate_id="c1", normalized_score=Decimal("50.000"))],
    )

    client, _ = _make_client(tmp_path, [c1], [(run, "mli")])
    try:
        resp = client.get("/api/products/mli/trends?tier=tier_1")
        assert resp.status_code == 200
        score = resp.json()["candidates"][0]["points"][0]["weighted_score"]
        assert isinstance(score, str)
        assert '"50.000"' in resp.text
    finally:
        app.dependency_overrides.clear()


def test_trends_only_includes_candidates_with_data_in_window(tmp_path: Path) -> None:
    """Candidate in slate but with no scored results in the window is omitted."""
    from mmfp.api.main import app

    c1 = _candidate(cid="c1", tiers=["tier_1"])
    # c-ghost is in slate but never scored.
    cg = _candidate(cid="c-ghost", display_name="Ghost", tiers=["tier_1"])
    run = _run(
        run_id="run-only-c1",
        offset_days=0,
        results=[_result(candidate_id="c1")],
    )

    client, _ = _make_client(tmp_path, [c1, cg], [(run, "mli")])
    try:
        resp = client.get("/api/products/mli/trends?tier=tier_1")
        assert resp.status_code == 200
        ids = [c["candidate_id"] for c in resp.json()["candidates"]]
        assert ids == ["c1"]
    finally:
        app.dependency_overrides.clear()


def test_trends_filters_by_tier(tmp_path: Path) -> None:
    """Results from other tiers don't bleed into the requested tier."""
    from mmfp.api.main import app

    c1 = _candidate(cid="c1", tiers=["tier_1", "tier_2"])
    run = _run(
        run_id="run-multi-tier",
        offset_days=0,
        results=[
            _result(tier_id="tier_1", candidate_id="c1", normalized_score=Decimal("70.000")),
            _result(tier_id="tier_2", candidate_id="c1", normalized_score=Decimal("30.000")),
        ],
    )

    client, _ = _make_client(tmp_path, [c1], [(run, "mli")])
    try:
        resp = client.get("/api/products/mli/trends?tier=tier_2")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tier_id"] == "tier_2"
        assert len(body["candidates"]) == 1
        assert Decimal(body["candidates"][0]["points"][0]["weighted_score"]) == Decimal(
            "30.000"
        )
    finally:
        app.dependency_overrides.clear()


def test_trends_404_unknown_product(tmp_path: Path) -> None:
    from mmfp.api import scoreboard
    from mmfp.api.main import app

    repo = MatrixRunRepository(tmp_path / "empty.db")

    def _override_loader() -> Callable[[str], list[Candidate]]:
        def _loader(product: str) -> list[Candidate]:
            raise FileNotFoundError(f"no slate for {product}")

        return _loader

    app.dependency_overrides[scoreboard.get_repository] = lambda: repo
    app.dependency_overrides[scoreboard.get_candidate_loader] = _override_loader

    client = TestClient(app)
    try:
        resp = client.get("/api/products/unknown/trends?tier=tier_1")
        assert resp.status_code == 404
        assert "unknown" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_trends_404_no_runs_for_product(tmp_path: Path) -> None:
    """Slate exists, but the product has no runs in the DB."""
    from mmfp.api.main import app

    c1 = _candidate(cid="c1", tiers=["tier_1"])
    client, _ = _make_client(tmp_path, [c1], runs_in_save_order=[])
    try:
        resp = client.get("/api/products/mli/trends?tier=tier_1")
        assert resp.status_code == 404
        assert "mli" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_trends_runs_bounds_validation(tmp_path: Path) -> None:
    """runs=0 and runs=-1 → 422 (Query bound is ge=1)."""
    from mmfp.api.main import app

    c1 = _candidate(cid="c1", tiers=["tier_1"])
    run = _run(
        run_id="run-1",
        offset_days=0,
        results=[_result(candidate_id="c1")],
    )

    client, _ = _make_client(tmp_path, [c1], [(run, "mli")])
    try:
        assert client.get("/api/products/mli/trends?tier=tier_1&runs=0").status_code == 422
        assert client.get("/api/products/mli/trends?tier=tier_1&runs=-1").status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_trends_invalid_tier_id_422(tmp_path: Path) -> None:
    """tier=tier_99 → 422; FastAPI validates the Literal."""
    from mmfp.api.main import app

    c1 = _candidate(cid="c1", tiers=["tier_1"])
    run = _run(run_id="r", offset_days=0, results=[_result(candidate_id="c1")])

    client, _ = _make_client(tmp_path, [c1], [(run, "mli")])
    try:
        assert client.get("/api/products/mli/trends?tier=tier_99").status_code == 422
        assert client.get("/api/products/mli/trends").status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_trends_openapi_smoke(tmp_path: Path) -> None:  # noqa: ARG001
    from mmfp.api import trends  # noqa: F401
    from mmfp.api.main import app

    client = TestClient(app)
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    path_key = "/api/products/{product}/trends"
    assert path_key in schema["paths"]
    get_op = schema["paths"][path_key]["get"]
    assert "200" in get_op["responses"]
    response_200 = get_op["responses"]["200"]
    schema_ref = response_200["content"].get("application/json", {}).get("schema", {})
    assert schema_ref, "200 response must reference a schema"
