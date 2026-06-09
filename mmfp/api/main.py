"""Minimal FastAPI application for the MMFP walking skeleton (MLI-160).

Exposes /health and /api/runs/skeleton. No auth yet — that comes in a later slice.

MLI-174: scoreboard router mounted here; see mmfp/api/scoreboard.py.
MLI-177: on startup, optionally download a seed SQLite from blob storage
into MMFP_DB_PATH so the deployed dev environment shows the latest
baseline-matrix run. Non-fatal — see mmfp/api/seed.py.
MLI-261: CORS middleware reads MMFP_CORS_ALLOWED_ORIGINS (comma-separated).
Browser-issued client fetches (e.g. CandidateDetail drill-down) cross
origins between the UI and API Container Apps; the deployed dev
environment was blocking those without this configured.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from mmfp.api import (
    candidate_detail,
    drift,
    promotion,
    rubric_preview,
    rubric_read,
    rubric_write,
    scoreboard,
    trends,
)
from mmfp.api.seed import download_seed_if_configured

CORS_ORIGINS_ENV = "MMFP_CORS_ALLOWED_ORIGINS"
# Local dev default: Next.js dev server. Deployed environments override via
# MMFP_CORS_ALLOWED_ORIGINS with their actual UI Container App URL.
_DEFAULT_LOCAL_ORIGIN = "http://localhost:3000"


def _parse_allowed_origins(env_value: str) -> list[str]:
    """Comma-separated origins → list. Strips whitespace; drops empties."""
    return [o.strip() for o in env_value.split(",") if o.strip()]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Runs once per container revision before any request is served.
    # Synchronous httpx call inside the async hook is intentional: small
    # SQLite blob, single shot, and we want it to complete before the
    # event loop accepts traffic.
    download_seed_if_configured()
    yield


app = FastAPI(
    title="MMFP API",
    description="Morae Model Fitness Platform API",
    version="0.0.1",
    lifespan=lifespan,
)

# CORS: read once at import. No credentials — UI fetches are anonymous; the
# UI's Basic Auth gate lives on its own Container App and doesn't propagate
# Authorization to the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_allowed_origins(
        os.environ.get(CORS_ORIGINS_ENV, _DEFAULT_LOCAL_ORIGIN)
    ),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["*"],
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


app.include_router(scoreboard.router)
app.include_router(trends.router)
app.include_router(candidate_detail.router)
app.include_router(rubric_write.router)
app.include_router(rubric_preview.router)
app.include_router(rubric_read.router)
app.include_router(promotion.router)
app.include_router(drift.router)
