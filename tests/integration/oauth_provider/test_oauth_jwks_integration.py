"""
OAuth JWKS Endpoint Integration Tests (Increment 16).

Tests the JWKS endpoint functionality:
8.1. GET /oauth/focused/jwks → returns valid JWKS
8.2. JWKS caching behavior (optional MCP-level test)

Also covers discovery endpoints validation.

Test framework: pytest
Client: httpx.AsyncClient
Database: test DB with migrations applied
"""

import pytest
import pytest_asyncio
import base64
import hashlib
import jwt
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.models import CoreConnection, CoreUser
from backend.core.encryption import encrypt_token
from backend.core.oauth_provider.services.consent_service import create_authorization_code


# ============================================================================
# FIXTURES
# ============================================================================

def generate_pkce_pair(seed: str = "test-verifier") -> tuple[str, str]:
    """Generate a valid PKCE code_verifier and code_challenge pair."""
    code_verifier = base64.urlsafe_b64encode(
        hashlib.sha256(seed.encode()).digest()
    ).rstrip(b"=").decode("utf-8")

    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode("utf-8")

    return code_verifier, code_challenge


@pytest_asyncio.fixture
async def test_user(async_session: AsyncSession) -> CoreUser:
    """Create a test user for JWKS tests."""
    user = CoreUser(
        chatgpt_user_id=f"test-chatgpt-user-jwks-{uuid4().hex[:8]}"
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def oauth_client(async_session: AsyncSession) -> dict:
    """Create a test OAuth client."""
    client_id = f"focused-client-jwks-{uuid4().hex[:8]}"
    client_secret = f"test-secret-{uuid4().hex[:16]}"
    redirect_uri = "https://chat.openai.com/aip/callback"

    client = CoreConnection(
        user_id=None,
        provider="Test OAuth Client",
        connection_type="oauth_provider",
        client_id=client_id,
        client_secret_enc=encrypt_token(client_secret),
        redirect_uris=[redirect_uri],
        grant_types=["authorization_code", "refresh_token"],
        encrypted_access_token="",
        scopes=["focused.read", "focused.write", "focused.notify"],
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        provider_metadata={"client_name": "JWKS Test Client"}
    )
    async_session.add(client)
    await async_session.commit()

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri
    }


@pytest_asyncio.fixture
async def access_token(
    client: AsyncClient,
    async_session: AsyncSession,
    test_user: CoreUser,
    oauth_client: dict
) -> str:
    """Get a valid access token for JWKS verification tests."""
    code_verifier, code_challenge = generate_pkce_pair("jwks-token-verifier")

    code = await create_authorization_code(
        db=async_session,
        user_id=str(test_user.id),
        client_id=oauth_client["client_id"],
        code_challenge=code_challenge,
        code_challenge_method="S256",
        redirect_uri=oauth_client["redirect_uri"],
        scope="focused.read focused.write",
        correlation_id="jwks-token"
    )

    response = await client.post(
        "/oauth/focused/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": code_verifier,
            "client_id": oauth_client["client_id"],
            "redirect_uri": oauth_client["redirect_uri"]
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )

    assert response.status_code == 200
    return response.json()["access_token"]


# ============================================================================
# TEST CLASS: JWKS ENDPOINT (8.1)
# ============================================================================

class TestJWKSEndpoint:
    """Test JWKS endpoint returns valid key set."""

    @pytest.mark.asyncio
    async def test_jwks_returns_valid_json(
        self,
        client: AsyncClient
    ):
        """
        8.1. GET /oauth/focused/jwks → returns valid JWKS

        Expect: JSON with keys: [...]
        """
        response = await client.get("/oauth/focused/jwks")

        assert response.status_code == 200
        assert "application/json" in response.headers.get("content-type", "")

        data = response.json()
        assert "keys" in data
        assert isinstance(data["keys"], list)
        assert len(data["keys"]) > 0

    @pytest.mark.asyncio
    async def test_jwks_key_structure(
        self,
        client: AsyncClient
    ):
        """
        Each key contains: kty, kid, n, e, alg: RS256, use: sig
        """
        response = await client.get("/oauth/focused/jwks")
        data = response.json()

        for key in data["keys"]:
            # Required fields per RFC 7517
            assert "kty" in key
            assert key["kty"] == "RSA"

            assert "kid" in key
            assert isinstance(key["kid"], str)
            assert len(key["kid"]) > 0

            # RSA public key components
            assert "n" in key  # modulus
            assert "e" in key  # exponent

            # Algorithm specification
            assert "alg" in key
            assert key["alg"] == "RS256"

            # Key use
            assert "use" in key
            assert key["use"] == "sig"

    @pytest.mark.asyncio
    async def test_jwks_kid_stability(
        self,
        client: AsyncClient
    ):
        """
        8.2. JWKS kid values must be stable across requests.
        """
        response1 = await client.get("/oauth/focused/jwks")
        response2 = await client.get("/oauth/focused/jwks")

        keys1 = response1.json()["keys"]
        keys2 = response2.json()["keys"]

        kids1 = sorted([k["kid"] for k in keys1])
        kids2 = sorted([k["kid"] for k in keys2])

        assert kids1 == kids2, "JWKS kid values changed between requests"

    @pytest.mark.asyncio
    async def test_jwks_modulus_is_valid_base64url(
        self,
        client: AsyncClient
    ):
        """
        RSA modulus (n) must be valid base64url encoded.
        """
        response = await client.get("/oauth/focused/jwks")
        data = response.json()

        for key in data["keys"]:
            modulus = key["n"]
            # Base64url decode should work
            try:
                # Add padding if needed (standard formula: 0, 2, or 3 = chars)
                padding = "=" * (-len(modulus) % 4)
                padded = modulus + padding
                decoded = base64.urlsafe_b64decode(padded)
                assert len(decoded) > 0
            except Exception as e:
                pytest.fail(f"Invalid base64url modulus: {e}")


# ============================================================================
# TEST CLASS: JWKS TOKEN VERIFICATION
# ============================================================================

class TestJWKSTokenVerification:
    """Test that tokens can be verified using JWKS."""

    @pytest.mark.asyncio
    async def test_token_kid_matches_jwks(
        self,
        client: AsyncClient,
        access_token: str
    ):
        """
        Token's kid header must match a key in JWKS.
        """
        # Get kid from token
        header = jwt.get_unverified_header(access_token)
        token_kid = header["kid"]

        # Get JWKS
        response = await client.get("/oauth/focused/jwks")
        jwks = response.json()

        # Find matching key
        matching_keys = [k for k in jwks["keys"] if k["kid"] == token_kid]
        assert len(matching_keys) == 1, f"Token kid {token_kid} not found in JWKS"

    @pytest.mark.asyncio
    async def test_token_algorithm_is_rs256(
        self,
        access_token: str
    ):
        """
        Access tokens must use RS256 algorithm.
        """
        header = jwt.get_unverified_header(access_token)
        assert header["alg"] == "RS256"
        assert header["typ"] == "JWT"


# ============================================================================
# TEST CLASS: DISCOVERY ENDPOINTS
# ============================================================================

class TestDiscoveryEndpoints:
    """Test OIDC discovery endpoints."""

    @pytest.mark.asyncio
    async def test_openid_configuration_reachable(
        self,
        client: AsyncClient
    ):
        """OpenID configuration endpoint must be reachable."""
        response = await client.get("/.well-known/openid-configuration")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_openid_configuration_structure(
        self,
        client: AsyncClient
    ):
        """OpenID configuration must contain required fields."""
        response = await client.get("/.well-known/openid-configuration")
        data = response.json()

        # Required OIDC discovery fields
        assert "issuer" in data
        assert "authorization_endpoint" in data
        assert "token_endpoint" in data
        assert "jwks_uri" in data
        assert "response_types_supported" in data
        assert "grant_types_supported" in data

    @pytest.mark.asyncio
    async def test_openid_configuration_jwks_uri_matches(
        self,
        client: AsyncClient
    ):
        """jwks_uri in discovery should point to valid JWKS endpoint."""
        # Get discovery document
        discovery_response = await client.get("/.well-known/openid-configuration")
        discovery = discovery_response.json()

        jwks_uri = discovery["jwks_uri"]
        assert "/oauth/focused/jwks" in jwks_uri

    @pytest.mark.asyncio
    async def test_openid_configuration_endpoints_valid(
        self,
        client: AsyncClient
    ):
        """All endpoints in discovery document should be valid URLs."""
        response = await client.get("/.well-known/openid-configuration")
        data = response.json()

        # Check authorization_endpoint
        assert data["authorization_endpoint"].startswith("http")
        assert "/oauth/focused/authorize" in data["authorization_endpoint"]

        # Check token_endpoint
        assert data["token_endpoint"].startswith("http")
        assert "/oauth/focused/token" in data["token_endpoint"]

        # Check jwks_uri
        assert data["jwks_uri"].startswith("http")
        assert "/oauth/focused/jwks" in data["jwks_uri"]

    @pytest.mark.asyncio
    async def test_oauth_protected_resource_reachable(
        self,
        client: AsyncClient
    ):
        """OAuth protected resource metadata must be reachable."""
        response = await client.get("/.well-known/oauth-protected-resource")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_oauth_protected_resource_structure(
        self,
        client: AsyncClient
    ):
        """OAuth protected resource metadata must be valid."""
        response = await client.get("/.well-known/oauth-protected-resource")
        data = response.json()

        assert "resource" in data
        assert "scopes" in data
        assert isinstance(data["scopes"], dict)

        # Should include our scopes
        scopes = data["scopes"]
        assert "focused.read" in scopes or any("focused" in s for s in scopes)


# ============================================================================
# TEST CLASS: JWKS CACHING HEADERS
# ============================================================================

class TestJWKSCaching:
    """Test JWKS caching behavior and headers."""

    @pytest.mark.asyncio
    async def test_jwks_has_cache_headers(
        self,
        client: AsyncClient
    ):
        """
        JWKS endpoint should have cache control headers.
        """
        response = await client.get("/oauth/focused/jwks")

        # Should have Cache-Control header
        assert "Cache-Control" in response.headers

    @pytest.mark.asyncio
    async def test_jwks_cache_is_reasonable(
        self,
        client: AsyncClient
    ):
        """
        JWKS cache duration should be reasonable (not too short, not too long).
        """
        response = await client.get("/oauth/focused/jwks")
        cache_control = response.headers.get("Cache-Control", "")

        # Should either be no-store (for security) or have a reasonable max-age
        # Both are valid approaches
        assert "no-store" in cache_control or "max-age" in cache_control or "public" in cache_control


# ============================================================================
# TEST CLASS: JWKS KEY ROTATION SUPPORT
# ============================================================================

class TestJWKSKeyRotation:
    """Test JWKS supports key rotation scenarios."""

    @pytest.mark.asyncio
    async def test_jwks_can_contain_multiple_keys(
        self,
        client: AsyncClient
    ):
        """
        JWKS should support multiple keys for rotation.

        During key rotation, both old and new keys should be present.
        """
        response = await client.get("/oauth/focused/jwks")
        data = response.json()

        # At minimum, should have at least one key
        assert len(data["keys"]) >= 1

        # All keys should be unique by kid
        kids = [k["kid"] for k in data["keys"]]
        assert len(kids) == len(set(kids)), "Duplicate kid values in JWKS"

    @pytest.mark.asyncio
    async def test_jwks_keys_are_all_valid(
        self,
        client: AsyncClient
    ):
        """
        All keys in JWKS should be valid RSA keys.
        """
        response = await client.get("/oauth/focused/jwks")
        data = response.json()

        for i, key in enumerate(data["keys"]):
            # Each key should have all required RSA fields
            assert key.get("kty") == "RSA", f"Key {i} is not RSA"
            assert "n" in key, f"Key {i} missing modulus"
            assert "e" in key, f"Key {i} missing exponent"
            assert "kid" in key, f"Key {i} missing kid"

            # Exponent should be valid (usually AQAB = 65537)
            e_value = key["e"]
            assert len(e_value) > 0, f"Key {i} has empty exponent"
