"""Tests for the CORS middleware configuration (MLI-261).

The MMFP API and UI run on separate Container Apps in dev. Without CORS the
candidate-detail drill-down (MLI-187), which is a client-side fetch in the
browser, is blocked. These tests pin the parser behaviour and confirm the
middleware actually attaches a `Access-Control-Allow-Origin` header for an
allowed origin.
"""

from fastapi.testclient import TestClient

from mmfp.api.main import _parse_allowed_origins, app

client = TestClient(app)


def test_parse_allowed_origins_strips_and_drops_empties() -> None:
    assert _parse_allowed_origins(
        "https://a.example.com, https://b.example.com , ,"
    ) == ["https://a.example.com", "https://b.example.com"]


def test_parse_allowed_origins_handles_single_origin() -> None:
    assert _parse_allowed_origins("http://localhost:3000") == [
        "http://localhost:3000"
    ]


def test_parse_allowed_origins_empty_string_yields_empty_list() -> None:
    assert _parse_allowed_origins("") == []


def test_cors_simple_request_from_default_origin_gets_allow_header() -> None:
    # No MMFP_CORS_ALLOWED_ORIGINS set in the test env → default localhost:3000.
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == (
        "http://localhost:3000"
    )


def test_cors_preflight_for_disallowed_origin_omits_allow_header() -> None:
    # Starlette's CORSMiddleware returns 200 for OPTIONS preflight but omits
    # Access-Control-Allow-Origin when the request origin isn't on the list,
    # which is what causes the browser to block the subsequent request.
    response = client.options(
        "/health",
        headers={
            "Origin": "https://not-allowed.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in {
        k.lower() for k in response.headers
    }
