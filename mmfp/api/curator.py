"""Dataset and judge-queue API endpoints (MFP-75).

Routes:
  GET  /api/products/{product}/datasets/{tier_id}
       List all examples in a tier's JSONL dataset file.

  POST /api/products/{product}/datasets/{tier_id}/examples
       Append one validated DatasetExample to the tier's JSONL file.

  GET  /api/products/{product}/judge-queue?status={pending|reviewed}
       List judge samples from the product's judge_samples.jsonl.
       Samples without a `status` field are treated as `pending`.

  POST /api/products/{product}/judge-queue/{sample_id}/mark
       Record a human decision (agree|disagree) on one judge sample.
       Rewrites the JSONL in place — acceptable at current single-replica,
       small-file scale. A distributed lock or blob ETag would be the
       fast-follow for multi-replica deployments.

Product validation: the product directory must exist under MMFP_PRODUCTS_DIR.
If not, all four endpoints return 404. This mirrors the "unknown product"
signal used elsewhere (scoreboard.py, rubric_write.py).

Dataset file path convention:
  products/<product>/datasets/<tier_id>.jsonl
This matches the loader in mmfp/products/loader.py. A GET on a non-existent
tier file returns 200 with an empty list — the file may not yet exist.

Judge queue file path:
  products/<product>/judge_samples.jsonl
This is the same file the LLMJudgeEvaluator (MFP-74) appends to. Samples
emitted by that evaluator carry no `status` field; the read path normalises
missing status to "pending" so existing data is correctly categorised.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from mmfp.models.dataset import DatasetExample

logger = logging.getLogger(__name__)

router = APIRouter(tags=["curator"])

# Status literals accepted by the judge-queue filter and mark endpoints.
_JudgeStatus = Literal["pending", "reviewed"]

# Default samples sentinel for missing status field (MFP-74 evaluator does not
# write a status field; we normalise it here rather than patching the evaluator).
_DEFAULT_STATUS = "pending"


# ---------------------------------------------------------------------------
# Dependency provider
# ---------------------------------------------------------------------------


def get_products_dir() -> Path:
    """Provide the products root from MMFP_PRODUCTS_DIR (or default `products/`).

    The wiring layer owns env-var resolution, matching the ADR-0001 pattern
    established in scoreboard.py. Tests override this symbol via
    app.dependency_overrides.
    """
    return Path(os.environ.get("MMFP_PRODUCTS_DIR", "products"))


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class DatasetListResponse(BaseModel):
    product: str
    tier_id: str
    examples: list[DatasetExample]


class JudgeSample(BaseModel):
    """One judge sample from judge_samples.jsonl, with normalised status."""

    sample_id: str
    run_id: str
    dimension_id: str
    candidate_id: str
    candidate_output: str
    judge_score: float
    judge_reasoning: str
    judge_confidence: str
    created_at: str
    status: str = Field(default=_DEFAULT_STATUS)
    decision: str | None = Field(default=None)
    note: str | None = Field(default=None)


class JudgeQueueResponse(BaseModel):
    product: str
    samples: list[JudgeSample]


class MarkRequest(BaseModel):
    decision: Literal["agree", "disagree"]
    note: str | None = Field(default=None)


class MarkResponse(BaseModel):
    sample_id: str
    status: str
    decision: str
    note: str | None = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _product_dir(products_root: Path, product: str) -> Path:
    """Resolve the product directory and raise 404 if it doesn't exist."""
    path = products_root / product
    if not path.is_dir():
        raise HTTPException(status_code=404, detail=f"Unknown product '{product}'")
    return path


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL file into a list of dicts; returns [] if the file is absent."""
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Overwrite a JSONL file with `rows`, one JSON object per line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    """Append one JSON object as a new line; creates the file if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/api/products/{product}/datasets/{tier_id}",
    response_model=DatasetListResponse,
    summary="List examples in a dataset tier",
)
def list_examples(
    product: str,
    tier_id: str,
    products_dir: Annotated[Path, Depends(get_products_dir)],
) -> DatasetListResponse:
    """Return all examples from `products/<product>/datasets/<tier_id>.jsonl`.

    404 if the product directory doesn't exist.
    200 with an empty list if the tier file doesn't exist yet.
    """
    prod_dir = _product_dir(products_dir, product)
    tier_file = prod_dir / "datasets" / f"{tier_id}.jsonl"

    raw_rows = _read_jsonl(tier_file)
    examples = [DatasetExample.model_validate(row) for row in raw_rows]

    logger.info(
        "curator.dataset.list",
        extra={"product": product, "tier_id": tier_id, "count": len(examples)},
    )
    return DatasetListResponse(product=product, tier_id=tier_id, examples=examples)


@router.post(
    "/api/products/{product}/datasets/{tier_id}/examples",
    response_model=DatasetExample,
    status_code=201,
    summary="Add an example to a dataset tier",
)
def add_example(
    product: str,
    tier_id: str,
    example: DatasetExample,
    products_dir: Annotated[Path, Depends(get_products_dir)],
) -> DatasetExample:
    """Validate and append one example to `products/<product>/datasets/<tier_id>.jsonl`.

    404 if the product directory doesn't exist.
    422 if the body fails DatasetExample validation.
    201 with the stored example on success.

    ASSUMES: the caller supplies a unique `id`; duplicates are not checked.
    The dataset is append-only (edit is out of scope per MFP-75 brief).
    """
    prod_dir = _product_dir(products_dir, product)
    tier_file = prod_dir / "datasets" / f"{tier_id}.jsonl"

    # model_dump(mode="json") serialises Any fields correctly (e.g. dicts).
    _append_jsonl(tier_file, example.model_dump(mode="json"))

    logger.info(
        "curator.dataset.add_example",
        extra={"product": product, "tier_id": tier_id, "example_id": example.id},
    )
    return example


@router.get(
    "/api/products/{product}/judge-queue",
    response_model=JudgeQueueResponse,
    summary="List judge samples for human calibration review",
)
def list_judge_queue(
    product: str,
    products_dir: Annotated[Path, Depends(get_products_dir)],
    status: _JudgeStatus | None = None,
) -> JudgeQueueResponse:
    """Return judge samples from `products/<product>/judge_samples.jsonl`.

    Query params:
      status — filter to `pending` or `reviewed`. Absent → return all.

    Samples written by LLMJudgeEvaluator (MFP-74) lack a `status` field;
    they are normalised to `pending` at read time.

    404 if the product directory doesn't exist.
    200 with empty list if the queue file doesn't exist yet.
    422 if `status` is not "pending" or "reviewed" (FastAPI enum validation).
    """
    prod_dir = _product_dir(products_dir, product)
    queue_file = prod_dir / "judge_samples.jsonl"

    raw_rows = _read_jsonl(queue_file)
    samples: list[JudgeSample] = []
    for row in raw_rows:
        # Normalise missing status to the default before filtering.
        if "status" not in row:
            row = {**row, "status": _DEFAULT_STATUS}
        sample = JudgeSample.model_validate(row)
        if status is None or sample.status == status:
            samples.append(sample)

    logger.info(
        "curator.judge_queue.list",
        extra={"product": product, "status_filter": status, "count": len(samples)},
    )
    return JudgeQueueResponse(product=product, samples=samples)


@router.post(
    "/api/products/{product}/judge-queue/{sample_id}/mark",
    response_model=MarkResponse,
    summary="Record a human decision on a judge sample",
)
def mark_sample(
    product: str,
    sample_id: str,
    payload: MarkRequest,
    products_dir: Annotated[Path, Depends(get_products_dir)],
) -> MarkResponse:
    """Record a human `agree` or `disagree` decision on one judge sample.

    Finds the sample by `sample_id`, updates its `status` to "reviewed",
    records `decision` and optional `note`, then rewrites the JSONL file.

    404 if the product doesn't exist or the sample_id is not found.
    422 if `decision` is not "agree" or "disagree".

    Implementation note: full file rewrite is acceptable at current scale
    (single replica, small per-product queue). A blob-level CAS lock would
    be the fast-follow for multi-replica deployments.
    """
    prod_dir = _product_dir(products_dir, product)
    queue_file = prod_dir / "judge_samples.jsonl"

    rows = _read_jsonl(queue_file)

    # Find the sample; normalise status on load.
    target_idx: int | None = None
    for i, row in enumerate(rows):
        if row.get("sample_id") == sample_id:
            target_idx = i
            break

    if target_idx is None:
        raise HTTPException(
            status_code=404,
            detail=f"Judge sample '{sample_id}' not found in product '{product}'",
        )

    # Mutate the row in place (new dict to avoid aliasing).
    updated_row = {
        **rows[target_idx],
        "status": "reviewed",
        "decision": payload.decision,
        "note": payload.note,
    }
    rows[target_idx] = updated_row

    _write_jsonl(queue_file, rows)

    logger.info(
        "curator.judge_queue.mark",
        extra={
            "product": product,
            "sample_id": sample_id,
            "decision": payload.decision,
        },
    )

    return MarkResponse(
        sample_id=sample_id,
        status="reviewed",
        decision=payload.decision,
        note=payload.note,
    )
