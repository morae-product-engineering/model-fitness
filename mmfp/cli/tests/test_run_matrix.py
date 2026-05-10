# @jira: MLI-176 — CLI command for matrix run.
#
# Unit tests cover argparse shape. Integration tests drive
# ``mmfp run-matrix`` end-to-end against the real ``products/mli/`` config
# with a stub binding so no network is touched; persistence lands in a
# tmp-path SQLite file.

from __future__ import annotations

import io
from pathlib import Path

import pytest

from mmfp.cli.__main__ import build_parser, main
from mmfp.engine.matrix import MatrixEngine
from mmfp.persistence import MatrixRunRepository
from mmfp.tests.test_mli_product_config import _StubBinding

REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Argparse — unit tests
# ---------------------------------------------------------------------------


def test_parser_run_matrix_requires_product() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["run-matrix"])


def test_parser_run_matrix_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args(["run-matrix", "--product", "mli"])
    assert args.command == "run-matrix"
    assert args.product == "mli"
    assert args.rubric_version is None
    assert args.dry_run is False


def test_parser_run_matrix_with_dry_run_flag() -> None:
    parser = build_parser()
    args = parser.parse_args(["run-matrix", "--product", "mli", "--dry-run"])
    assert args.dry_run is True


def test_parser_run_matrix_with_rubric_version() -> None:
    parser = build_parser()
    args = parser.parse_args(
        ["run-matrix", "--product", "mli", "--rubric-version", "v0.1"]
    )
    assert args.rubric_version == "v0.1"


def test_parser_requires_a_subcommand() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


# ---------------------------------------------------------------------------
# run-matrix — integration tests
# ---------------------------------------------------------------------------


@pytest.fixture
def use_repo_products_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin MMFP_PRODUCTS_DIR to the repo's ``products/`` directory.

    pytest may be invoked from any cwd, so an absolute path keeps the tests
    robust without depending on the default ``products`` relative resolution.
    """
    monkeypatch.setenv("MMFP_PRODUCTS_DIR", str(REPO_ROOT / "products"))


def _stub_engine_factory() -> MatrixEngine:
    return MatrixEngine(
        binding_factory=lambda _provider: _StubBinding(),
        # Deterministic ordering, no thread-pool noise on a tiny matrix.
        max_workers=1,
    )


def test_run_matrix_persists_and_prints_run_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    use_repo_products_dir: None,
) -> None:
    """Happy path: real config + stub binding → persisted run, run_id stdout."""
    db_path = tmp_path / "mmfp.db"
    monkeypatch.setenv("MMFP_DB_PATH", str(db_path))

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = main(
        ["run-matrix", "--product", "mli"],
        engine_factory=_stub_engine_factory,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0, stderr.getvalue()
    out = stdout.getvalue()
    assert "run_id:" in out
    assert "rubric_version: v0.1" in out
    assert "per-tier candidate counts:" in out
    # All three tiers should have at least one candidate in the summary.
    assert "tier_1:" in out
    assert "tier_2:" in out
    assert "tier_3:" in out

    run_id = next(
        line.split(":", 1)[1].strip()
        for line in out.splitlines()
        if line.startswith("run_id:")
    )
    assert run_id

    persisted = MatrixRunRepository(db_path).get(run_id)
    assert persisted is not None, "CLI did not persist the run"
    assert persisted.results, "persisted run has no results"


def test_run_matrix_dry_run_prints_plan_without_invoking_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    use_repo_products_dir: None,
) -> None:
    """``--dry-run`` validates config and prints the plan but never builds an engine."""
    db_path = tmp_path / "should_not_be_created.db"
    monkeypatch.setenv("MMFP_DB_PATH", str(db_path))

    def bomb_engine() -> MatrixEngine:
        raise AssertionError("dry-run must not construct an engine")

    def bomb_repository(_path: Path) -> MatrixRunRepository:
        raise AssertionError("dry-run must not construct a repository")

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = main(
        ["run-matrix", "--product", "mli", "--dry-run"],
        engine_factory=bomb_engine,
        repository_factory=bomb_repository,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0, stderr.getvalue()
    out = stdout.getvalue()
    assert "DRY RUN" in out
    assert "product='mli'" in out
    assert "candidates" in out
    assert "datasets" in out
    assert "dimensions per tier" in out
    assert "no models will be invoked." in out
    # And we never touched the DB.
    assert not db_path.exists()


def test_run_matrix_unknown_product_exits_non_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unknown product slug exits non-zero with a useful stderr message."""
    # Empty products dir → no product directory exists.
    monkeypatch.setenv("MMFP_PRODUCTS_DIR", str(tmp_path))

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = main(
        ["run-matrix", "--product", "does-not-exist"],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code != 0
    err = stderr.getvalue()
    assert "does-not-exist" in err
    assert "unknown product" in err.lower()


def test_run_matrix_rubric_version_mismatch_exits_non_zero(
    monkeypatch: pytest.MonkeyPatch,
    use_repo_products_dir: None,
) -> None:
    """Explicit ``--rubric-version`` mismatch aborts before the engine runs."""

    def bomb_engine() -> MatrixEngine:
        raise AssertionError("version mismatch should abort before engine is built")

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = main(
        ["run-matrix", "--product", "mli", "--rubric-version", "v99.9"],
        engine_factory=bomb_engine,
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code != 0
    err = stderr.getvalue()
    assert "v99.9" in err
    assert "v0.1" in err
