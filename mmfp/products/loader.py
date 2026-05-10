"""Product configuration loader.

Promoted from `mmfp/tests/conftest.py` (where it was introduced by MLI-173)
into a real module so the CLI (MLI-176) and the CI seed job (MLI-177) can
share it. Tests continue to consume it through the existing fixtures.

A product lives under ``${MMFP_PRODUCTS_DIR:-products}/<slug>/`` and contains
``rubric.yaml``, ``candidates.yaml``, and ``datasets/*.jsonl``. The JSONL
filename declares the tier (``tier_1.jsonl`` → ``tier_1``); keeping that out
of the row body keeps the dataset files ergonomic for hand-editing.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from mmfp.models.candidate import Candidate
from mmfp.models.dataset import Dataset, DatasetExample
from mmfp.models.rubric import Rubric


@dataclass(frozen=True)
class ProductConfig:
    """Everything the matrix engine needs to score a product end-to-end."""

    rubric: Rubric
    candidates: list[Candidate]
    datasets: list[Dataset]
    dimension_evaluators: Mapping[str, str]


def load_rubric(path: Path) -> Rubric:
    return Rubric.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def load_candidates(path: Path) -> list[Candidate]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Candidate.model_validate(c) for c in raw["candidates"]]


def load_datasets(directory: Path, *, slug: str) -> list[Dataset]:
    """Load every ``*.jsonl`` under ``directory`` as a :class:`Dataset`.

    ``slug`` namespaces the synthetic dataset ids (``<slug>-<tier_id>``) so
    different products can't collide on dataset identifiers.
    """
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
                id=f"{slug}-{tier_id}",
                name=f"{slug.upper()} {tier_id} golden set",
                description=f"Seed dataset for {slug.upper()} {tier_id}",
                version="v0.1",
                tier_id=tier_id,
                examples=examples,
            )
        )
    return out


def dimension_evaluators(rubric: Rubric) -> Mapping[str, str]:
    """Derive the engine-shaped mapping ``dimension_id -> evaluator_id``."""
    return {d.id: d.evaluator for tier in rubric.tiers for d in tier.dimensions}


def load_product(product_dir: Path) -> ProductConfig:
    """Load the rubric / candidates / datasets bundle for one product.

    Raises :class:`FileNotFoundError` if any of the three required artefacts
    is missing — that's the "unknown product" signal for callers (the CLI
    maps it to a non-zero exit).
    """
    rubric_path = product_dir / "rubric.yaml"
    candidates_path = product_dir / "candidates.yaml"
    datasets_dir = product_dir / "datasets"

    if not rubric_path.exists():
        raise FileNotFoundError(f"rubric.yaml not found at {rubric_path}")
    if not candidates_path.exists():
        raise FileNotFoundError(f"candidates.yaml not found at {candidates_path}")
    if not datasets_dir.is_dir():
        raise FileNotFoundError(f"datasets/ not found at {datasets_dir}")

    rubric = load_rubric(rubric_path)
    candidates = load_candidates(candidates_path)
    datasets = load_datasets(datasets_dir, slug=product_dir.name)
    return ProductConfig(
        rubric=rubric,
        candidates=candidates,
        datasets=datasets,
        dimension_evaluators=dimension_evaluators(rubric),
    )


__all__ = [
    "ProductConfig",
    "dimension_evaluators",
    "load_candidates",
    "load_datasets",
    "load_product",
    "load_rubric",
]
