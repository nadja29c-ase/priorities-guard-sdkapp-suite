"""
Integration tests for Google Connection MCP Tools (Increment 18).

Tests:
- /api/focused/google/connection-status endpoint
- /api/focused/google/initiate-connection endpoint
- /auth/google/start with token parameter
- Token expiration and single-use behavior
"""

import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.models import CoreUser, CoreConnection

# Mark all tests as async
pytestmark = pytest.mark.asyncio


# =============================================================================
# Fixtures
# =============================================================================

@pytest_asyncio.fixture
async def test_user(async_session: AsyncSession):
    """Create a test user in the database."""
    user = CoreUser(id=uuid4())
    async_session.add(user)
    await async_session.commit()
    return user


@pytest_asyncio.fixture
async def connected_user(async_session: AsyncSession):
    """Create a test user with an active Google connection."""
    user = CoreUser(id=uuid4())
    async_session.add(user)
    await async_session.flush()

    connection = CoreConnection(
        user_id=str(user.id),
        provider="google",
        connection_type="google",  # Valid per ck_connection_type_enum constraint
        encrypted_access_token="encrypted_access",
        encrypted_refresh_token="encrypted_refresh",
        token_expires_at=datetime.now(timezone.utc),
        scopes=["https://www.googleapis.com/auth/calendar.readonly"],
    )
    async_session.add(connection)
    await async_session.commit()
    return user


# =============================================================================
# /api/focused/google/connection-status Tests
# =============================================================================

class TestConnectionStatusEndpoint:
    """Tests for GET /api/focused/google/connection-status."""

    async def test_returns_connected_true_when_connection_exists(
        self, client, connected_user
    ):
        """Test endpoint returns connected=true for user with Google connection."""
        response = await client.get(
            "/api/focused/google/connection-status",
            headers={"X-User-ID": str(connected_user.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True
        assert "connected_at" in data
        assert "scopes" in data

    async def test_returns_connected_false_when_no_connection(
        self, client, test_user
    ):
        """Test endpoint returns connected=false for user without connection."""
        response = await client.get(
            "/api/focused/google/connection-status",
            headers={"X-User-ID": str(test_user.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False

    async def test_requires_user_id_header(self, client):
        """Test endpoint requires X-User-ID header."""
        response = await client.get("/api/focused/google/connection-status")

        assert response.status_code == 422  # Missing required header

    async def test_returns_scopes_when_connected(self, client, connected_user):
        """Test endpoint returns granted scopes when connected."""
        response = await client.get(
            "/api/focused/google/connection-status",
            headers={"X-User-ID": str(connected_user.id)},
        )

        data = response.json()
        assert "scopes" in data
        assert "https://www.googleapis.com/auth/calendar.readonly" in data["scopes"]

    async def test_returns_false_when_connection_revoked(
        self, client, async_session: AsyncSession
    ):
        """Test endpoint returns connected=false when revoked_at is set.

        Per Increment 10: revoked_at indicates disconnection.
        A connection with revoked_at set should not appear as "connected".
        """
        from datetime import datetime, timezone

        # Create user with revoked connection
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        connection = CoreConnection(
            user_id=str(user.id),
            provider="google",
            connection_type="google",
            encrypted_access_token="encrypted_access",
            encrypted_refresh_token="encrypted_refresh",
            token_expires_at=datetime.now(timezone.utc),
            scopes=["https://www.googleapis.com/auth/calendar.readonly"],
            revoked_at=datetime.now(timezone.utc),  # Connection was revoked
        )
        async_session.add(connection)
        await async_session.commit()

        response = await client.get(
            "/api/focused/google/connection-status",
            headers={"X-User-ID": str(user.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False, "Revoked connection should not appear as connected"


# =============================================================================
# /api/focused/google/initiate-connection Tests
# =============================================================================

class TestInitiateConnectionEndpoint:
    """Tests for POST /api/focused/google/initiate-connection."""

    async def test_returns_opaque_token(self, client, test_user):
        """Test endpoint returns an opaque connection token."""
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.set = AsyncMock(return_value=True)

            response = await client.post(
                "/api/focused/google/initiate-connection",
                headers={"X-User-ID": str(test_user.id)},
            )

        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert len(data["token"]) == 43  # secrets.token_urlsafe(32)

    async def test_returns_connect_url(self, client, test_user):
        """Test endpoint returns a complete connect URL."""
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.set = AsyncMock(return_value=True)

            response = await client.post(
                "/api/focused/google/initiate-connection",
                headers={"X-User-ID": str(test_user.id)},
            )

        data = response.json()
        assert "connect_url" in data
        assert "/auth/google/start?token=" in data["connect_url"]

    async def test_returns_expires_in(self, client, test_user):
        """Test endpoint returns token expiration time."""
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.set = AsyncMock(return_value=True)

            response = await client.post(
                "/api/focused/google/initiate-connection",
                headers={"X-User-ID": str(test_user.id)},
            )

        data = response.json()
        assert data["expires_in"] == 600  # 10 minutes

    async def test_token_stored_in_redis(self, client, test_user):
        """Test token is stored in Redis with correct key format."""
        stored_key = None

        async def capture_set(key, value, ex=None):
            nonlocal stored_key
            stored_key = key
            return True

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.set = capture_set

            response = await client.post(
                "/api/focused/google/initiate-connection",
                headers={"X-User-ID": str(test_user.id)},
            )

        token = response.json()["token"]
        assert stored_key == f"google_connect:{token}"

    async def test_redis_key_format_is_safe(self, client, test_user):
        """Test Redis key format prevents key injection attacks.

        SECURITY: Redis key injection can allow:
        - Overwriting other keys (if attacker controls token)
        - Accessing unrelated data via key traversal
        - DoS via extremely long keys

        The token must:
        - Not contain colons (would create nested namespaces)
        - Not contain slashes (could be interpreted as paths)
        - Not contain null bytes (could truncate keys)
        - Not contain newlines (could inject commands in some clients)
        - Be URL-safe characters only (A-Za-z0-9-_)
        """
        stored_key = None
        stored_value = None

        async def capture_set(key, value, ex=None):
            nonlocal stored_key, stored_value
            stored_key = key
            stored_value = value
            return True

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.set = capture_set

            response = await client.post(
                "/api/focused/google/initiate-connection",
                headers={"X-User-ID": str(test_user.id)},
            )

        token = response.json()["token"]

        # Token must not contain dangerous characters
        assert ":" not in token, "Token contains colon - Redis namespace injection risk"
        assert "/" not in token, "Token contains slash - path traversal risk"
        assert "\\" not in token, "Token contains backslash - escape sequence risk"
        assert "\x00" not in token, "Token contains null byte - truncation risk"
        assert "\n" not in token, "Token contains newline - command injection risk"
        assert "\r" not in token, "Token contains carriage return - command injection risk"
        assert " " not in token, "Token contains space - parsing issues"

        # Token must be URL-safe only (secrets.token_urlsafe uses A-Za-z0-9-_)
        valid_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
        invalid_chars = set(token) - valid_chars
        assert not invalid_chars, f"Token contains invalid characters: {invalid_chars}"

        # Key must have exactly one colon (the prefix separator)
        assert stored_key.count(":") == 1, f"Key has wrong number of colons: {stored_key}"

        # Key must start with exact prefix
        assert stored_key.startswith("google_connect:"), f"Wrong key prefix: {stored_key}"

        # Value must be exactly the user_id (no extra data)
        assert stored_value == str(test_user.id), "Value should be only user_id"

    async def test_redis_value_contains_only_user_id(self, client, test_user):
        """Test Redis value is minimal - only user_id, no sensitive data leakage.

        SECURITY: The Redis value should NOT contain:
        - Scopes (could leak permissions)
        - Timestamps (could aid timing attacks)
        - IP addresses (privacy concern)
        - Any PII beyond the user_id reference
        """
        stored_value = None

        async def capture_set(key, value, ex=None):
            nonlocal stored_value
            stored_value = value
            return True

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.set = capture_set

            await client.post(
                "/api/focused/google/initiate-connection",
                headers={"X-User-ID": str(test_user.id)},
            )

        # Value must be exactly the user_id string, nothing else
        assert stored_value == str(test_user.id), (
            f"Redis value should be exactly user_id. Got: {stored_value}"
        )

        # Verify it's not JSON or structured data
        try:
            parsed = json.loads(stored_value)
            # If it parses as JSON, it should fail (we want plain string)
            if isinstance(parsed, dict):
                pytest.fail("Redis value is JSON object - should be plain user_id string")
        except json.JSONDecodeError:
            pass  # Expected - value should not be JSON

    async def test_user_id_stored_as_value(self, client, test_user):
        """Test user_id is stored as the Redis value."""
        stored_value = None

        async def capture_set(key, value, ex=None):
            nonlocal stored_value
            stored_value = value
            return True

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.set = capture_set

            await client.post(
                "/api/focused/google/initiate-connection",
                headers={"X-User-ID": str(test_user.id)},
            )

        assert stored_value == str(test_user.id)

    async def test_token_stored_with_correct_ttl(self, client, test_user):
        """Test token is stored with 600 second TTL (10 minutes).

        SECURITY CRITICAL: The TTL ensures tokens auto-expire.
        Without this, orphaned tokens could accumulate in Redis
        and potentially be exploited if Redis is compromised.
        """
        stored_ttl = None

        async def capture_set(key, value, ex=None):
            nonlocal stored_ttl
            stored_ttl = ex
            return True

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.set = capture_set

            await client.post(
                "/api/focused/google/initiate-connection",
                headers={"X-User-ID": str(test_user.id)},
            )

        assert stored_ttl == 600, f"Expected TTL=600 (10 minutes), got {stored_ttl}"

    async def test_requires_user_id_header(self, client):
        """Test endpoint requires X-User-ID header."""
        response = await client.post("/api/focused/google/initiate-connection")

        assert response.status_code == 422

    async def test_token_is_url_safe(self, client, test_user):
        """Test generated token contains only URL-safe characters."""
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.set = AsyncMock(return_value=True)

            response = await client.post(
                "/api/focused/google/initiate-connection",
                headers={"X-User-ID": str(test_user.id)},
            )

        token = response.json()["token"]
        valid_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
        assert all(c in valid_chars for c in token)

    async def test_allows_initiation_when_already_connected(self, client, connected_user):
        """Test initiate-connection succeeds even if user already has a connection.

        DESIGN DECISION: The endpoint does NOT block already-connected users.

        Rationale:
        - The MCP tool (connect_google_calendar_logic) checks status first
        - Allowing re-initiation supports token refresh / reconnection scenarios
        - The OAuth callback uses upsert, so reconnecting updates existing record

        If this behavior changes, this test will fail and force explicit decision.
        """
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.set = AsyncMock(return_value=True)

            response = await client.post(
                "/api/focused/google/initiate-connection",
                headers={"X-User-ID": str(connected_user.id)},
            )

        # Should succeed (200), not block (400/409)
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "connect_url" in data


# =============================================================================
# /auth/google/start with Token Parameter Tests
# =============================================================================

class TestStartWithTokenParameter:
    """Tests for GET /auth/google/start?token=..."""

    async def test_valid_token_redirects_to_google(self, client, test_user):
        """Test valid token results in redirect to Google OAuth."""
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            # Token verification returns user_id
            mock_redis.get = AsyncMock(return_value=str(test_user.id))
            mock_redis.delete = AsyncMock()
            # State storage succeeds
            mock_redis.set = AsyncMock(return_value=True)

            response = await client.get(
                "/auth/google/start?token=valid_token_123",
                follow_redirects=False,
            )

        assert response.status_code == 307
        location = response.headers.get("location")
        assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth")

    async def test_valid_token_includes_pkce(self, client, test_user):
        """Test redirect URL includes PKCE parameters."""
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=str(test_user.id))
            mock_redis.delete = AsyncMock()
            mock_redis.set = AsyncMock(return_value=True)

            response = await client.get(
                "/auth/google/start?token=valid_token",
                follow_redirects=False,
            )

        location = response.headers.get("location")
        assert "code_challenge=" in location
        assert "code_challenge_method=S256" in location

    async def test_expired_token_returns_html_error(self, client):
        """Test expired token returns user-friendly HTML error."""
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            # Token not found (expired)
            mock_redis.get = AsyncMock(return_value=None)

            response = await client.get(
                "/auth/google/start?token=expired_token",
            )

        assert response.status_code == 400
        assert "text/html" in response.headers.get("content-type", "")
        assert "expired" in response.text.lower() or "link" in response.text.lower()

    async def test_invalid_token_returns_html_error(self, client):
        """Test invalid/unknown token returns HTML error."""
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)

            response = await client.get(
                "/auth/google/start?token=nonexistent_token",
            )

        assert response.status_code == 400
        assert "text/html" in response.headers.get("content-type", "")

    async def test_token_deleted_after_use(self, client, test_user):
        """Test token is deleted from Redis after successful use (single-use)."""
        delete_called_with = None

        async def capture_delete(key):
            nonlocal delete_called_with
            delete_called_with = key

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=str(test_user.id))
            mock_redis.delete = capture_delete
            mock_redis.set = AsyncMock(return_value=True)

            await client.get(
                "/auth/google/start?token=single_use_token",
                follow_redirects=False,
            )

        assert delete_called_with == "google_connect:single_use_token"

    async def test_token_replay_rejected(self, client, test_user):
        """Test same token cannot be used twice."""
        call_count = 0

        async def mock_get(key):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return str(test_user.id)
            return None  # Token was deleted

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = mock_get
            mock_redis.delete = AsyncMock()
            mock_redis.set = AsyncMock(return_value=True)

            # First use should succeed
            response1 = await client.get(
                "/auth/google/start?token=replay_token",
                follow_redirects=False,
            )

            # Second use should fail
            response2 = await client.get(
                "/auth/google/start?token=replay_token",
            )

        assert response1.status_code == 307  # Redirect to Google
        assert response2.status_code == 400  # Token already used

    async def test_requires_token_parameter(self, client):
        """Test endpoint requires token query parameter."""
        response = await client.get("/auth/google/start")

        assert response.status_code == 422  # Missing required param

    async def test_error_page_does_not_expose_token(self, client):
        """Test error page does not include the token in response."""
        secret_token = "super_secret_token_value_xyz"

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)

            response = await client.get(
                f"/auth/google/start?token={secret_token}",
            )

        # Token should not appear in error page
        assert secret_token not in response.text

    async def test_error_page_escapes_script_tags(self, client):
        """Test error page escapes script tags to prevent XSS.

        SECURITY CRITICAL: Reflected XSS prevention.
        An attacker could craft a malicious URL like:
        /auth/google/start?token=<script>alert(1)</script>

        If the token is reflected in the error page without escaping,
        this becomes a reflected XSS vulnerability.
        """
        xss_payload = "<script>alert('xss')</script>"

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)

            response = await client.get(
                f"/auth/google/start?token={xss_payload}",
            )

        # Script tag must NOT appear unescaped in response
        assert "<script>" not in response.text, "Unescaped <script> tag found - XSS vulnerability!"
        assert "</script>" not in response.text, "Unescaped </script> tag found - XSS vulnerability!"

        # Also check the payload isn't reflected at all
        assert xss_payload not in response.text, "XSS payload reflected in response"

    async def test_error_page_escapes_html_entities(self, client):
        """Test error page escapes HTML entities in user input."""
        html_payload = "<img src=x onerror=alert(1)>"

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)

            response = await client.get(
                f"/auth/google/start?token={html_payload}",
            )

        # HTML tags must not appear unescaped
        assert "<img" not in response.text, "Unescaped <img> tag found - XSS vulnerability!"
        assert "onerror" not in response.text, "Event handler reflected - XSS vulnerability!"

    async def test_error_page_escapes_javascript_protocol(self, client):
        """Test error page escapes javascript: protocol URLs."""
        js_payload = "javascript:alert(document.cookie)"

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)

            response = await client.get(
                f"/auth/google/start?token={js_payload}",
            )

        # javascript: protocol must not appear in any href or src
        assert "javascript:" not in response.text.lower(), "javascript: protocol found - XSS vulnerability!"

    async def test_error_page_escapes_encoded_xss(self, client):
        """Test error page handles URL-encoded XSS attempts."""
        # URL-encoded <script>alert(1)</script>
        encoded_payload = "%3Cscript%3Ealert(1)%3C%2Fscript%3E"

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)

            response = await client.get(
                f"/auth/google/start?token={encoded_payload}",
            )

        # After URL decoding by the server, script tags must still be escaped
        assert "<script>" not in response.text, "Decoded XSS payload executed"
        assert "</script>" not in response.text, "Decoded XSS payload executed"

    async def test_redis_error_page_no_user_input_reflection(self, client):
        """Test Redis error page doesn't reflect any user input."""
        malicious_token = "<b>bold</b><!--comment-->"

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(side_effect=Exception("Redis connection failed"))

            response = await client.get(
                f"/auth/google/start?token={malicious_token}",
            )

        assert response.status_code == 500
        # No user input should be reflected in error page
        assert "<b>" not in response.text, "HTML tag reflected in error page"
        assert "<!--" not in response.text, "HTML comment reflected in error page"
        assert malicious_token not in response.text, "User input reflected in error page"

    async def test_stores_oauth_state_with_user_from_token(self, client, test_user):
        """Test OAuth state is stored with user_id from connection token."""
        stored_state_data = None

        async def capture_set(key, value, ex=None):
            nonlocal stored_state_data
            if key.startswith("oauth:google:state:"):
                stored_state_data = json.loads(value)
            return True

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=str(test_user.id))
            mock_redis.delete = AsyncMock()
            mock_redis.set = capture_set

            await client.get(
                "/auth/google/start?token=valid_token",
                follow_redirects=False,
            )

        assert stored_state_data is not None
        assert stored_state_data["user_id"] == str(test_user.id)
        assert "code_verifier" in stored_state_data

    async def test_oauth_state_structure_complete(self, client, test_user):
        """Test OAuth state contains all required fields for callback processing.

        The stored state MUST contain:
        - user_id: To identify which user initiated the flow
        - code_verifier: For PKCE verification during token exchange
        - created_at: For audit trail and debugging

        The callback handler (verify_and_get_oauth_state) expects these exact keys.
        If any are missing, the callback will fail with KeyError.

        NOTE: redirect_uri, scopes, and code_challenge are NOT stored in state.
        They are reconstructed from config during callback (settings.GOOGLE_REDIRECT_URI).
        This is safe because they are server-side constants, not user-controlled.
        """
        stored_state_data = None
        stored_state_ttl = None

        async def capture_set(key, value, ex=None):
            nonlocal stored_state_data, stored_state_ttl
            if key.startswith("oauth:google:state:"):
                stored_state_data = json.loads(value)
                stored_state_ttl = ex
            return True

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=str(test_user.id))
            mock_redis.delete = AsyncMock()
            mock_redis.set = capture_set

            await client.get(
                "/auth/google/start?token=valid_token",
                follow_redirects=False,
            )

        # Verify all required fields are present
        assert stored_state_data is not None, "OAuth state was not stored"

        # Required: user_id (string, non-empty)
        assert "user_id" in stored_state_data, "Missing required field: user_id"
        assert isinstance(stored_state_data["user_id"], str), "user_id must be string"
        assert stored_state_data["user_id"] == str(test_user.id), "user_id mismatch"

        # Required: code_verifier (string, 43-128 chars per RFC 7636)
        assert "code_verifier" in stored_state_data, "Missing required field: code_verifier"
        verifier = stored_state_data["code_verifier"]
        assert isinstance(verifier, str), "code_verifier must be string"
        assert 43 <= len(verifier) <= 128, f"code_verifier length {len(verifier)} outside RFC 7636 range [43,128]"

        # Required: created_at (ISO 8601 timestamp)
        assert "created_at" in stored_state_data, "Missing required field: created_at"
        created_at = stored_state_data["created_at"]
        assert isinstance(created_at, str), "created_at must be string"
        # Verify it's a valid ISO timestamp
        from datetime import datetime
        try:
            datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            pytest.fail(f"created_at is not valid ISO 8601: {created_at}")

        # Verify TTL is set (600 seconds = 10 minutes)
        assert stored_state_ttl == 600, f"OAuth state TTL must be 600, got {stored_state_ttl}"

        # Verify no unexpected fields (defense against accidental data leakage)
        # scope is optional - added in scope parameterization to support per-app scopes
        expected_fields = {"user_id", "code_verifier", "created_at", "scope"}
        actual_fields = set(stored_state_data.keys())
        unexpected = actual_fields - expected_fields
        assert not unexpected, f"Unexpected fields in OAuth state: {unexpected}"


# =============================================================================
# Full Flow Integration Tests
# =============================================================================

class TestFullConnectionFlow:
    """Tests for the complete connection flow."""

    async def test_initiate_then_start_flow(self, client, test_user):
        """Test: initiate-connection → start with token → redirect to Google."""
        # Step 1: Initiate connection to get token
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            stored_tokens = {}

            async def mock_set(key, value, ex=None):
                stored_tokens[key] = value
                return True

            async def mock_get(key):
                return stored_tokens.get(key)

            async def mock_delete(key):
                stored_tokens.pop(key, None)

            mock_redis.set = mock_set
            mock_redis.get = mock_get
            mock_redis.delete = mock_delete

            # Initiate connection
            initiate_response = await client.post(
                "/api/focused/google/initiate-connection",
                headers={"X-User-ID": str(test_user.id)},
            )

            assert initiate_response.status_code == 200
            token = initiate_response.json()["token"]

            # Use token to start OAuth
            start_response = await client.get(
                f"/auth/google/start?token={token}",
                follow_redirects=False,
            )

        assert start_response.status_code == 307
        assert "accounts.google.com" in start_response.headers.get("location", "")

    async def test_user_id_not_in_any_url(self, client, test_user):
        """Test user_id never appears in any URL (security requirement)."""
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.set = AsyncMock(return_value=True)

            response = await client.post(
                "/api/focused/google/initiate-connection",
                headers={"X-User-ID": str(test_user.id)},
            )

        connect_url = response.json()["connect_url"]

        # user_id should NOT appear in the URL
        assert str(test_user.id) not in connect_url
        assert "user_id" not in connect_url.lower()


# =============================================================================
# Scope Verification Tests
# =============================================================================

class TestScopeVerification:
    """Tests for Google OAuth scope handling.

    Google reviewers manually verify scope handling. These tests ensure:
    - Scopes stored in DB match what connection-status returns
    - Only expected scopes are accepted
    - Extra/missing scopes are handled correctly
    """

    async def test_connection_status_returns_exact_db_scopes(
        self, client, async_session: AsyncSession
    ):
        """Test connection-status returns exactly the scopes stored in DB."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Store connection with specific scopes
        stored_scopes = ["https://www.googleapis.com/auth/calendar.readonly"]
        connection = CoreConnection(
            user_id=str(user.id),
            provider="google",
            connection_type="google",
            encrypted_access_token="encrypted_access",
            encrypted_refresh_token="encrypted_refresh",
            token_expires_at=datetime.now(timezone.utc),
            scopes=stored_scopes,
        )
        async_session.add(connection)
        await async_session.commit()

        response = await client.get(
            "/api/focused/google/connection-status",
            headers={"X-User-ID": str(user.id)},
        )

        data = response.json()
        assert data["scopes"] == stored_scopes, "Returned scopes must match DB exactly"

    async def test_connection_status_with_multiple_scopes(
        self, client, async_session: AsyncSession
    ):
        """Test connection-status returns all scopes when multiple are stored."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Multiple scopes (hypothetical future scenario)
        stored_scopes = [
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/calendar.events.readonly",
        ]
        connection = CoreConnection(
            user_id=str(user.id),
            provider="google",
            connection_type="google",
            encrypted_access_token="encrypted_access",
            encrypted_refresh_token="encrypted_refresh",
            token_expires_at=datetime.now(timezone.utc),
            scopes=stored_scopes,
        )
        async_session.add(connection)
        await async_session.commit()

        response = await client.get(
            "/api/focused/google/connection-status",
            headers={"X-User-ID": str(user.id)},
        )

        data = response.json()
        assert set(data["scopes"]) == set(stored_scopes), "All scopes must be returned"

    async def test_database_rejects_empty_scopes(
        self, async_session: AsyncSession
    ):
        """Test database constraint prevents empty scopes array.

        SECURITY: The ck_scopes_not_empty constraint ensures connections
        always have at least one scope. This prevents:
        - Connections with no permissions (useless)
        - Bypassing scope validation during token storage
        - Data corruption from bugs

        If this test fails, the constraint was removed or modified.
        """
        from sqlalchemy.exc import IntegrityError

        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        connection = CoreConnection(
            user_id=str(user.id),
            provider="google",
            connection_type="google",
            encrypted_access_token="encrypted_access",
            encrypted_refresh_token="encrypted_refresh",
            token_expires_at=datetime.now(timezone.utc),
            scopes=[],  # Empty scopes - should be rejected
        )
        async_session.add(connection)

        with pytest.raises(IntegrityError) as exc_info:
            await async_session.commit()

        assert "ck_scopes_not_empty" in str(exc_info.value), (
            "Expected ck_scopes_not_empty constraint violation"
        )

    async def test_oauth_start_requests_correct_scope(self, client, test_user):
        """Test OAuth redirect URL requests exactly the required scope.

        SECURITY CRITICAL: We must request ONLY calendar.readonly.
        Requesting extra scopes triggers additional Google review.
        Requesting wrong scopes breaks the app.
        """
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=str(test_user.id))
            mock_redis.delete = AsyncMock()
            mock_redis.set = AsyncMock(return_value=True)

            response = await client.get(
                "/auth/google/start?token=valid_token",
                follow_redirects=False,
            )

        location = response.headers.get("location", "")

        # Must request exactly calendar.readonly
        assert "scope=" in location, "Missing scope parameter"

        # Extract scope from URL
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(location)
        params = parse_qs(parsed.query)

        assert "scope" in params, "scope parameter missing from redirect URL"
        scope_value = params["scope"][0]

        # Must be exactly this scope
        expected_scope = "https://www.googleapis.com/auth/calendar.readonly"
        assert scope_value == expected_scope, (
            f"Wrong scope requested. Expected: {expected_scope}, Got: {scope_value}"
        )

    async def test_oauth_start_does_not_request_write_scope(self, client, test_user):
        """Test OAuth redirect does NOT request write/modify scopes.

        PRIVACY CRITICAL: We only need read access.
        Write scopes would allow the app to modify user's calendar.
        Google reviewers specifically check for scope minimization.
        """
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=str(test_user.id))
            mock_redis.delete = AsyncMock()
            mock_redis.set = AsyncMock(return_value=True)

            response = await client.get(
                "/auth/google/start?token=valid_token",
                follow_redirects=False,
            )

        location = response.headers.get("location", "")

        # Must NOT contain any write scopes
        dangerous_scopes = [
            "calendar.events",  # Full read/write
            "calendar.events.owned",  # Write owned events
            "calendar",  # Full calendar access
            "/auth/calendar ",  # Generic calendar (not readonly)
        ]

        for dangerous in dangerous_scopes:
            assert dangerous not in location or "readonly" in location, (
                f"Dangerous scope pattern found: {dangerous}"
            )

    async def test_connection_scopes_not_modified_by_endpoint(
        self, client, async_session: AsyncSession
    ):
        """Test connection-status does not modify scopes during retrieval.

        Ensures the endpoint is read-only and doesn't accidentally
        filter, sort, or transform scopes.
        """
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Store with specific order (to detect sorting)
        stored_scopes = [
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/userinfo.email",
        ]
        connection = CoreConnection(
            user_id=str(user.id),
            provider="google",
            connection_type="google",
            encrypted_access_token="encrypted_access",
            encrypted_refresh_token="encrypted_refresh",
            token_expires_at=datetime.now(timezone.utc),
            scopes=stored_scopes,
        )
        async_session.add(connection)
        await async_session.commit()

        response = await client.get(
            "/api/focused/google/connection-status",
            headers={"X-User-ID": str(user.id)},
        )

        data = response.json()
        # Must be exactly equal (same order, same values)
        assert data["scopes"] == stored_scopes, (
            f"Scopes were modified. Expected: {stored_scopes}, Got: {data['scopes']}"
        )


# =============================================================================
# Logging / Observability Tests
# =============================================================================

class TestLoggingObservability:
    """Tests for structured logging in OAuth flows.

    WARNING: Log Taxonomy is Frozen by These Tests
    -----------------------------------------------
    These tests enforce exact log message patterns. The following log events
    are now part of the contract:

    store_connection_token:
        - "[oauth] Stored connection token for user_id={user_id}"
        - "[oauth] Failed to store connection token in Redis"

    verify_connection_token:
        - "[oauth] Connection token verification failed: malformed token"
        - "[oauth] Connection token verification failed: invalid characters"
        - "[oauth] Connection token verification failed: invalid or expired (prefix=...)"
        - "[oauth] Connection token verified for user_id={user_id}"
        - "[oauth] Failed to delete connection token after verification: ..."

    store_oauth_state:
        - "[oauth] Stored state for user_id={user_id}"
        - "[oauth] Failed to store state for user_id={user_id}"

    verify_and_get_oauth_state:
        - "[oauth] State verification failed: invalid or expired state"
        - "[oauth] State verified for user_id={user_id}"
        - "[oauth] Failed to parse state data: ..."

    Renaming these events will break observability dashboards and alerts.
    """

    async def test_token_creation_logs_success(self, client, test_user):
        """Test successful token creation logs with user_id in extra."""
        log_calls = []

        def capture_log(msg, *args, **kwargs):
            log_calls.append({"msg": msg, "extra": kwargs.get("extra", {})})

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.set = AsyncMock(return_value=True)

            with patch("backend.core.google_oauth.logger") as mock_logger:
                mock_logger.info = capture_log
                mock_logger.error = capture_log
                mock_logger.warning = capture_log

                await client.post(
                    "/api/focused/google/initiate-connection",
                    headers={"X-User-ID": str(test_user.id)},
                )

        # Must log successful token creation with user_id in extra
        success_logs = [c for c in log_calls if "Stored connection token" in c["msg"]]
        assert len(success_logs) == 1, f"Expected 1 success log, got {len(success_logs)}"
        assert success_logs[0]["extra"].get("user_id") == str(test_user.id), "user_id not in log extra"

    async def test_token_creation_logs_redis_failure(self, client, test_user):
        """Test Redis failure during token creation is logged."""
        log_messages = []

        def capture_log(msg, *args, **kwargs):
            log_messages.append(msg)

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.set = AsyncMock(return_value=False)  # Redis returns False

            with patch("backend.core.google_oauth.logger") as mock_logger:
                mock_logger.info = capture_log
                mock_logger.error = capture_log
                mock_logger.warning = capture_log

                await client.post(
                    "/api/focused/google/initiate-connection",
                    headers={"X-User-ID": str(test_user.id)},
                )

        # Must log Redis failure
        error_logs = [m for m in log_messages if "Failed to store connection token" in m]
        assert len(error_logs) == 1, f"Expected 1 error log, got: {log_messages}"

    async def test_token_verification_logs_invalid_token(self, client):
        """Test invalid/expired token verification is logged."""
        log_messages = []

        def capture_log(msg, *args, **kwargs):
            log_messages.append(msg)

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)  # Token not found

            with patch("backend.core.google_oauth.logger") as mock_logger:
                mock_logger.info = capture_log
                mock_logger.error = capture_log
                mock_logger.warning = capture_log

                await client.get("/auth/google/start?token=invalid_token")

        # Must log verification failure
        warning_logs = [m for m in log_messages if "invalid or expired" in m]
        assert len(warning_logs) == 1, f"Expected 1 warning log, got: {log_messages}"

    async def test_token_verification_logs_success(self, client, test_user):
        """Test successful token verification is logged with user_id in extra."""
        log_calls = []

        def capture_log(msg, *args, **kwargs):
            log_calls.append({"msg": msg, "extra": kwargs.get("extra", {})})

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=str(test_user.id))
            mock_redis.delete = AsyncMock()
            mock_redis.set = AsyncMock(return_value=True)  # For OAuth state storage

            with patch("backend.core.google_oauth.logger") as mock_logger:
                mock_logger.info = capture_log
                mock_logger.error = capture_log
                mock_logger.warning = capture_log

                await client.get(
                    "/auth/google/start?token=valid_token",
                    follow_redirects=False,
                )

        # Must log successful verification with user_id in extra
        success_logs = [c for c in log_calls if "Connection token verified" in c["msg"]]
        assert len(success_logs) == 1, f"Expected 1 success log, got: {[c['msg'] for c in log_calls]}"
        assert success_logs[0]["extra"].get("user_id") == str(test_user.id), "user_id not in log extra"

    async def test_oauth_state_storage_logs_success(self, client, test_user):
        """Test OAuth state storage is logged with user_id in extra."""
        log_calls = []

        def capture_log(msg, *args, **kwargs):
            log_calls.append({"msg": msg, "extra": kwargs.get("extra", {})})

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=str(test_user.id))
            mock_redis.delete = AsyncMock()
            mock_redis.set = AsyncMock(return_value=True)

            with patch("backend.core.google_oauth.logger") as mock_logger:
                mock_logger.info = capture_log
                mock_logger.error = capture_log
                mock_logger.warning = capture_log

                await client.get(
                    "/auth/google/start?token=valid_token",
                    follow_redirects=False,
                )

        # Must log OAuth state storage with user_id in extra
        state_logs = [c for c in log_calls if "Stored state" in c["msg"]]
        assert len(state_logs) == 1, f"Expected 1 state log, got: {[c['msg'] for c in log_calls]}"
        assert state_logs[0]["extra"].get("user_id") == str(test_user.id), "user_id not in state log extra"

    async def test_malformed_token_logs_warning(self, client):
        """Test malformed token (whitespace) is logged as warning."""
        log_messages = []

        def capture_log(msg, *args, **kwargs):
            log_messages.append(msg)

        with patch("backend.core.google_oauth.logger") as mock_logger:
            mock_logger.info = capture_log
            mock_logger.error = capture_log
            mock_logger.warning = capture_log

            # Token with leading whitespace
            await client.get("/auth/google/start?token=%20invalid")

        # Must log malformed token warning
        warning_logs = [m for m in log_messages if "malformed token" in m]
        assert len(warning_logs) >= 1, f"Expected malformed token warning, got: {log_messages}"

    async def test_logs_do_not_contain_full_token(self, client, test_user):
        """Test logs never contain full token value (security)."""
        log_messages = []
        test_token = "abcdefghij1234567890abcdefghij1234567890abc"

        def capture_log(msg, *args, **kwargs):
            log_messages.append(str(msg))

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)  # Token not found

            with patch("backend.core.google_oauth.logger") as mock_logger:
                mock_logger.info = capture_log
                mock_logger.error = capture_log
                mock_logger.warning = capture_log

                await client.get(f"/auth/google/start?token={test_token}")

        # Full token should never appear in logs
        for msg in log_messages:
            assert test_token not in msg, f"Full token leaked in log: {msg}"


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error scenarios."""

    async def test_empty_token_rejected(self, client):
        """Test empty token parameter is rejected."""
        response = await client.get("/auth/google/start?token=")

        # Either 422 (validation) or 400 (invalid token)
        assert response.status_code in [400, 422]

    async def test_redis_failure_on_initiate(self, client, test_user):
        """Test graceful handling when Redis fails during initiation."""
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.set = AsyncMock(side_effect=Exception("Redis connection failed"))

            response = await client.post(
                "/api/focused/google/initiate-connection",
                headers={"X-User-ID": str(test_user.id)},
            )

        assert response.status_code == 500

    async def test_redis_failure_on_start(self, client):
        """Test graceful handling when Redis fails during token verification."""
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(side_effect=Exception("Redis connection failed"))

            response = await client.get(
                "/auth/google/start?token=any_token",
            )

        assert response.status_code == 500
        assert "text/html" in response.headers.get("content-type", "")
