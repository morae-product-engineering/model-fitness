"""Tests for the MMFP API health and skeleton endpoints (MLI-162).

Uses FastAPI's TestClient (backed by httpx) to exercise the endpoints
in-process — no server process required.
"""

from fastapi.testclient import TestClient

from mmfp.api.main import MatrixRunResponse, app

client = TestClient(app)


def test_health_returns_200_and_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_skeleton_run_returns_expected_shape() -> None:
    response = client.get("/api/runs/skeleton")
    assert response.status_code == 200
    body = response.json()
    # Verify the two fields called out in the acceptance criteria.
    assert body["weighted_score"] == 42
    assert body["source"] == "hardcoded MatrixRun"
    # Verify the full response validates against the declared Pydantic model.
    MatrixRunResponse(**body)
