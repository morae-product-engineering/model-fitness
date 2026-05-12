"""Seed the dev SQLite DB with N back-dated MatrixRuns (MLI-183).

Trends UI needs more than one run to render a trend line. The single
:file:`baseline-matrix.yml` workflow only emits one row per invocation; this
script drives the same engine multiple times into a single
``data/mmfp.db`` so the dev environment ships with a believable run history
the moment ``MLI-184`` lands.

How it differs from the baseline workflow
-----------------------------------------
* Same matrix engine, same rubric, same datasets — runs are *real* Foundry
  output, not fabricated. The MLI-183 AC is explicit on that point.
* Varies *run timing only* (back-dated ``created_at``/``started_at``/
  ``completed_at``), not rubric weights. Varying weights would commit
  seed-only edits to the tracked ``rubric.yaml``; a flat trend over a
  stable rubric is enough for trend-strip visualisation.
* Skips ``phi-4-mini-instruct`` by default. MLI-178 measured that
  deployment at 4–14 min per call versus ~7s for the other nine candidates,
  so including it in the seed triples wall-clock and spend with no signal
  benefit — trends are for visualising movement, not for portfolio
  decisions. Pass ``--include-phi-4-mini`` to seed the full slate.

Usage
-----
Local invocation, against a fresh ``data/mmfp.db``::

    export FOUNDRY_ACCOUNT_KEY=$(az keyvault secret show \\
        --vault-name kv-uks-mmfp-dev --name foundry-account-key \\
        --query value -o tsv)
    python scripts/seed_dev_runs.py

Re-seed (wipe existing runs for the product, then run three fresh ones)::

    python scripts/seed_dev_runs.py --reset

After the local DB is built, upload it to the dev seed blob the same way
``baseline-matrix.yml`` does (``az storage blob upload --overwrite``) and
rotate ``MMFP_SEED_BLOB_URL`` on ``ca-mmfp-api-dev``.

Idempotency
-----------
Default behaviour refuses to re-seed if the target product already has
``>= len(_OFFSETS_DAYS)`` runs in the DB. ``--reset`` purges those rows
first and then runs the seeds afresh. Either path satisfies the MLI-183
"idempotent or ``--reset``" AC.
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mmfp.engine.matrix import MatrixEngine
from mmfp.models.candidate import Candidate
from mmfp.persistence import MatrixRunRepository
from mmfp.products.loader import load_product

logger = logging.getLogger(__name__)

# Phi-4-mini-instruct is the slate's latency outlier (MLI-178: 4–14 min vs
# ~7s for the other nine). Including it in three full runs would push the
# seed past 90 min wall-clock; skipping it lands the same trend signal in
# ~10–15 min at proportionally lower Foundry spend. Override with
# --include-phi-4-mini when a full-slate historical baseline is genuinely
# wanted (e.g. before evaluating a Phi-class replacement).
_DEFAULT_SKIPPED_CANDIDATES = frozenset({"phi-4-mini-instruct"})

# Three runs over four weeks. The AC requires ≥2 distinct weeks for trend
# visualisation; 14-day cadence gives clean separation without painting
# more history than the rubric/slate actually justify.
_OFFSETS_DAYS = (28, 14, 0)

_DEFAULT_PRODUCT = "mli"
_DEFAULT_DB_PATH = Path(os.environ.get("MMFP_DB_PATH", "data/mmfp.db"))
_DEFAULT_PRODUCTS_DIR = Path(os.environ.get("MMFP_PRODUCTS_DIR", "products"))


def _utc_anchor() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _filter_candidates(
    candidates: Iterable[Candidate], *, skip: frozenset[str]
) -> list[Candidate]:
    return [c for c in candidates if c.id not in skip]


def _existing_run_count(repository: MatrixRunRepository, product: str) -> int:
    # list_for_product walks via get() per row, which is fine at seed scale
    # (three rows) but pulls the full payload. A direct COUNT would be
    # cheaper; this stays on the public API to avoid touching the repo.
    return len(repository.list_for_product(product, limit=1000))


def _reset_product(db_path: Path, product: str) -> int:
    """Delete all rows for ``product``. FK CASCADE handles run_results."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.execute(
            "DELETE FROM matrix_runs WHERE product = ?", (product,)
        )
        return cur.rowcount


def _backdate_run(
    db_path: Path,
    *,
    run_id: str,
    started_at: datetime,
    completed_at: datetime,
) -> None:
    """Rewrite the engine's wall-clock timestamps to the back-dated anchor.

    The repository's INSERT stamps ``created_at`` server-side via
    ``strftime('now')`` and copies ``started_at``/``completed_at`` from the
    model. To make the row look genuinely historical we rewrite all three
    in a single UPDATE. ``list_for_product`` orders by ``created_at DESC``,
    so the back-date is what the API/UI will see in any per-product sort.
    """
    started_iso = started_at.isoformat()
    completed_iso = completed_at.isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE matrix_runs
               SET started_at   = ?,
                   completed_at = ?,
                   created_at   = ?
             WHERE id = ?
            """,
            (started_iso, completed_iso, started_iso, run_id),
        )


def seed(
    *,
    product: str,
    db_path: Path,
    products_dir: Path,
    reset: bool,
    include_phi_4_mini: bool,
) -> int:
    config = load_product(products_dir / product)
    repository = MatrixRunRepository(db_path)

    existing = _existing_run_count(repository, product)
    if existing >= len(_OFFSETS_DAYS) and not reset:
        logger.warning(
            "Dev DB already has %d runs for product %s; pass --reset to re-seed",
            existing,
            product,
        )
        return 0
    if reset:
        deleted = _reset_product(db_path, product)
        logger.info(
            "Reset: deleted %d existing rows for product %s", deleted, product
        )

    skipped = frozenset() if include_phi_4_mini else _DEFAULT_SKIPPED_CANDIDATES
    if skipped:
        logger.info(
            "Skipping candidates for seed: %s (rationale in module docstring)",
            sorted(skipped),
        )
    candidates = _filter_candidates(config.candidates, skip=skipped)
    if not candidates:
        logger.error("No candidates left after filter; aborting")
        return 1

    anchor = _utc_anchor()
    written: list[tuple[str, str]] = []
    for index, offset_days in enumerate(_OFFSETS_DAYS, start=1):
        run_anchor = anchor - timedelta(days=offset_days)
        logger.info(
            "Seed run %d/%d: candidates=%d anchor=%s",
            index,
            len(_OFFSETS_DAYS),
            len(candidates),
            run_anchor.isoformat(),
        )
        engine = MatrixEngine()
        run = engine.run(
            rubric=config.rubric,
            datasets=config.datasets,
            candidates=candidates,
            dimension_evaluators=config.dimension_evaluators,
            repository=repository,
            product=product,
        )
        elapsed = (
            (run.completed_at - run.started_at)
            if run.completed_at is not None
            else timedelta(0)
        )
        _backdate_run(
            db_path,
            run_id=run.id,
            started_at=run_anchor,
            completed_at=run_anchor + elapsed,
        )
        written.append((run.id, run_anchor.isoformat()))
        logger.info("Persisted run %s back-dated to %s", run.id, run_anchor.isoformat())

    logger.info("Done. Wrote %d runs:", len(written))
    for run_id, when in written:
        logger.info("  - %s @ %s", run_id, when)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seed_dev_runs",
        description=(
            "Drive the matrix engine N times into a single SQLite, back-date "
            "the resulting rows, and write a believable dev run history."
        ),
    )
    parser.add_argument(
        "--product",
        default=_DEFAULT_PRODUCT,
        help="Product slug (default: %(default)s)",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=_DEFAULT_DB_PATH,
        help="SQLite path (default from $MMFP_DB_PATH or %(default)s)",
    )
    parser.add_argument(
        "--products-dir",
        type=Path,
        default=_DEFAULT_PRODUCTS_DIR,
        help="Products directory (default from $MMFP_PRODUCTS_DIR or %(default)s)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe existing runs for the product before seeding",
    )
    parser.add_argument(
        "--include-phi-4-mini",
        action="store_true",
        help=(
            "Override the default skip and include phi-4-mini-instruct in the "
            "seed (expensive — see module docstring)."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        stream=sys.stderr,
        level=os.environ.get("MMFP_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = _build_parser().parse_args(argv)
    return seed(
        product=args.product,
        db_path=args.db_path,
        products_dir=args.products_dir,
        reset=args.reset,
        include_phi_4_mini=args.include_phi_4_mini,
    )


if __name__ == "__main__":
    sys.exit(main())
