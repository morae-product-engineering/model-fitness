# @jira: MLI-173 (populates the YAML / JSONL fixtures the slice acceptance
#         test consumes), MLI-168 / MLI-169 (original fixture introduction).
#
# Loads real `products/mli/` configuration into Pydantic models so the slice
# acceptance test can drive the matrix engine end-to-end. JSONL datasets hold
# one `DatasetExample` per line — the file's tier_id comes from the filename
# (`tier_1.jsonl` etc.), which the loader reads to assemble the wrapping
# `Dataset`. Per-file dataset metadata kept implicit in the filename keeps
# the JSONL ergonomic for hand-editing.

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest
import yaml

from mmfp.models.candidate import Candidate
from mmfp.models.dataset import Dataset, DatasetExample
from mmfp.models.rubric import Rubric

REPO_ROOT = Path(__file__).resolve().parents[2]
MLI_PRODUCT_DIR = REPO_ROOT / "products" / "mli"


def _load_rubric(path: Path) -> Rubric:
    return Rubric.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _load_candidates(path: Path) -> list[Candidate]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Candidate.model_validate(c) for c in raw["candidates"]]


def _load_datasets(directory: Path) -> list[Dataset]:
    files = sorted(p for p in directory.iterdir() if p.is_file() and p.suffix == ".jsonl")
    if not files:
        raise FileNotFoundError(f"no JSONL dataset files under {directory}")
    out: list[Dataset] = []
    for path in files:
        tier_id = path.stem  # `tier_1.jsonl` → `tier_1`
        examples = [
            DatasetExample.model_validate(json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        out.append(
            Dataset(
                id=f"mli-{tier_id}",
                name=f"MLI {tier_id} golden set",
                description=f"Seed dataset for MLI {tier_id}",
                version="v0.1",
                tier_id=tier_id,
                examples=examples,
            )
        )
    return out


@pytest.fixture
def real_rubric() -> Rubric:
    return _load_rubric(MLI_PRODUCT_DIR / "rubric.yaml")


@pytest.fixture
def real_dataset() -> list[Dataset]:
    return _load_datasets(MLI_PRODUCT_DIR / "datasets")


@pytest.fixture
def real_candidates() -> list[Candidate]:
    return _load_candidates(MLI_PRODUCT_DIR / "candidates.yaml")


@pytest.fixture
def real_dimension_evaluators(real_rubric: Rubric) -> Mapping[str, str]:
    """Engine-shaped mapping derived from the rubric model."""
    return {d.id: d.evaluator for tier in real_rubric.tiers for d in tier.dimensions}
