"""
Increment 90: robots.txt Route Tests

Tests for GET /robots.txt endpoint on the shared backend.
Verifies the route returns correct content, content-type, and is excluded from OpenAPI schema.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app


# =============================================================================
# Test Setup
# =============================================================================

@pytest.fixture
def client():
    """Create a test client for the main FastAPI app."""
    return TestClient(app)


# =============================================================================
# robots.txt Route Tests
# =============================================================================

def test_robots_txt_returns_200(client):
    """GET /robots.txt returns HTTP 200."""
    response = client.get("/robots.txt")
    assert response.status_code == 200


def test_robots_txt_content_type_is_plain_text(client):
    """Response content-type starts with text/plain."""
    response = client.get("/robots.txt")
    content_type = response.headers.get("content-type", "")
    assert content_type.startswith("text/plain"), f"Expected text/plain, got {content_type}"


def test_robots_txt_body_is_correct(client):
    """Response body equals exactly 'User-agent: *\\nDisallow: /\\n'."""
    response = client.get("/robots.txt")
    expected_body = "User-agent: *\nDisallow: /\n"
    assert response.text == expected_body, f"Expected {expected_body!r}, got {response.text!r}"


def test_robots_txt_not_in_openapi_schema():
    """The /robots.txt route is NOT present in the OpenAPI schema."""
    openapi_schema = app.openapi()
    paths = openapi_schema.get("paths", {})
    assert "/robots.txt" not in paths, "robots.txt should not appear in OpenAPI schema"
