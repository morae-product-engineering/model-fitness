"""Placeholder test file — ensures pytest has something to collect before
real API tests are added in MLI-162.

The substantive health-endpoint tests (using FastAPI's TestClient) will be
written as part of the unit-python CI job in MLI-162.
"""


def test_health_endpoint_exists() -> None:
    # Placeholder: verifies pytest can find and run this module.
    # TODO(MLI-162): replace with real TestClient assertions.
    assert True
