"""mmfp CLI — entry point for ``mmfp <command>`` and ``python -m mmfp.cli``.

Commands
--------
``run-matrix --product <slug> [--rubric-version <v>] [--dry-run]``
    Load the product's rubric, candidate slate, and golden datasets, run the
    matrix engine end-to-end, persist the :class:`MatrixRun` to SQLite, and
    print ``run_id`` + per-tier candidate counts. ``--dry-run`` validates
    config and prints the plan without invoking any models.

Env vars
--------
``MMFP_PRODUCTS_DIR`` — products root (default ``products``). Same convention
introduced by MLI-174 (scoreboard API) and ADR-0001.
``MMFP_DB_PATH`` — SQLite file the repository writes to (default
``data/mmfp.db``). Same convention introduced by MLI-258.

Streams
-------
Logging goes to stderr; the human summary goes to stdout so callers can pipe
or grep it without log noise.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TextIO

from mmfp.engine.matrix import MatrixEngine
from mmfp.models.matrix_run import MatrixRun
from mmfp.persistence import MatrixRunRepository
from mmfp.products.loader import ProductConfig, load_product

logger = logging.getLogger(__name__)

_DEFAULT_PRODUCTS_DIR = "products"
_DEFAULT_DB_PATH = "data/mmfp.db"

# Exit codes:
#   0 — success (including dry-run)
#   1 — runtime failure during the engine run
#   2 — usage error (unknown product, version mismatch, missing args)
_EXIT_OK = 0
_EXIT_RUNTIME = 1
_EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mmfp",
        description="Morae Model Fitness Platform CLI",
    )
    subs = parser.add_subparsers(dest="command", required=True)

    run_matrix = subs.add_parser(
        "run-matrix",
        help="Run a matrix against a product's rubric and golden datasets",
    )
    run_matrix.add_argument(
        "--product",
        required=True,
        help="Product slug (subdirectory under MMFP_PRODUCTS_DIR / 'products')",
    )
    run_matrix.add_argument(
        "--rubric-version",
        default=None,
        help=(
            "Expected rubric version. Defaults to whatever the product's "
            "rubric.yaml declares; if supplied and the rubric disagrees, "
            "the run aborts before any model is called."
        ),
    )
    run_matrix.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config and print the plan; do not invoke models",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    engine_factory: Callable[[], MatrixEngine] | None = None,
    repository_factory: Callable[[Path], MatrixRunRepository] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Parse ``argv``, dispatch, return the exit code.

    The factory hooks let tests inject a stub-binding engine and an in-tmp
    repository without monkeypatching module globals. Real CLI use leaves
    them at the production defaults.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr

    if args.command == "run-matrix":
        return _run_matrix(
            product=args.product,
            rubric_version=args.rubric_version,
            dry_run=args.dry_run,
            engine_factory=engine_factory or MatrixEngine,
            repository_factory=repository_factory or MatrixRunRepository,
            stdout=out,
            stderr=err,
        )

    # argparse ``required=True`` should have already short-circuited.
    parser.print_usage(err)
    return _EXIT_USAGE


def _run_matrix(
    *,
    product: str,
    rubric_version: str | None,
    dry_run: bool,
    engine_factory: Callable[[], MatrixEngine],
    repository_factory: Callable[[Path], MatrixRunRepository],
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    products_dir = Path(os.environ.get("MMFP_PRODUCTS_DIR", _DEFAULT_PRODUCTS_DIR))
    product_dir = products_dir / product

    try:
        config = load_product(product_dir)
    except FileNotFoundError as exc:
        logger.error(
            "Unknown product",
            extra={"product": product, "products_dir": str(products_dir)},
        )
        print(f"error: unknown product '{product}' — {exc}", file=stderr)
        return _EXIT_USAGE

    if rubric_version is not None and rubric_version != config.rubric.version:
        logger.error(
            "Rubric version mismatch",
            extra={
                "product": product,
                "requested": rubric_version,
                "found": config.rubric.version,
            },
        )
        print(
            f"error: rubric version mismatch — requested {rubric_version}, "
            f"product '{product}' declares {config.rubric.version}",
            file=stderr,
        )
        return _EXIT_USAGE

    if dry_run:
        _print_plan(config, product=product, out=stdout)
        return _EXIT_OK

    db_path = Path(os.environ.get("MMFP_DB_PATH", _DEFAULT_DB_PATH))
    repository = repository_factory(db_path)
    engine = engine_factory()

    logger.info(
        "Starting matrix run",
        extra={
            "product": product,
            "rubric_version": config.rubric.version,
            "candidates": len(config.candidates),
            "datasets": len(config.datasets),
            "db_path": str(db_path),
        },
    )
    try:
        run = engine.run(
            rubric=config.rubric,
            datasets=config.datasets,
            candidates=config.candidates,
            dimension_evaluators=config.dimension_evaluators,
            repository=repository,
            product=product,
        )
    except Exception as exc:  # noqa: BLE001 — CLI top-level boundary
        logger.exception("Matrix run failed", extra={"product": product})
        print(f"error: matrix run failed — {type(exc).__name__}: {exc}", file=stderr)
        return _EXIT_RUNTIME

    logger.info(
        "Matrix run complete",
        extra={"run_id": run.id, "results": len(run.results)},
    )
    _print_summary(run, product=product, out=stdout)
    return _EXIT_OK


def _print_plan(config: ProductConfig, *, product: str, out: TextIO) -> None:
    print(f"DRY RUN — product='{product}' rubric='{config.rubric.version}'", file=out)
    print(f"  candidates ({len(config.candidates)}):", file=out)
    for cand in config.candidates:
        tiers = ", ".join(sorted(cand.tiers))
        print(f"    - {cand.id} [{cand.family.value}] tiers={tiers}", file=out)
    print(f"  datasets ({len(config.datasets)}):", file=out)
    for ds in config.datasets:
        print(f"    - {ds.id} tier={ds.tier_id} examples={len(ds.examples)}", file=out)
    print("  dimensions per tier:", file=out)
    for tier in config.rubric.tiers:
        print(f"    - {tier.id}: {len(tier.dimensions)} dimensions", file=out)
    print("  no models will be invoked.", file=out)


def _print_summary(run: MatrixRun, *, product: str, out: TextIO) -> None:
    per_tier_candidates: dict[str, set[str]] = {}
    for result in run.results:
        per_tier_candidates.setdefault(result.tier_id, set()).add(result.candidate_id)

    print(f"run_id: {run.id}", file=out)
    print(f"product: {product}", file=out)
    print(f"rubric_version: {run.rubric_version}", file=out)
    print(f"results: {len(run.results)}", file=out)
    print("per-tier candidate counts:", file=out)
    for tier_id in sorted(per_tier_candidates):
        print(f"  {tier_id}: {len(per_tier_candidates[tier_id])}", file=out)


def entry() -> None:
    """Console-script entry point declared in ``pyproject.toml``."""
    logging.basicConfig(
        stream=sys.stderr,
        level=os.environ.get("MMFP_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    sys.exit(main(sys.argv[1:]))


if __name__ == "__main__":
    entry()
