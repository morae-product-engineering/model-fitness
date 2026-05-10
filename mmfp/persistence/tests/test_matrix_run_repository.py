"""Unit tests for `MatrixRunRepository` (MLI-258).

Tests use real SQLite files under `tmp_path`; no mocks for the DB.
The Pydantic models are constructed in-memory rather than loaded from
YAML — keeps the tests focused on the persistence boundary.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from mmfp.models.matrix_run import (
    EvaluatorScore,
    MatrixRun,
    MatrixRunResult,
    SourceField,
)
from mmfp.persistence import MatrixRunRepository

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _score(
    *,
    dimension_id: str = "t1.classification_accuracy",
    evaluator_id: str = "exact_match",
    raw_value: object = "A",
    normalized_score: Decimal = Decimal("100.000"),
    passed: bool | None = True,
    cost_usd: Decimal | None = Decimal("0.000123"),
    error: str | None = None,
) -> EvaluatorScore:
    return EvaluatorScore(
        dimension_id=dimension_id,
        evaluator_id=evaluator_id,
        raw_value=raw_value,
        normalized_score=normalized_score,
        passed=passed,
        source_field=SourceField.CONTENT,
        latency_ms=12,
        cost_usd=cost_usd,
        reason="exact match",
        error=error,
    )


def _result(
    *,
    tier_id: str = "tier_1",
    candidate_id: str = "c1",
    example_id: str = "t1.e1",
    score: EvaluatorScore | None = None,
) -> MatrixRunResult:
    return MatrixRunResult(
        tier_id=tier_id,
        candidate_id=candidate_id,
        dataset_id="ds-tier1",
        example_id=example_id,
        score=score or _score(),
        prompt_tokens=5,
        completion_tokens=3,
        finish_reason="stop",
    )


def _run(
    *,
    run_id: str = "deadbeef",
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    results: list[MatrixRunResult] | None = None,
) -> MatrixRun:
    started = started_at or datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
    completed = completed_at or (started + timedelta(seconds=30))
    return MatrixRun(
        id=run_id,
        rubric_version="v0.1",
        started_at=started,
        completed_at=completed,
        results=results
        if results is not None
        else [
            _result(candidate_id="c1", example_id="t1.e1"),
            _result(
                candidate_id="c2",
                example_id="t1.e2",
                score=_score(
                    raw_value={"matched": ["a", "b"]},
                    normalized_score=Decimal("66.667"),
                    passed=False,
                ),
            ),
        ],
    )


@pytest.fixture
def repo(tmp_path: Path) -> MatrixRunRepository:
    return MatrixRunRepository(tmp_path / "mmfp.db")


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def test_save_then_get_round_trips_full_model(repo: MatrixRunRepository) -> None:
    run = _run()
    repo.save(run, product="mli")

    loaded = repo.get(run.id)

    assert loaded == run


def test_get_returns_none_for_unknown_id(repo: MatrixRunRepository) -> None:
    assert repo.get("does-not-exist") is None


def test_save_rejects_empty_product(repo: MatrixRunRepository) -> None:
    with pytest.raises(ValueError, match="product"):
        repo.save(_run(), product="")


def test_save_is_one_shot_per_run_id(repo: MatrixRunRepository) -> None:
    run = _run()
    repo.save(run, product="mli")
    with pytest.raises(sqlite3.IntegrityError):
        repo.save(run, product="mli")


def test_save_persists_run_with_no_results(repo: MatrixRunRepository) -> None:
    run = _run(results=[])
    repo.save(run, product="mli")
    loaded = repo.get(run.id)
    assert loaded is not None
    assert loaded.results == []


def test_save_persists_run_with_completed_at_unset(repo: MatrixRunRepository) -> None:
    started = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
    run = MatrixRun(
        id="abc",
        rubric_version="v0.1",
        started_at=started,
        completed_at=None,
        results=[],
    )
    repo.save(run, product="mli")
    loaded = repo.get(run.id)
    assert loaded is not None
    assert loaded.completed_at is None


# ---------------------------------------------------------------------------
# Decimal & datetime fidelity
# ---------------------------------------------------------------------------


def test_decimal_round_trip_preserves_trailing_zeros(repo: MatrixRunRepository) -> None:
    """Pydantic v2 emits Decimal as a JSON string; round-trip is byte-exact.

    Trailing-zero preservation matters because percentage weights and
    cost-per-call scores are authored as decimals (`Decimal('33.300')`)
    and a downstream comparator against the original may reject a
    silently-trimmed value.
    """
    score = _score(
        normalized_score=Decimal("33.300"),
        cost_usd=Decimal("0.0000010"),
    )
    run = _run(results=[_result(score=score)])
    repo.save(run, product="mli")

    loaded = repo.get(run.id)

    assert loaded is not None
    loaded_score = loaded.results[0].score
    # Equality plus exact-form comparison: Decimal('33.300') ==
    # Decimal('33.3') is True, so check the underlying tuple as well.
    assert loaded_score.normalized_score == Decimal("33.300")
    assert loaded_score.normalized_score.as_tuple() == Decimal("33.300").as_tuple()
    assert loaded_score.cost_usd == Decimal("0.0000010")
    assert loaded_score.cost_usd.as_tuple() == Decimal("0.0000010").as_tuple()


def test_datetime_round_trip_preserves_microseconds(repo: MatrixRunRepository) -> None:
    started = datetime(2026, 5, 10, 12, 0, 0, 123456, tzinfo=timezone.utc)
    completed = started + timedelta(microseconds=987654)
    run = _run(started_at=started, completed_at=completed, results=[])
    repo.save(run, product="mli")

    loaded = repo.get(run.id)

    assert loaded is not None
    assert loaded.started_at == started
    assert loaded.completed_at == completed


def test_non_utc_input_is_normalised_on_round_trip(repo: MatrixRunRepository) -> None:
    """`MatrixRun` accepts any tz-aware datetime; the model normalises to
    UTC at validation time (see `_common._require_tz_aware_utc`). Storage
    must preserve the same instant."""
    other = timezone(timedelta(hours=5, minutes=30))
    started_local = datetime(2026, 5, 10, 17, 30, tzinfo=other)
    started_utc = started_local.astimezone(timezone.utc)
    run = _run(started_at=started_local, completed_at=started_utc, results=[])
    repo.save(run, product="mli")

    loaded = repo.get(run.id)

    assert loaded is not None
    assert loaded.started_at == started_utc


def test_evaluator_score_with_dict_raw_value_round_trips(
    repo: MatrixRunRepository,
) -> None:
    score = _score(raw_value={"matched_groups": ["foo", "bar"], "count": 2})
    run = _run(results=[_result(score=score)])
    repo.save(run, product="mli")

    loaded = repo.get(run.id)

    assert loaded is not None
    assert loaded.results[0].score.raw_value == {
        "matched_groups": ["foo", "bar"],
        "count": 2,
    }


def test_errored_score_round_trips(repo: MatrixRunRepository) -> None:
    """The engine emits errored cells with `raw_value=None`,
    `normalized_score=Decimal('0')`, `passed=None`, and an `error`
    string. All five fields must survive the round-trip — the API
    surfaces these to the UI as 'errored' badges."""
    errored = _score(
        raw_value=None,
        normalized_score=Decimal("0"),
        passed=None,
        cost_usd=None,
        error="binding error: HTTPStatusError: 503",
    )
    run = _run(results=[_result(score=errored)])
    repo.save(run, product="mli")

    loaded = repo.get(run.id)

    assert loaded is not None
    score = loaded.results[0].score
    assert score.error == "binding error: HTTPStatusError: 503"
    assert score.raw_value is None
    assert score.passed is None
    assert score.cost_usd is None


# ---------------------------------------------------------------------------
# list_for_product
# ---------------------------------------------------------------------------


def test_list_for_product_returns_newest_first(repo: MatrixRunRepository) -> None:
    base = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
    runs = [
        _run(run_id=f"run-{i}", started_at=base + timedelta(minutes=i), results=[])
        for i in range(3)
    ]
    for r in runs:
        repo.save(r, product="mli")

    listed = repo.list_for_product("mli", limit=10)

    assert [r.id for r in listed] == ["run-2", "run-1", "run-0"]


def test_list_for_product_respects_limit(repo: MatrixRunRepository) -> None:
    base = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
    for i in range(5):
        repo.save(
            _run(
                run_id=f"run-{i}",
                started_at=base + timedelta(minutes=i),
                results=[],
            ),
            product="mli",
        )

    listed = repo.list_for_product("mli", limit=2)

    assert len(listed) == 2
    assert [r.id for r in listed] == ["run-4", "run-3"]


def test_list_for_product_isolates_products(repo: MatrixRunRepository) -> None:
    repo.save(_run(run_id="mli-1", results=[]), product="mli")
    repo.save(_run(run_id="other-1", results=[]), product="other-product")

    mli = repo.list_for_product("mli", limit=10)
    other = repo.list_for_product("other-product", limit=10)

    assert [r.id for r in mli] == ["mli-1"]
    assert [r.id for r in other] == ["other-1"]


def test_list_for_product_returns_empty_when_unknown(
    repo: MatrixRunRepository,
) -> None:
    repo.save(_run(results=[]), product="mli")
    assert repo.list_for_product("nope", limit=10) == []


def test_list_for_product_rejects_negative_limit(repo: MatrixRunRepository) -> None:
    with pytest.raises(ValueError, match="limit"):
        repo.list_for_product("mli", limit=-1)


def test_list_for_product_returns_full_runs_with_results(
    repo: MatrixRunRepository,
) -> None:
    """Listing isn't just metadata — the API will read full runs from
    here, and the round-trip semantics must match `get()`."""
    run = _run()
    repo.save(run, product="mli")

    listed = repo.list_for_product("mli", limit=10)

    assert listed == [run]


# ---------------------------------------------------------------------------
# Schema migration idempotency
# ---------------------------------------------------------------------------


def test_schema_applies_idempotently_on_fresh_db(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh.db"
    repo_a = MatrixRunRepository(db_path)
    repo_a.save(_run(run_id="a", results=[]), product="mli")

    # A second repository instance against the same file must apply the
    # migration without error and see the prior data.
    repo_b = MatrixRunRepository(db_path)
    loaded = repo_b.get("a")
    assert loaded is not None


def test_schema_creates_parent_directory(tmp_path: Path) -> None:
    """Repository creates `data/` if missing — convenience for first-run
    dev environments that don't have the dir yet."""
    db_path = tmp_path / "nested" / "more" / "mmfp.db"
    repo = MatrixRunRepository(db_path)
    repo.save(_run(results=[]), product="mli")
    assert db_path.exists()


def test_results_preserve_ordinal_order(repo: MatrixRunRepository) -> None:
    """Engine relies on stable result ordering for snapshot-style tests
    and human-readable output (see MatrixEngine docstring); persistence
    must preserve insertion order, not whatever SQLite returns by
    default."""
    results = [
        _result(candidate_id=f"c{i}", example_id=f"t1.e{i}") for i in range(5)
    ]
    run = _run(run_id="ordered", results=results)
    repo.save(run, product="mli")

    loaded = repo.get(run.id)

    assert loaded is not None
    assert [r.candidate_id for r in loaded.results] == [
        "c0",
        "c1",
        "c2",
        "c3",
        "c4",
    ]
