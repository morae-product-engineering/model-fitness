# @jira: MLI-168
# Slice 2 acceptance fixtures. Load real rubric, dataset, and candidate
# definitions from products/mli/. They will not yet exist (subtask 2.8 will
# populate them), so these fixtures are expected to raise FileNotFoundError
# until the slice converges.

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MLI_PRODUCT_DIR = REPO_ROOT / "products" / "mli"


@pytest.fixture
def real_rubric():
    path = MLI_PRODUCT_DIR / "rubric.yaml"
    return path.read_text(encoding="utf-8")


@pytest.fixture
def real_dataset():
    path = MLI_PRODUCT_DIR / "datasets"
    files = sorted(p for p in path.iterdir() if p.is_file() and p.suffix in {".jsonl", ".json"})
    if not files:
        raise FileNotFoundError(f"no dataset files under {path}")
    return [p.read_text(encoding="utf-8") for p in files]


@pytest.fixture
def real_candidates():
    path = MLI_PRODUCT_DIR / "candidates.yaml"
    return path.read_text(encoding="utf-8")
