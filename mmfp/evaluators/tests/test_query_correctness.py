"""QueryCorrectnessEvaluator unit tests.

Tests build a small SQLite golden DB via a fresh .sql file in tmp_path so
each test is hermetic. One test exercises the shipped reference golden
DB at products/mli/datasets/golden_dbs/query_correctness_v0.sql to keep
the file from drifting silently.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from mmfp.evaluators import get


@pytest.fixture
def evaluator():
    return get("query_correctness")()


@pytest.fixture
def golden_db(tmp_path: Path) -> Path:
    """A 3-row toy DB built per-test, isolated under tmp_path."""
    sql = (
        "CREATE TABLE widgets ("
        "    id INTEGER PRIMARY KEY,"
        "    name TEXT NOT NULL,"
        "    qty INTEGER NOT NULL"
        ");\n"
        "INSERT INTO widgets (id, name, qty) VALUES"
        " (1, 'alpha', 10),"
        " (2, 'beta', 5),"
        " (3, 'gamma', 7);"
    )
    p = tmp_path / "golden.sql"
    p.write_text(sql)
    return p


def _ctx(golden_db: Path, *, dim_id: str = "dim_query") -> dict:
    return {
        "dimension_id": dim_id,
        "evaluator_config": {"golden_db_path": str(golden_db)},
    }


def test_exact_match_passes(evaluator, golden_db):
    score = evaluator.evaluate(
        "SELECT name FROM widgets WHERE qty > 6 ORDER BY name",
        {"rows": [["alpha"], ["gamma"]]},
        _ctx(golden_db),
    )
    assert score.passed is True
    assert score.normalized_score == Decimal("100")


def test_row_set_mismatch_fails(evaluator, golden_db):
    score = evaluator.evaluate(
        "SELECT name FROM widgets WHERE qty > 100",
        {"rows": [["alpha"]]},
        _ctx(golden_db),
    )
    assert score.passed is False
    assert score.normalized_score == Decimal("0")
    assert "0 row" in score.reason or "expected 1" in score.reason


def test_unordered_match_by_default(evaluator, golden_db):
    """Order doesn't matter by default — rows are compared as a multiset."""
    score = evaluator.evaluate(
        "SELECT name FROM widgets WHERE qty > 6",
        {"rows": [["gamma"], ["alpha"]]},
        _ctx(golden_db),
    )
    assert score.passed is True


def test_order_matters_when_requested(evaluator, golden_db):
    score = evaluator.evaluate(
        "SELECT name FROM widgets WHERE qty > 6 ORDER BY qty",
        {"rows": [["alpha"], ["gamma"]], "order_matters": True},
        _ctx(golden_db),
    )
    assert score.passed is False  # qty order is gamma (7) then alpha (10)


def test_order_matters_passes_with_correct_order(evaluator, golden_db):
    score = evaluator.evaluate(
        "SELECT name FROM widgets WHERE qty > 6 ORDER BY qty",
        {"rows": [["gamma"], ["alpha"]], "order_matters": True},
        _ctx(golden_db),
    )
    assert score.passed is True


def test_invalid_sql_scores_0_with_error(evaluator, golden_db):
    score = evaluator.evaluate(
        "SELEKT * FROM widgets",
        {"rows": []},
        _ctx(golden_db),
    )
    assert score.passed is False
    assert score.normalized_score == Decimal("0")
    assert "SQL error" in score.reason
    assert "sql_error" in score.raw_value


def test_write_attempts_are_denied(evaluator, golden_db):
    """The SELECT-only authorizer rejects DML — the harness can't be poisoned."""
    score = evaluator.evaluate(
        "INSERT INTO widgets (id, name, qty) VALUES (4, 'delta', 99)",
        {"rows": []},
        _ctx(golden_db),
    )
    assert score.passed is False
    assert "SQL error" in score.reason


def test_drop_attempts_are_denied(evaluator, golden_db):
    score = evaluator.evaluate(
        "DROP TABLE widgets",
        {"rows": []},
        _ctx(golden_db),
    )
    assert score.passed is False
    assert "SQL error" in score.reason


def test_missing_rows_raises(evaluator, golden_db):
    with pytest.raises(ValueError, match="expected\\['rows'\\]"):
        evaluator.evaluate("SELECT 1", {}, _ctx(golden_db))


def test_missing_golden_db_path_raises(evaluator):
    ctx = {"dimension_id": "dim_query", "evaluator_config": {}}
    with pytest.raises(ValueError, match="golden_db_path"):
        evaluator.evaluate("SELECT 1", {"rows": [[1]]}, ctx)


def test_missing_evaluator_config_raises(evaluator):
    ctx = {"dimension_id": "dim_query"}
    with pytest.raises(ValueError, match="golden_db_path"):
        evaluator.evaluate("SELECT 1", {"rows": [[1]]}, ctx)


def test_nonexistent_golden_db_path_raises(evaluator, tmp_path):
    ctx = {
        "dimension_id": "dim_query",
        "evaluator_config": {"golden_db_path": str(tmp_path / "missing.sql")},
    }
    with pytest.raises(FileNotFoundError):
        evaluator.evaluate("SELECT 1", {"rows": [[1]]}, ctx)


def test_aggregate_query_with_function(evaluator, golden_db):
    """Built-in functions (COUNT, SUM, AVG) are allowed under the authorizer."""
    score = evaluator.evaluate(
        "SELECT COUNT(*) FROM widgets",
        {"rows": [[3]]},
        _ctx(golden_db),
    )
    assert score.passed is True


def test_raw_value_captures_query_and_rows(evaluator, golden_db):
    score = evaluator.evaluate(
        "SELECT name FROM widgets WHERE qty = 5",
        {"rows": [["beta"]]},
        _ctx(golden_db),
    )
    assert score.raw_value["query"] == "SELECT name FROM widgets WHERE qty = 5"
    assert score.raw_value["actual_rows"] == [("beta",)]
    assert score.raw_value["expected_rows"] == [("beta",)]


def test_reference_golden_db_loads_and_runs(evaluator):
    """Exercise the shipped reference golden DB to catch silent drift."""
    repo_root = Path(__file__).resolve().parents[3]
    sql_path = (
        repo_root
        / "products"
        / "mli"
        / "datasets"
        / "golden_dbs"
        / "query_correctness_v0.sql"
    )
    assert sql_path.is_file(), f"reference golden DB not found at {sql_path}"
    ctx = {
        "dimension_id": "dim_query_ref",
        "evaluator_config": {"golden_db_path": str(sql_path)},
    }
    score = evaluator.evaluate(
        "SELECT COUNT(*) FROM matters",
        {"rows": [[5]]},
        ctx,
    )
    assert score.passed is True
    score2 = evaluator.evaluate(
        "SELECT practice FROM matters WHERE id = 2",
        {"rows": [["litigation"]]},
        ctx,
    )
    assert score2.passed is True
