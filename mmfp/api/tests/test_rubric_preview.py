"""Tests for POST /api/products/{product}/rubric/preview-impact (MLI-193).

Eight cases cover:
  1. No-change rubric → zero deltas
  2. Weight tweak shifts rankings
  3. Invalid rubric → 422
  4. Unknown product → 404
  5. No run → 200 empty state
  6. Coverage-incomplete flagged
  7. Normalisation staleness flagged
  8. OpenAPI smoke: path + operation present

Harness pattern mirrors test_candidate_detail.py: a `_make_client` helper saves
runs to a real MatrixRunRepository, back-dates `created_at` to `started_at` for
deterministic ordering, and injects dependency overrides for `get_repository`
and `get_current_rubric_loader`.

Import of `rubric_preview` is deferred into test bodies and helpers per
CLAUDE.md — a module-level import of a not-yet-existent symbol would fail at
collection time before any -m filtering could protect the pipeline.
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
from mmfp.models.rubric import (
    Dimension,
    Direction,
    JudgeConfig,
    Method,
    Rubric,
    Tier,
)
from mmfp.persistence import MatrixRunRepository

_RUN_ANCHOR = datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------


def _judge_config() -> JudgeConfig:
    return JudgeConfig(
        model="claude-sonnet-4-5",
        provider="anthropic",
        version_pin="2025-10-01",
        calibration_set="products/test/datasets/judge_calibration.jsonl",
    )


def _stub_rubric(
    *,
    tier_id: str = "tier_1",
    dimensions: list[Dimension] | None = None,
    version: str = "v0.1",
) -> Rubric:
    """Minimal single-tier rubric for preview-impact tests."""
    if dimensions is None:
        dimensions = [
            Dimension(
                id="t1.accuracy",
                name="Accuracy",
                description="Exact-match accuracy",
                weight=Decimal("75"),
                status="active",
                method=Method.DETERMINISTIC,
                direction=Direction.HIGHER_IS_BETTER,
                evaluator="exact_match",
            ),
            Dimension(
                id="t1.latency",
                name="Latency",
                description="Per-call latency proxy",
                weight=Decimal("25"),
                status="active",
                method=Method.METRIC,
                direction=Direction.LOWER_IS_BETTER,
                evaluator="latency_p95",
            ),
        ]
    return Rubric(
        version=version,
        tiers=[
            Tier(
                id=tier_id,
                name="Test Tier",
                intent="Test rubric",
                mode="single_turn",
                dimensions=dimensions,
            )
        ],
        judge=_judge_config(),
    )


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
    offset_days: int = 0,
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
    deployment: str | None = None,
) -> Candidate:
    return Candidate(
        id=cid,
        display_name=f"Candidate {cid}",
        family=CandidateFamily.CHAT,
        max_tokens=1024,
        context_window=128000,
        tiers=["tier_1"],
        status=CandidateStatus.UNDER_EVALUATION,
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
    runs_in_save_order: list[tuple[MatrixRun, str]],
    rubric: Rubric | None = None,
) -> tuple[TestClient, MatrixRunRepository]:
    """Save runs to a real repo, back-date created_at, wire dependency overrides.

    Pattern mirrors test_candidate_detail._make_client — back-dating
    `created_at` to `started_at` makes `list_for_product(limit=1)` ordering
    deterministic (the repo orders `created_at DESC, id DESC`).
    """
    from mmfp.api import rubric_preview
    from mmfp.api.main import app
    from mmfp.api.scoreboard import get_repository

    db_path = tmp_path / "test.db"
    repo = MatrixRunRepository(db_path)
    for run, product in runs_in_save_order:
        repo.save(run, product=product)
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE matrix_runs SET created_at = ? WHERE id = ?",
                (run.started_at.isoformat(), run.id),
            )

    rubric_for_test = rubric if rubric is not None else _stub_rubric()

    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[rubric_preview.get_current_rubric_loader] = (
        lambda: (lambda product: rubric_for_test)  # noqa: ARG005
    )

    return TestClient(app, raise_server_exceptions=True), repo


def _rubric_as_dict(rubric: Rubric) -> dict:
    """Serialise a Rubric to the dict shape the endpoint accepts."""
    return rubric.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_preview_no_change_rubric_zero_deltas(tmp_path: Path) -> None:
    """Posting the same rubric as current produces zero score and rank deltas."""
    from mmfp.api.main import app

    rubric = _stub_rubric()
    run = _run(
        run_id="run-1",
        results=[
            _result(candidate_id="c1", dimension_id="t1.accuracy", normalized_score=Decimal("80")),
            _result(candidate_id="c1", dimension_id="t1.latency", normalized_score=Decimal("60")),
            _result(candidate_id="c2", dimension_id="t1.accuracy", normalized_score=Decimal("50")),
            _result(candidate_id="c2", dimension_id="t1.latency", normalized_score=Decimal("50")),
        ],
    )

    client, _ = _make_client(tmp_path, [(run, "mli")], rubric=rubric)
    try:
        resp = client.post(
            "/api/products/mli/rubric/preview-impact",
            json={"rubric": _rubric_as_dict(rubric)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["has_run"] is True
        assert body["run_id"] == "run-1"
        assert body["current_version"] == "v0.1"
        assert body["candidate_version"] == "v0.1"

        tier = body["tiers"][0]
        assert tier["tier_id"] == "tier_1"
        for delta in tier["candidates"]:
            assert Decimal(delta["score_before"]) == Decimal(delta["score_after"])
            assert delta["rank_before"] == delta["rank_after"]
    finally:
        app.dependency_overrides.clear()


def test_preview_weight_tweak_shifts_rankings(tmp_path: Path) -> None:
    """Re-weighting flips ranking for a tier with two candidates and two dims.

    c1 is strong on t1.accuracy (weight=75 before), weak on t1.latency.
    c2 is the reverse. Flipping to accuracy=25, latency=75 flips the winner.
    """
    from mmfp.api.main import app

    current_rubric = _stub_rubric(
        dimensions=[
            Dimension(
                id="t1.accuracy",
                name="Accuracy",
                description="Accuracy",
                weight=Decimal("75"),
                status="active",
                method=Method.DETERMINISTIC,
                direction=Direction.HIGHER_IS_BETTER,
                evaluator="exact_match",
            ),
            Dimension(
                id="t1.latency",
                name="Latency",
                description="Latency",
                weight=Decimal("25"),
                status="active",
                method=Method.METRIC,
                direction=Direction.LOWER_IS_BETTER,
                evaluator="latency_p95",
            ),
        ]
    )

    # c1: accuracy=90, latency=20 → weighted = (90*75 + 20*25)/100 = 72.5
    # c2: accuracy=20, latency=90 → weighted = (20*75 + 90*25)/100 = 37.5
    # So before: c1 rank=1, c2 rank=2.
    # After (accuracy=25, latency=75):
    # c1: (90*25 + 20*75)/100 = 37.5
    # c2: (20*25 + 90*75)/100 = 72.5
    # So after: c2 rank=1, c1 rank=2.
    run = _run(
        run_id="run-1",
        results=[
            _result(candidate_id="c1", dimension_id="t1.accuracy", normalized_score=Decimal("90")),
            _result(candidate_id="c1", dimension_id="t1.latency", normalized_score=Decimal("20")),
            _result(candidate_id="c2", dimension_id="t1.accuracy", normalized_score=Decimal("20")),
            _result(candidate_id="c2", dimension_id="t1.latency", normalized_score=Decimal("90")),
        ],
    )

    candidate_rubric = _stub_rubric(
        dimensions=[
            Dimension(
                id="t1.accuracy",
                name="Accuracy",
                description="Accuracy",
                weight=Decimal("25"),
                status="active",
                method=Method.DETERMINISTIC,
                direction=Direction.HIGHER_IS_BETTER,
                evaluator="exact_match",
            ),
            Dimension(
                id="t1.latency",
                name="Latency",
                description="Latency",
                weight=Decimal("75"),
                status="active",
                method=Method.METRIC,
                direction=Direction.LOWER_IS_BETTER,
                evaluator="latency_p95",
            ),
        ],
        version="v0.2",
    )

    client, _ = _make_client(tmp_path, [(run, "mli")], rubric=current_rubric)
    try:
        resp = client.post(
            "/api/products/mli/rubric/preview-impact",
            json={"rubric": _rubric_as_dict(candidate_rubric)},
        )
        assert resp.status_code == 200
        body = resp.json()
        tier = body["tiers"][0]
        deltas_by_candidate = {d["candidate"]: d for d in tier["candidates"]}
        # At least one candidate changed rank.
        assert any(
            d["rank_before"] != d["rank_after"] for d in tier["candidates"]
        ), "Expected at least one ranking change"
        # c1 drops from rank 1 to rank 2.
        c1 = deltas_by_candidate["c1"]
        assert c1["rank_before"] == 1
        assert c1["rank_after"] == 2
        # c2 rises from rank 2 to rank 1.
        c2 = deltas_by_candidate["c2"]
        assert c2["rank_before"] == 2
        assert c2["rank_after"] == 1
    finally:
        app.dependency_overrides.clear()


def test_preview_invalid_rubric_422(tmp_path: Path) -> None:
    """Posting a rubric with active-weight sum > 100 returns 422 with field errors."""
    from mmfp.api.main import app

    run = _run(run_id="run-1", results=[_result()])
    client, _ = _make_client(tmp_path, [(run, "mli")])
    try:
        # Active weights sum to 130 (> 100) — Tier validator rejects this.
        invalid_rubric = {
            "schema_version": "v1",
            "version": "v0.1",
            "tiers": [
                {
                    "id": "tier_1",
                    "name": "Test",
                    "intent": "Test",
                    "mode": "single_turn",
                    "dimensions": [
                        {
                            "id": "d1",
                            "name": "D1",
                            "description": "D1",
                            "weight": "80",
                            "status": "active",
                            "method": "deterministic",
                            "direction": "higher_is_better",
                            "evaluator": "exact_match",
                        },
                        {
                            "id": "d2",
                            "name": "D2",
                            "description": "D2",
                            "weight": "50",
                            "status": "active",
                            "method": "deterministic",
                            "direction": "higher_is_better",
                            "evaluator": "exact_match",
                        },
                    ],
                }
            ],
            "judge": {
                "model": "claude-sonnet-4-5",
                "provider": "anthropic",
                "version_pin": "2025-10-01",
                "calibration_set": "products/test/datasets/judge_calibration.jsonl",
            },
        }
        resp = client.post(
            "/api/products/mli/rubric/preview-impact",
            json={"rubric": invalid_rubric},
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert isinstance(detail, list), f"Expected list of field errors, got: {detail!r}"
    finally:
        app.dependency_overrides.clear()


def test_preview_unknown_product_404(tmp_path: Path) -> None:
    """Overriding the rubric loader to raise FileNotFoundError yields 404."""
    from mmfp.api import rubric_preview
    from mmfp.api.main import app
    from mmfp.api.scoreboard import get_repository

    repo = MatrixRunRepository(tmp_path / "empty.db")

    def _not_found_loader() -> Callable[[str], Rubric]:
        def _loader(product: str) -> Rubric:
            raise FileNotFoundError(f"no rubric for {product}")

        return _loader

    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[rubric_preview.get_current_rubric_loader] = _not_found_loader

    client = TestClient(app)
    try:
        resp = client.post(
            "/api/products/unknown/rubric/preview-impact",
            json={"rubric": _rubric_as_dict(_stub_rubric())},
        )
        assert resp.status_code == 404
        assert "unknown" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_preview_no_run_empty_state(tmp_path: Path) -> None:
    """Product rubric exists but no MatrixRun stored → 200, has_run=False, tiers=[]."""
    from mmfp.api import rubric_preview
    from mmfp.api.main import app
    from mmfp.api.scoreboard import get_repository

    rubric = _stub_rubric()
    # Repository with no runs saved.
    repo = MatrixRunRepository(tmp_path / "empty.db")

    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[rubric_preview.get_current_rubric_loader] = (
        lambda: (lambda product: rubric)  # noqa: ARG005
    )

    client = TestClient(app, raise_server_exceptions=True)
    try:
        candidate_rubric = _stub_rubric(version="v0.2")
        resp = client.post(
            "/api/products/mli/rubric/preview-impact",
            json={"rubric": _rubric_as_dict(candidate_rubric)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["has_run"] is False
        assert body["run_id"] is None
        assert body["tiers"] == []
        assert body["current_version"] == "v0.1"
        assert body["candidate_version"] == "v0.2"
    finally:
        app.dependency_overrides.clear()


def test_preview_coverage_incomplete_flagged(tmp_path: Path) -> None:
    """Candidate rubric adds an extra active dim the run never measured → coverage_complete=False.

    The run only has results for `t1.accuracy`. The candidate rubric activates a
    second dimension `t1.new` that the run never scored. Because `t1.new` is
    missing from the run's per_dimension map for that candidate, `has_complete_coverage`
    from ScoringEngine is False for the after-card, making `coverage_complete=False`
    on the delta.
    """
    from mmfp.api.main import app

    current_rubric = _stub_rubric(
        dimensions=[
            Dimension(
                id="t1.accuracy",
                name="Accuracy",
                description="Accuracy",
                weight=Decimal("100"),
                status="active",
                method=Method.DETERMINISTIC,
                direction=Direction.HIGHER_IS_BETTER,
                evaluator="exact_match",
            ),
        ]
    )
    # Run only scores t1.accuracy.
    run = _run(
        run_id="run-1",
        results=[
            _result(candidate_id="c1", dimension_id="t1.accuracy", normalized_score=Decimal("80")),
        ],
    )

    # Candidate rubric adds t1.new as active — run never measured it.
    candidate_rubric = _stub_rubric(
        dimensions=[
            Dimension(
                id="t1.accuracy",
                name="Accuracy",
                description="Accuracy",
                weight=Decimal("50"),
                status="active",
                method=Method.DETERMINISTIC,
                direction=Direction.HIGHER_IS_BETTER,
                evaluator="exact_match",
            ),
            Dimension(
                id="t1.new",
                name="New Dim",
                description="A new unmeasured dimension",
                weight=Decimal("50"),
                status="active",
                method=Method.DETERMINISTIC,
                direction=Direction.HIGHER_IS_BETTER,
                evaluator="exact_match",
            ),
        ],
        version="v0.2",
    )

    client, _ = _make_client(tmp_path, [(run, "mli")], rubric=current_rubric)
    try:
        resp = client.post(
            "/api/products/mli/rubric/preview-impact",
            json={"rubric": _rubric_as_dict(candidate_rubric)},
        )
        assert resp.status_code == 200
        tier = resp.json()["tiers"][0]
        c1_delta = next(d for d in tier["candidates"] if d["candidate"] == "c1")
        # t1.new is missing from the run → coverage incomplete for the after-card.
        assert c1_delta["coverage_complete"] is False
    finally:
        app.dependency_overrides.clear()


def test_preview_normalization_staleness_flagged(tmp_path: Path) -> None:
    """A dim whose direction flips in the candidate rubric appears in the stale-dimensions list.

    A same-id-same-direction dim does NOT appear in the stale list.
    """
    from mmfp.api.main import app

    current_rubric = _stub_rubric(
        dimensions=[
            Dimension(
                id="t1.accuracy",
                name="Accuracy",
                description="Accuracy",
                weight=Decimal("60"),
                status="active",
                method=Method.DETERMINISTIC,
                direction=Direction.HIGHER_IS_BETTER,
                evaluator="exact_match",
            ),
            Dimension(
                id="t1.latency",
                name="Latency",
                description="Latency",
                weight=Decimal("40"),
                status="active",
                method=Method.METRIC,
                direction=Direction.LOWER_IS_BETTER,  # lower is better in current
                evaluator="latency_p95",
            ),
        ]
    )

    run = _run(
        run_id="run-1",
        results=[
            _result(candidate_id="c1", dimension_id="t1.accuracy", normalized_score=Decimal("80")),
            _result(
                candidate_id="c1", dimension_id="t1.latency", example_id="ex2",
                normalized_score=Decimal("60"),
            ),
        ],
    )

    # Candidate rubric flips t1.latency to higher_is_better — stale normalisation.
    # t1.accuracy keeps the same direction — should NOT appear in stale list.
    candidate_rubric = _stub_rubric(
        dimensions=[
            Dimension(
                id="t1.accuracy",
                name="Accuracy",
                description="Accuracy",
                weight=Decimal("60"),
                status="active",
                method=Method.DETERMINISTIC,
                direction=Direction.HIGHER_IS_BETTER,  # unchanged
                evaluator="exact_match",
            ),
            Dimension(
                id="t1.latency",
                name="Latency",
                description="Latency",
                weight=Decimal("40"),
                status="active",
                method=Method.METRIC,
                direction=Direction.HIGHER_IS_BETTER,  # flipped → stale
                evaluator="latency_p95",
            ),
        ],
        version="v0.2",
    )

    client, _ = _make_client(tmp_path, [(run, "mli")], rubric=current_rubric)
    try:
        resp = client.post(
            "/api/products/mli/rubric/preview-impact",
            json={"rubric": _rubric_as_dict(candidate_rubric)},
        )
        assert resp.status_code == 200
        tier = resp.json()["tiers"][0]
        stale = tier["normalization_stale_dimensions"]
        assert "t1.latency" in stale, f"Expected t1.latency in stale list, got {stale}"
        assert "t1.accuracy" not in stale, "t1.accuracy direction unchanged; should not be stale"
    finally:
        app.dependency_overrides.clear()


def test_preview_openapi_smoke() -> None:
    """GET /openapi.json contains the preview-impact path with POST + requestBody + 200."""
    from mmfp.api import rubric_preview  # noqa: F401
    from mmfp.api.main import app

    client = TestClient(app)
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()

    path_key = "/api/products/{product}/rubric/preview-impact"
    assert path_key in schema["paths"], f"Path {path_key!r} missing from OpenAPI schema"
    post_op = schema["paths"][path_key]["post"]
    assert "requestBody" in post_op, "POST operation must declare a requestBody"
    assert "200" in post_op["responses"], "POST operation must declare a 200 response"
    response_200 = post_op["responses"]["200"]
    schema_ref = response_200["content"].get("application/json", {}).get("schema", {})
    assert schema_ref, "200 response must reference a schema"
