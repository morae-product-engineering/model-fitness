"""Minimal FastAPI application for the MMFP walking skeleton (MLI-160).

Exposes /health and /api/runs/skeleton. No auth yet — that comes in a later slice.
"""

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(
    title="MMFP API",
    description="Morae Model Fitness Platform API",
    version="0.0.1",
)


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str = Field(description="Service liveness indicator")


class MatrixRunResponse(BaseModel):
    """Skeleton MatrixRun returned before real evaluation is wired (MLI-160).

    Fields are deliberately minimal — enough to prove the API ↔ UI path works.
    """

    tier: str = Field(description="Evaluation tier identifier")
    candidate: str = Field(description="Model candidate identifier")
    weighted_score: int = Field(description="Weighted aggregate score (0–100)")
    source: str = Field(description="Indicates data provenance")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness probe — used by the container orchestrator and CI smoke tests."""
    return HealthResponse(status="ok")


@app.get("/api/runs/skeleton", response_model=MatrixRunResponse)
def get_skeleton_run() -> MatrixRunResponse:
    """Return a hardcoded MatrixRun to prove the full stack is wired.

    This endpoint exists only for Slice 1. Once real evaluation is wired
    (later slices) this will be replaced by a proper persistence-backed route.
    """
    return MatrixRunResponse(
        tier="tier_3",
        candidate="claude-sonnet-4-5",
        weighted_score=42,
        source="hardcoded MatrixRun",
    )
