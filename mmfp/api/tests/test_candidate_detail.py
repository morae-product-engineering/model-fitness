"""Tests for GET /api/products/{product}/candidates/{deployment_name} (MLI-184).

Lookup is by `binding.deployment` (provider-side deployment name), not the
slate `id` — matches the UI URL form and the scoreboard's `deployment` field.
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
        context_window=128000,  # MLI-272: Candidate.context_window now required.
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
    """Save the runs, then back-date `created_at` to each run's `started_at`.

    The repository orders by `created_at DESC, id DESC`. SQLite's default is
    millisecond precision, so consecutive inserts inside one test can tie;
    `id DESC` then makes lexical run id govern "latest". Back-dating
    `created_at` (the same workaround `scripts/seed_dev_runs.py` uses for
    deployed dev) makes ordering deterministic and matches what the API
    would see against real seeded data.
    """
    from mmfp.api import candidate_detail, scoreboard
    from mmfp.api.main import app

    db_path = tmp_path / "test.db"
    repo = MatrixRunRepository(db_path)
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
    if hasattr(candidate_detail, "get_repository"):
        app.dependency_overrides[candidate_detail.get_repository] = lambda: repo
    if hasattr(candidate_detail, "get_candidate_loader"):
        app.dependency_overrides[candidate_detail.get_candidate_loader] = (
            lambda: (lambda product: candidates)  # noqa: ARG005
        )

    return TestClient(app, raise_server_exceptions=True), repo


def test_candidate_detail_happy_path(tmp_path: Path) -> None:
    """Returns latest-run per-dimension scores plus a history of aggregate scores."""
    from mmfp.api.main import app

    c1 = _candidate(cid="c1", tiers=["tier_1"], deployment="Deploy-One")
    runs = [
        _run(
            run_id="run-old",
            offset_days=28,
            results=[
                _result(
                    candidate_id="c1",
                    dimension_id="t1.accuracy",
                    normalized_score=Decimal("60.000"),
                ),
                _result(
                    candidate_id="c1",
                    dimension_id="t1.latency",
                    example_id="ex2",
                    normalized_score=Decimal("40.000"),
                ),
            ],
        ),
        _run(
            run_id="run-new",
            offset_days=0,
            results=[
                _result(
                    candidate_id="c1",
                    dimension_id="t1.accuracy",
                    normalized_score=Decimal("80.000"),
                ),
                _result(
                    candidate_id="c1",
                    dimension_id="t1.latency",
                    example_id="ex2",
                    normalized_score=Decimal("60.000"),
                ),
            ],
        ),
    ]

    client, _ = _make_client(tmp_path, [c1], [(r, "mli") for r in runs])
    try:
        resp = client.get("/api/products/mli/candidates/Deploy-One")
        assert resp.status_code == 200
        body = resp.json()

        assert body["product"] == "mli"
        assert body["candidate_id"] == "c1"
        assert body["display_name"] == "Candidate One"
        assert body["deployment"] == "Deploy-One"
        assert body["family"] == "chat"
        assert body["status"] == "under_evaluation"
        assert body["tiers"] == ["tier_1"]

        latest = body["latest_run"]
        assert latest is not None
        assert latest["run_id"] == "run-new"
        per_tier = latest["per_tier"]
        assert len(per_tier) == 1
        assert per_tier[0]["tier_id"] == "tier_1"
        per_dim = per_tier[0]["per_dimension"]
        assert set(per_dim.keys()) == {"t1.accuracy", "t1.latency"}
        assert Decimal(per_dim["t1.accuracy"]) == Decimal("80.000")
        assert Decimal(per_dim["t1.latency"]) == Decimal("60.000")
        assert Decimal(per_tier[0]["weighted_score"]) == Decimal("70.000")

        # History: newest first; 2 entries.
        history = body["history"]
        assert [h["run_id"] for h in history] == ["run-new", "run-old"]
        # Each entry carries the tier_1 aggregate weighted score.
        assert Decimal(history[0]["per_tier_scores"]["tier_1"]) == Decimal("70.000")
        assert Decimal(history[1]["per_tier_scores"]["tier_1"]) == Decimal("50.000")
    finally:
        app.dependency_overrides.clear()


def test_candidate_detail_multi_tier_candidate(tmp_path: Path) -> None:
    """Candidate scored in two tiers — both appear in per_tier and per_tier_scores."""
    from mmfp.api.main import app

    c1 = _candidate(cid="c1", tiers=["tier_1", "tier_2"], deployment="Deploy-One")
    run = _run(
        run_id="run-multi",
        offset_days=0,
        results=[
            _result(
                tier_id="tier_1",
                candidate_id="c1",
                normalized_score=Decimal("80.000"),
            ),
            _result(
                tier_id="tier_2",
                candidate_id="c1",
                normalized_score=Decimal("50.000"),
            ),
        ],
    )

    client, _ = _make_client(tmp_path, [c1], [(run, "mli")])
    try:
        resp = client.get("/api/products/mli/candidates/Deploy-One")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tiers"] == ["tier_1", "tier_2"]
        per_tier_ids = [t["tier_id"] for t in body["latest_run"]["per_tier"]]
        assert per_tier_ids == ["tier_1", "tier_2"]
        per_tier_scores = body["history"][0]["per_tier_scores"]
        assert set(per_tier_scores.keys()) == {"tier_1", "tier_2"}
    finally:
        app.dependency_overrides.clear()


def test_candidate_detail_no_scoring_data_returns_200_empty(tmp_path: Path) -> None:
    """Candidate exists in slate but no run contains it — 200 with nulls.

    Matches the seeded-DB phi-4 case: dev seed skips phi-4-mini-instruct by
    default, so its detail page must still load (200) and surface the empty
    state rather than 404.
    """
    from mmfp.api.main import app

    c1 = _candidate(cid="c1", tiers=["tier_1"], deployment="Deploy-One")
    cg = _candidate(cid="phi", tiers=["tier_1"], deployment="Phi-4-mini-instruct")
    run = _run(
        run_id="run-1",
        offset_days=0,
        results=[_result(candidate_id="c1")],
    )

    client, _ = _make_client(tmp_path, [c1, cg], [(run, "mli")])
    try:
        resp = client.get("/api/products/mli/candidates/Phi-4-mini-instruct")
        assert resp.status_code == 200
        body = resp.json()
        assert body["candidate_id"] == "phi"
        assert body["latest_run"] is None
        assert body["history"] == []
    finally:
        app.dependency_overrides.clear()


def test_candidate_detail_latest_walks_back_to_first_run_with_data(tmp_path: Path) -> None:
    """If newest run lacks this candidate, latest_run uses the next one that has it.

    Realistic when a candidate is dropped from one run but appears in prior ones.
    """
    from mmfp.api.main import app

    c1 = _candidate(cid="c1", tiers=["tier_1"], deployment="Deploy-One")
    c2 = _candidate(cid="c2", tiers=["tier_1"], deployment="Deploy-Two")
    runs = [
        _run(
            run_id="run-old",
            offset_days=14,
            results=[_result(candidate_id="c2", normalized_score=Decimal("60.000"))],
        ),
        _run(
            run_id="run-new",
            offset_days=0,
            # Only c1 scored in this run.
            results=[_result(candidate_id="c1")],
        ),
    ]

    client, _ = _make_client(tmp_path, [c1, c2], [(r, "mli") for r in runs])
    try:
        resp = client.get("/api/products/mli/candidates/Deploy-Two")
        assert resp.status_code == 200
        body = resp.json()
        # Latest available run for c2 is run-old.
        assert body["latest_run"]["run_id"] == "run-old"
        # History only contains the run where c2 has data.
        assert [h["run_id"] for h in body["history"]] == ["run-old"]
    finally:
        app.dependency_overrides.clear()


def test_candidate_detail_runs_param_caps_history(tmp_path: Path) -> None:
    """?runs=2 caps history; default is 10."""
    from mmfp.api.main import app

    c1 = _candidate(cid="c1", tiers=["tier_1"], deployment="Deploy-One")
    runs = [
        _run(
            run_id=f"run-{i:02d}",
            offset_days=11 - i,
            results=[_result(candidate_id="c1")],
        )
        for i in range(12)
    ]

    client, _ = _make_client(tmp_path, [c1], [(r, "mli") for r in runs])
    try:
        resp_default = client.get("/api/products/mli/candidates/Deploy-One")
        assert len(resp_default.json()["history"]) == 10

        resp_two = client.get("/api/products/mli/candidates/Deploy-One?runs=2")
        history = resp_two.json()["history"]
        assert len(history) == 2
        assert [h["run_id"] for h in history] == ["run-11", "run-10"]
    finally:
        app.dependency_overrides.clear()


def test_candidate_detail_runs_more_than_available(tmp_path: Path) -> None:
    """runs=100 against 2 runs — returns 2, no error."""
    from mmfp.api.main import app

    c1 = _candidate(cid="c1", tiers=["tier_1"], deployment="Deploy-One")
    runs = [
        _run(run_id="r1", offset_days=14, results=[_result(candidate_id="c1")]),
        _run(run_id="r2", offset_days=0, results=[_result(candidate_id="c1")]),
    ]

    client, _ = _make_client(tmp_path, [c1], [(r, "mli") for r in runs])
    try:
        resp = client.get("/api/products/mli/candidates/Deploy-One?runs=100")
        assert resp.status_code == 200
        assert len(resp.json()["history"]) == 2
    finally:
        app.dependency_overrides.clear()


def test_candidate_detail_decimal_rendered_as_string(tmp_path: Path) -> None:
    from mmfp.api.main import app

    c1 = _candidate(cid="c1", tiers=["tier_1"], deployment="Deploy-One")
    run = _run(
        run_id="run-1",
        offset_days=0,
        results=[_result(candidate_id="c1", normalized_score=Decimal("50.000"))],
    )

    client, _ = _make_client(tmp_path, [c1], [(run, "mli")])
    try:
        resp = client.get("/api/products/mli/candidates/Deploy-One")
        assert resp.status_code == 200
        body = resp.json()
        score = body["latest_run"]["per_tier"][0]["weighted_score"]
        assert isinstance(score, str)
        assert '"50.000"' in resp.text
    finally:
        app.dependency_overrides.clear()


def test_candidate_detail_404_unknown_product(tmp_path: Path) -> None:
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
        resp = client.get("/api/products/unknown/candidates/Whatever")
        assert resp.status_code == 404
        assert "unknown" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_candidate_detail_404_unknown_candidate(tmp_path: Path) -> None:
    """Slate exists but no candidate has that deployment name."""
    from mmfp.api.main import app

    c1 = _candidate(cid="c1", tiers=["tier_1"], deployment="Deploy-One")
    run = _run(run_id="r", offset_days=0, results=[_result(candidate_id="c1")])

    client, _ = _make_client(tmp_path, [c1], [(run, "mli")])
    try:
        resp = client.get("/api/products/mli/candidates/Nonexistent-Deployment")
        assert resp.status_code == 404
        # Distinguishable from the product-unknown 404.
        assert "Nonexistent-Deployment" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_candidate_detail_runs_bounds_validation(tmp_path: Path) -> None:
    from mmfp.api.main import app

    c1 = _candidate(cid="c1", tiers=["tier_1"], deployment="Deploy-One")
    run = _run(run_id="r", offset_days=0, results=[_result(candidate_id="c1")])

    client, _ = _make_client(tmp_path, [c1], [(run, "mli")])
    try:
        assert (
            client.get("/api/products/mli/candidates/Deploy-One?runs=0").status_code
            == 422
        )
        assert (
            client.get("/api/products/mli/candidates/Deploy-One?runs=-3").status_code
            == 422
        )
    finally:
        app.dependency_overrides.clear()


def test_candidate_detail_openapi_smoke(tmp_path: Path) -> None:  # noqa: ARG001
    from mmfp.api import candidate_detail  # noqa: F401
    from mmfp.api.main import app

    client = TestClient(app)
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    path_key = "/api/products/{product}/candidates/{deployment_name}"
    assert path_key in schema["paths"]
    get_op = schema["paths"][path_key]["get"]
    assert "200" in get_op["responses"]
    response_200 = get_op["responses"]["200"]
    schema_ref = response_200["content"].get("application/json", {}).get("schema", {})
    assert schema_ref, "200 response must reference a schema"
