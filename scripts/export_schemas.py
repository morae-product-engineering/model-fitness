"""Export JSON Schemas for the v1 MMFP top-level data models.

Run from the repo root:

    python scripts/export_schemas.py

Writes one JSON file per top-level model under `schemas/v1/`. Schemas are the
boundary contract — UI typegen, persistence migrations, and external integrators
(future) read from `schemas/v1/`. Pydantic models are the runtime authority;
this script keeps the on-disk schemas in lock-step.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from mmfp.models import Candidate, Dataset, MatrixRun, Rubric

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "schemas" / "v1"

# Top-level persisted models. Plugin output / derived views (Scorecard,
# EvaluatorScore) are exported transitively as `$defs` inside MatrixRun, so
# downstream consumers see them without needing a second top-level file.
TOP_LEVEL_MODELS = [Rubric, Candidate, Dataset, MatrixRun]


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for model in TOP_LEVEL_MODELS:
        schema = model.model_json_schema()
        out_path = OUTPUT_DIR / f"{model.__name__.lower()}.json"
        out_path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
