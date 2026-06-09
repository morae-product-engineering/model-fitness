"""Dataset endpoints (MFP-75).

  GET  /api/products/{product}/datasets/{tier_id}
  POST /api/products/{product}/datasets/{tier_id}/examples

Examples are stored as JSONL at `products/<product>/datasets/<tier_id>.jsonl`.
Each line is a flat JSON object matching `DatasetExample`.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Annotated, Any
from collections.abc import Callable

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from mmfp.models.candidate import Candidate, TierId
from mmfp.models.dataset import DatasetExample

logger = logging.getLogger(__name__)

router = APIRouter(tags=["datasets"])

_PRODUCT_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_VALID_TIERS: frozenset[str] = frozenset(TierId.__args__)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class AddExampleRequest(BaseModel):
    id: str | None = Field(
        default=None,
        description="Stable id; server auto-generates a UUID hex8 if omitted",
    )
    input: dict[str, Any] | str = Field(
        description="String prompt or structured payload"
    )
    expected: Any = Field(description="Evaluator-specific expected outcome")
    tags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Dependency providers
# ---------------------------------------------------------------------------


def get_products_dir() -> Path:
    return Path(os.environ.get("MMFP_PRODUCTS_DIR", "products"))


def get_candidate_loader() -> Callable[[str], list[Candidate]]:
    products_dir = Path(os.environ.get("MMFP_PRODUCTS_DIR", "products"))

    def _load(product: str) -> list[Candidate]:
        slate_path = products_dir / product / "candidates.yaml"
        if not slate_path.exists():
            raise FileNotFoundError(f"candidates.yaml not found at {slate_path}")
        raw = yaml.safe_load(slate_path.read_text(encoding="utf-8"))
        return [Candidate.model_validate(c) for c in raw["candidates"]]

    return _load


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_product_and_tier(
    product: str,
    tier_id: str,
    candidate_loader: Callable[[str], list[Candidate]],
) -> None:
    if not _PRODUCT_SLUG_RE.match(product):
        raise HTTPException(status_code=404, detail=f"Unknown product '{product}'")
    if tier_id not in _VALID_TIERS:
        raise HTTPException(status_code=404, detail=f"Unknown tier '{tier_id}'")
    try:
        candidate_loader(product)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Unknown product '{product}'")


def _dataset_path(products_dir: Path, product: str, tier_id: str) -> Path:
    return products_dir / product / "datasets" / f"{tier_id}.jsonl"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/api/products/{product}/datasets/{tier_id}",
    response_model=list[DatasetExample],
    summary="List all examples in a dataset",
)
def list_examples(
    product: str,
    tier_id: str,
    products_dir: Annotated[Path, Depends(get_products_dir)],
    candidate_loader: Annotated[
        Callable[[str], list[Candidate]], Depends(get_candidate_loader)
    ],
) -> list[DatasetExample]:
    _validate_product_and_tier(product, tier_id, candidate_loader)
    path = _dataset_path(products_dir, product, tier_id)
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No dataset found for product '{product}', tier '{tier_id}'",
        )
    examples: list[DatasetExample] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            examples.append(DatasetExample.model_validate_json(line))
    return examples


@router.post(
    "/api/products/{product}/datasets/{tier_id}/examples",
    response_model=DatasetExample,
    status_code=201,
    summary="Add an example to a dataset",
)
def add_example(
    product: str,
    tier_id: str,
    body: AddExampleRequest,
    products_dir: Annotated[Path, Depends(get_products_dir)],
    candidate_loader: Annotated[
        Callable[[str], list[Candidate]], Depends(get_candidate_loader)
    ],
) -> DatasetExample:
    _validate_product_and_tier(product, tier_id, candidate_loader)
    path = _dataset_path(products_dir, product, tier_id)
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No dataset found for product '{product}', tier '{tier_id}'",
        )
    example = DatasetExample(
        id=body.id or uuid.uuid4().hex[:8],
        input=body.input,
        expected=body.expected,
        tags=body.tags,
    )
    with path.open("a", encoding="utf-8") as fh:
        fh.write(example.model_dump_json() + "\n")
    logger.info("added example %s to %s/%s", example.id, product, tier_id)
    return example
