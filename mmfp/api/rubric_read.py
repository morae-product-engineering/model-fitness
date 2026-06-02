"""Rubric read endpoint — GET /api/products/{product}/rubric (MLI-195).

Read-only counterpart to the PUT endpoint in ``rubric_write.py`` (MLI-273,
reconciled in MLI-194). Added in MLI-195 because the UI container cannot
read the YAML directly (it talks to the API over HTTP) and no GET for the
full rubric dict existed.

Architectural context (MLI-190 normalisation-boundary note):
  The Editor needs the full rubric dict — including ``evaluator_config``
  and ``gates`` — so it can POST the dict verbatim to preview-impact and
  PUT it verbatim to the write endpoint. Returning ``model_dump(mode="json")``
  round-trips cleanly through ``Rubric.model_validate`` because the model
  uses ``extra="forbid"``, which means the serialised form is exactly the
  schema the write endpoint expects.

The dependency ``get_rubric_loader`` is defined here locally (not imported
from another endpoint) so tests can override it independently — the same
pattern used in ``rubric_preview.py``.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from mmfp.models.rubric import Rubric
from mmfp.products.loader import load_rubric

router = APIRouter(tags=["rubric"])


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


class RubricReadResponse(BaseModel):
    product: str
    version: str
    rubric: dict[str, Any]


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


def get_rubric_loader() -> Callable[[str], Rubric]:
    """Provide a callable that loads a product's current rubric from disk.

    Reads ``${MMFP_PRODUCTS_DIR:-products}/<product>/rubric.yaml`` via
    ``load_rubric``.  Raises ``FileNotFoundError`` for unknown products
    (mapped to 404 by the route). Defined locally so tests can override
    this dependency independently of the preview and write endpoints.
    """
    products_dir = Path(os.environ.get("MMFP_PRODUCTS_DIR", "products"))

    def _load(product: str) -> Rubric:
        rubric_path = products_dir / product / "rubric.yaml"
        if not rubric_path.exists():
            raise FileNotFoundError(f"rubric.yaml not found at {rubric_path}")
        return load_rubric(rubric_path)

    return _load


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.get(
    "/api/products/{product}/rubric",
    response_model=RubricReadResponse,
    summary="Read a product's current rubric",
)
def get_rubric(
    product: str,
    rubric_loader: Annotated[Callable[[str], Rubric], Depends(get_rubric_loader)],
) -> RubricReadResponse:
    """Return the full rubric dict for ``product``.

    The ``rubric`` field is serialised via ``model_dump(mode="json")`` so it
    round-trips through ``Rubric.model_validate`` cleanly — the Editor posts
    this dict straight back to preview-impact and PUT without re-serialising
    field-by-field (which would drop ``evaluator_config`` and other
    passthrough fields).

    Error states:
      * 404 — product's ``rubric.yaml`` doesn't exist (unknown product).
    """
    try:
        rubric = rubric_loader(product)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Unknown product '{product}'")

    return RubricReadResponse(
        product=product,
        version=rubric.version,
        rubric=rubric.model_dump(mode="json"),
    )
