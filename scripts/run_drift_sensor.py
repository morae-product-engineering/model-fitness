"""Drift sensor runner — invoked by .github/workflows/drift-sensor.yml (MFP-99).

For each candidate/tier in the product config, fetches live samples from
LangSmith, compares them against the latest baseline run, and writes any
drift signals as JSON files under MMFP_DRIFT_DIR.

Exit codes:
  0 — success, or deliberate clean skip (missing LANGSMITH_API_KEY / no baseline)
  1 — runtime error

SKIP conditions (exit 0):
  - LANGSMITH_API_KEY not set in environment
  - Seed database does not exist at MMFP_DB_PATH
  - No matrix runs for the product in the database
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

_DEFAULT_PRODUCTS_DIR = "products"
_DEFAULT_DB_PATH = "data/mmfp.db"
_DEFAULT_DRIFT_DIR = "data/drift"
_DEFAULT_PRODUCT = "mli"
_DEFAULT_LANGSMITH_PROJECT = "mmfp-drift-seed"


def _write_summary(msg: str) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    print(msg)


def _skip(reason: str) -> int:
    _write_summary(f"### Drift sensor skipped\n\n{reason}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run_drift_sensor")
    parser.add_argument("--product", default=_DEFAULT_PRODUCT)
    args = parser.parse_args(argv)

    # Skip cleanly when LangSmith API key is absent — expected before provisioning.
    api_key = os.environ.get("LANGSMITH_API_KEY")
    if not api_key:
        return _skip("`LANGSMITH_API_KEY` is not set — no live samples available.")

    db_path = Path(os.environ.get("MMFP_DB_PATH", _DEFAULT_DB_PATH))
    if not db_path.exists():
        return _skip(
            f"Seed database not found at `{db_path}`. "
            "Run `baseline-matrix.yml` first to seed the dev environment."
        )

    # Deferred imports: keeps the module-level import surface minimal and
    # lets the script exit early above without loading the full mmfp package.
    from mmfp.persistence import MatrixRunRepository
    from mmfp.products.loader import load_product
    from mmfp.sensors.drift import DriftSensor
    from mmfp.sensors.langsmith_sampler import LangSmithSampler

    products_dir = Path(os.environ.get("MMFP_PRODUCTS_DIR", _DEFAULT_PRODUCTS_DIR))
    try:
        config = load_product(products_dir / args.product)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    repo = MatrixRunRepository(db_path)
    runs = repo.list_for_product(args.product, limit=1)
    if not runs:
        return _skip(
            "No baseline runs found for product `{product}` in the database. "
            "Run `baseline-matrix.yml` first.".format(product=args.product)
        )

    baseline = runs[0]
    drift_dir = Path(os.environ.get("MMFP_DRIFT_DIR", _DEFAULT_DRIFT_DIR))
    langsmith_project = os.environ.get("LANGSMITH_PROJECT", _DEFAULT_LANGSMITH_PROJECT)

    sampler = LangSmithSampler(project_name=langsmith_project, api_key=api_key)
    signals_written: list[str] = []
    warnings: list[str] = []

    try:
        for candidate in config.candidates:
            for tier_id in candidate.tiers:
                sensor = DriftSensor(product_id=args.product)
                try:
                    live = sampler.fetch(candidate_id=candidate.id, tier_id=tier_id)
                    signal = sensor.detect(
                        candidate_id=candidate.id,
                        tier_id=tier_id,
                        baseline=baseline,
                        live_sample=live,
                    )
                    if signal is None:
                        continue
                    signals_dir = drift_dir / args.product / "signals"
                    signals_dir.mkdir(parents=True, exist_ok=True)
                    signal_id = uuid.uuid4().hex
                    (signals_dir / f"{signal_id}.json").write_text(
                        signal.model_dump_json(), encoding="utf-8"
                    )
                    signals_written.append(
                        f"{candidate.id}/{tier_id} → {signal.severity} "
                        f"(delta {float(signal.delta):+.1f})"
                    )
                except Exception as exc:  # noqa: BLE001
                    msg = f"{candidate.id}/{tier_id}: {type(exc).__name__}: {exc}"
                    warnings.append(msg)
                    print(f"warning: {msg}", file=sys.stderr)
    finally:
        sampler.close()

    summary_lines = [
        "### Drift sensor",
        "",
        f"- **Product:** `{args.product}`",
        f"- **Baseline run:** `{baseline.id}`",
        f"- **LangSmith project:** `{langsmith_project}`",
        f"- **Signals written:** {len(signals_written)}",
    ]
    if signals_written:
        summary_lines += ["", "**Signals detected:**"]
        summary_lines += [f"  - {s}" for s in signals_written]
    if warnings:
        summary_lines += ["", f"**Warnings ({len(warnings)}):**"]
        summary_lines += [f"  - {w}" for w in warnings]

    _write_summary("\n".join(summary_lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
