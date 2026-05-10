# @jira: MLI-173 (populates the YAML / JSONL fixtures the slice acceptance
#         test consumes), MLI-168 / MLI-169 (original fixture introduction),
#         MLI-176 (loader promoted to mmfp/products/loader.py; these fixtures
#         now thin-wrap it so the CLI and tests share one parser).
#
# Loads real `products/mli/` configuration into Pydantic models so the slice
# acceptance test can drive the matrix engine end-to-end.

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from mmfp.models.candidate import Candidate
from mmfp.models.dataset import Dataset
from mmfp.models.rubric import Rubric
from mmfp.products.loader import (
    dimension_evaluators,
    load_candidates,
    load_datasets,
    load_rubric,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MLI_PRODUCT_DIR = REPO_ROOT / "products" / "mli"


@pytest.fixture
def real_rubric() -> Rubric:
    return load_rubric(MLI_PRODUCT_DIR / "rubric.yaml")


@pytest.fixture
def real_dataset() -> list[Dataset]:
    return load_datasets(MLI_PRODUCT_DIR / "datasets", slug="mli")


@pytest.fixture
def real_candidates() -> list[Candidate]:
    return load_candidates(MLI_PRODUCT_DIR / "candidates.yaml")


@pytest.fixture
def real_dimension_evaluators(real_rubric: Rubric) -> Mapping[str, str]:
    """Engine-shaped mapping derived from the rubric model."""
    return dimension_evaluators(real_rubric)
