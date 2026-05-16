"""QueryCorrectnessEvaluator — execute candidate SQL against a golden DB.

The candidate emits a SQL query (`candidate_output`). The evaluator loads
the dimension's golden DB from a hermetic .sql script into an in-memory
SQLite, executes the query under a SELECT-only authorizer, and compares
result rows against `expected["rows"]`.

Pass/fail by design. Row-set equality is the unit of correctness — a
"close" result (off-by-one row, extra column) is wrong for a downstream
program that consumes the result. Order-sensitivity is opt-in via
`expected["order_matters"]` because most analytics queries don't require
a specific row order unless they `ORDER BY`.

Dialect: SQLite (per AC). The dialect choice is itself an architectural
question — a candidate that produces correct ANSI-SQL but trips on
SQLite-specific syntax (or vice-versa) is mis-graded against a
production target that's actually Postgres/MS SQL. Flagged as
architectural-input on MLI-267.

Context contract:
    context['evaluator_config']['golden_db_path']  str  (file path)
        Path to a .sql script that builds the golden DB (schema +
        INSERTs). Loaded into `:memory:` per evaluation; the file is
        read every call. For ~100-row goldens this is sub-millisecond
        and keeps the harness stateless.

Safety: the candidate query runs under a SQLite authorizer that allows
SELECT/READ/FUNCTION and denies everything else. An INSERT/UPDATE/DELETE
attempted by a candidate fails with an `sqlite3.DatabaseError` and is
reported as a SQL error (score 0). The in-memory DB is also discarded at
the end of each call, so even a hypothetical authorizer bypass cannot
persist state.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from mmfp.evaluators._registry import register
from mmfp.evaluators.deterministic._helpers import make_score
from mmfp.models.matrix_run import EvaluatorScore
from mmfp.plugins.evaluator import EvaluatorPlugin


@register
class QueryCorrectnessEvaluator(EvaluatorPlugin):
    name = "query_correctness"

    def evaluate(
        self,
        candidate_output: str,
        expected: dict[str, Any],
        context: dict[str, Any],
    ) -> EvaluatorScore:
        if "rows" not in expected:
            raise ValueError(
                "QueryCorrectness requires expected['rows'] (list of result rows)"
            )
        target_rows = expected["rows"]
        if not isinstance(target_rows, list):
            raise TypeError("expected['rows'] must be a list of row lists/tuples")
        order_matters = bool(expected.get("order_matters", False))

        cfg = context.get("evaluator_config") or {}
        if not isinstance(cfg, dict):
            raise ValueError(
                f"evaluator_config must be a dict; got {type(cfg).__name__}"
            )
        if "golden_db_path" not in cfg:
            raise ValueError(
                "evaluator 'query_correctness' requires "
                "evaluator_config['golden_db_path'] (path to .sql script "
                "building the golden DB)"
            )
        sql_path = Path(cfg["golden_db_path"])
        if not sql_path.is_file():
            raise FileNotFoundError(
                f"golden_db_path does not exist or is not a file: {sql_path}"
            )

        target = [tuple(r) for r in target_rows]
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(sql_path.read_text())
            conn.commit()
            conn.set_authorizer(_select_only_authorizer)
            try:
                actual = [tuple(r) for r in conn.execute(candidate_output).fetchall()]
            except sqlite3.Error as e:
                return make_score(
                    context=context,
                    evaluator_name=self.name,
                    source_field=self.scores_field,
                    raw_value={
                        "sql_error": str(e),
                        "query": candidate_output,
                        "expected_rows": target,
                    },
                    passed=False,
                    reason=f"SQL error: {e}",
                )
        finally:
            conn.close()

        if order_matters:
            matches = actual == target
        else:
            try:
                matches = Counter(actual) == Counter(target)
            except TypeError:
                # Unhashable cell type (rare: BLOB-returning queries). Fall
                # back to sorted-list equality keyed on repr — slower but
                # robust. The dimensions in the v0.1 reference rubric all
                # return scalar columns, so this branch is defensive.
                matches = sorted(actual, key=repr) == sorted(target, key=repr)

        if matches:
            reason = (
                f"{len(actual)} row(s) match"
                + (" (ordered)" if order_matters else "")
            )
        else:
            reason = (
                f"got {len(actual)} row(s), expected {len(target)}"
                if len(actual) != len(target)
                else "row sets differ"
            )
        return make_score(
            context=context,
            evaluator_name=self.name,
            source_field=self.scores_field,
            raw_value={
                "query": candidate_output,
                "actual_rows": actual,
                "expected_rows": target,
                "order_matters": order_matters,
            },
            passed=matches,
            reason=reason,
        )


# SQLite authorizer action codes are integers; the named constants live on
# the sqlite3 module. SELECT (21) and READ (20) are the row-fetch path;
# FUNCTION (31) covers built-ins like COUNT/SUM/UPPER. TRANSACTION (22) is
# allowed because SQLite implicitly wraps SELECTs in a read transaction.
_ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_TRANSACTION,
}


def _select_only_authorizer(action: int, *_args: Any) -> int:
    """SQLite authorizer callback: permit reads, deny everything else.

    Returns SQLITE_OK for read actions, SQLITE_DENY for the rest. Denied
    actions raise `sqlite3.DatabaseError` at execute time, which the
    evaluator catches and reports as a SQL error.
    """
    return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY
