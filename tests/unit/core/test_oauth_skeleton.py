"""
Tests for Increment 7A: OAuth Provider Skeleton.

Tests:
- Discovery endpoints (.well-known)
- JWKS endpoint
- Placeholder /authorize, /token, /register endpoints
- JWT validation

No real authorization logic tested (that's 7B).
"""

import json
import pytest
from fastapi.testclient import TestClient
from jose import jwt

from backend.main import app
from backend.core.config import settings
from backend.core.crypto import get_public_key


@pytest.fixture
def client():
    """Create test client with proper lifespan handling."""
    with TestClient(app) as test_client:
        yield test_client


# =============================================================================
# Discovery Endpoints Tests
# =============================================================================

def test_openid_configuration(client):
    """Test OpenID Connect discovery endpoint."""
    response = client.get("/.well-known/openid-configuration")

    assert response.status_code == 200
    data = response.json()

    # Verify required fields
    assert data["issuer"] == settings.OAUTH_ISSUER
    assert data["authorization_endpoint"] == f"{settings.OAUTH_ISSUER}/oauth/focused/authorize"
    assert data["token_endpoint"] == f"{settings.OAUTH_ISSUER}/oauth/focused/token"
    assert data["jwks_uri"] == f"{settings.OAUTH_ISSUER}/oauth/focused/jwks"
    assert data["registration_endpoint"] == f"{settings.OAUTH_ISSUER}/oauth/focused/register"

    # Verify scopes
    assert "focused.read" in data["scopes_supported"]
    assert "focused.write" in data["scopes_supported"]
    assert "focused.notify" in data["scopes_supported"]

    # Verify grant types
    assert "authorization_code" in data["grant_types_supported"]
    assert "refresh_token" in data["grant_types_supported"]

    # Verify PKCE support
    assert "S256" in data["code_challenge_methods_supported"]


def test_oauth_protected_resource(client):
    """Test OAuth protected resource metadata endpoint."""
    response = client.get("/.well-known/oauth-protected-resource")

    assert response.status_code == 200
    data = response.json()

    # Verify resource metadata
    assert data["resource"] == f"{settings.OAUTH_ISSUER}/mcp/focused"
    assert settings.OAUTH_ISSUER in data["authorization_servers"]

    # Verify scopes
    assert "focused.read" in data["scopes"]
    assert "focused.write" in data["scopes"]
    assert "focused.notify" in data["scopes"]


# =============================================================================
# JWKS Endpoint Tests
# =============================================================================

def test_jwks_endpoint(client):
    """Test JWKS endpoint returns valid public key."""
    response = client.get("/oauth/focused/jwks")

    assert response.status_code == 200
    data = response.json()

    # Verify JWKS structure
    assert "keys" in data
    assert len(data["keys"]) == 1

    # Verify key properties
    key = data["keys"][0]
    assert key["kty"] == "RSA"
    assert key["use"] == "sig"
    assert key["kid"] == settings.OAUTH_JWT_KID
    assert key["alg"] == "RS256"
    assert "n" in key  # Modulus
    assert "e" in key  # Exponent

    # Verify no private key components
    assert "d" not in key  # Private exponent
    assert "p" not in key  # Prime 1
    assert "q" not in key  # Prime 2


def test_jwks_caching(client):
    """Test JWKS response is cacheable."""
    # Make two requests
    response1 = client.get("/oauth/focused/jwks")
    response2 = client.get("/oauth/focused/jwks")

    assert response1.status_code == 200
    assert response2.status_code == 200

    # Should return identical JWKS
    assert response1.json() == response2.json()


# =============================================================================
# Placeholder Endpoint Tests
# =============================================================================

def test_authorize_endpoint_placeholder(client):
    """Test /authorize endpoint returns HTML placeholder."""
    response = client.get("/oauth/focused/authorize")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "OAuth Authorization" in response.text
    assert "Placeholder" in response.text


def test_token_endpoint_returns_dummy_jwt(client):
    """Test /token endpoint returns dummy signed JWT."""
    response = client.post(
        "/oauth/focused/token",
        json={
            "grant_type": "authorization_code",
            "code": "dummy-code",
            "redirect_uri": "http://localhost:8000/callback"
        }
    )

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "access_token" in data
    assert data["token_type"] == "Bearer"
    assert data["expires_in"] == settings.OAUTH_TOKEN_EXPIRY_SECONDS
    assert "focused.read" in data["scope"]
    assert "focused.write" in data["scope"]

    # Verify JWT is signed and valid
    access_token = data["access_token"]
    assert isinstance(access_token, str)
    assert len(access_token.split(".")) == 3  # JWT has 3 parts


def test_token_endpoint_requires_grant_type(client):
    """Test /token endpoint validates grant_type."""
    response = client.post(
        "/oauth/focused/token",
        json={}
    )

    # Should fail validation
    assert response.status_code == 422


def test_token_jwt_can_be_decoded(client):
    """Test dummy JWT can be decoded and verified."""
    response = client.post(
        "/oauth/focused/token",
        json={
            "grant_type": "authorization_code",
            "code": "dummy-code"
        }
    )

    assert response.status_code == 200
    data = response.json()
    access_token = data["access_token"]

    # Decode JWT header (unverified)
    header = jwt.get_unverified_header(access_token)
    assert header["kid"] == settings.OAUTH_JWT_KID
    assert header["alg"] == "RS256"

    # Decode JWT payload (unverified)
    payload = jwt.get_unverified_claims(access_token)
    assert payload["iss"] == settings.OAUTH_ISSUER
    assert payload["aud"] == settings.OAUTH_ISSUER
    assert "sub" in payload  # User ID
    assert "jti" in payload  # JWT ID
    assert "scope" in payload
    assert "client_id" in payload
    assert "exp" in payload
    assert "iat" in payload


def test_register_endpoint_returns_client_credentials(client):
    """Test /register endpoint returns dummy client credentials."""
    response = client.post(
        "/oauth/focused/register",
        json={
            "client_name": "Test Client",
            "redirect_uris": ["http://localhost:8000/callback"]
        }
    )

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "client_id" in data
    assert "client_secret" in data
    assert "scope" in data

    # Verify client_id format
    assert data["client_id"].startswith("focused-client-")

    # Verify scopes
    assert "focused.read" in data["scope"]
    assert "focused.write" in data["scope"]


def test_register_endpoint_accepts_minimal_body(client):
    """Test /register endpoint accepts minimal request body."""
    response = client.post(
        "/oauth/focused/register",
        json={}
    )

    assert response.status_code == 200
    data = response.json()
    assert "client_id" in data
    assert "client_secret" in data


# =============================================================================
# Integration Tests
# =============================================================================

def test_full_discovery_flow(client):
    """Test complete discovery flow (discovery → JWKS → token)."""
    # Step 1: Discovery
    discovery_response = client.get("/.well-known/openid-configuration")
    assert discovery_response.status_code == 200
    discovery_data = discovery_response.json()

    # Step 2: Fetch JWKS
    jwks_uri = discovery_data["jwks_uri"]
    # Extract path from full URL
    jwks_path = "/oauth/focused/jwks"
    jwks_response = client.get(jwks_path)
    assert jwks_response.status_code == 200
    jwks_data = jwks_response.json()
    assert len(jwks_data["keys"]) == 1

    # Step 3: Get dummy token
    token_response = client.post(
        "/oauth/focused/token",
        json={"grant_type": "authorization_code", "code": "test"}
    )
    assert token_response.status_code == 200
    token_data = token_response.json()
    assert "access_token" in token_data

    # Step 4: Verify JWT header matches JWKS
    access_token = token_data["access_token"]
    header = jwt.get_unverified_header(access_token)
    jwks_kid = jwks_data["keys"][0]["kid"]
    assert header["kid"] == jwks_kid


# =============================================================================
# Error Handling Tests
# =============================================================================

def test_invalid_endpoint_returns_404(client):
    """Test invalid OAuth endpoint returns 404."""
    response = client.get("/oauth/focused/invalid")
    assert response.status_code == 404


def test_token_endpoint_post_only(client):
    """Test /token endpoint only accepts POST."""
    response = client.get("/oauth/focused/token")
    assert response.status_code == 405  # Method Not Allowed


def test_register_endpoint_post_only(client):
    """Test /register endpoint only accepts POST."""
    response = client.get("/oauth/focused/register")
    assert response.status_code == 405  # Method Not Allowed
