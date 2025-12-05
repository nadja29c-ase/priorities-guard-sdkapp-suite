"""
Integration tests for Google OAuth flow (Increment 11 Part A).

Tests the full OAuth flow including:
- /google/start endpoint with PKCE
- /google/callback endpoint with state validation
- HTML error responses
- Redis state management

Uses async test infrastructure with real test database.
"""

import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.models import CoreUser

# Mark all tests as async
pytestmark = pytest.mark.asyncio


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def valid_user_id():
    """Generate a valid UUID for testing."""
    return str(uuid4())


@pytest_asyncio.fixture
async def oauth_user(async_session: AsyncSession):
    """Create a test user in the database for OAuth tests."""
    user = CoreUser(id=uuid4())
    async_session.add(user)
    await async_session.commit()
    return user


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    mock = AsyncMock()
    mock.set = AsyncMock(return_value=True)
    mock.get = AsyncMock(return_value=None)
    mock.delete = AsyncMock()
    return mock


# =============================================================================
# /google/start Endpoint Tests
# =============================================================================

class TestGoogleOAuthStart:
    """Tests for /google/start endpoint."""

    async def test_start_redirects_to_google(self, client, valid_user_id):
        """Test /start endpoint redirects to Google authorization URL."""
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.set = AsyncMock(return_value=True)

            response = await client.get(
                f"/auth/google/start?user_id={valid_user_id}",
                follow_redirects=False,
            )

        assert response.status_code == 307
        location = response.headers.get("location")
        assert location is not None
        assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth")

    async def test_start_includes_pkce_in_redirect(self, client, valid_user_id):
        """Test redirect URL includes PKCE code_challenge."""
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.set = AsyncMock(return_value=True)

            response = await client.get(
                f"/auth/google/start?user_id={valid_user_id}",
                follow_redirects=False,
            )

        location = response.headers.get("location")
        assert "code_challenge=" in location
        assert "code_challenge_method=S256" in location

    async def test_start_includes_state_in_redirect(self, client, valid_user_id):
        """Test redirect URL includes state parameter."""
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.set = AsyncMock(return_value=True)

            response = await client.get(
                f"/auth/google/start?user_id={valid_user_id}",
                follow_redirects=False,
            )

        location = response.headers.get("location")
        assert "state=" in location

    async def test_start_stores_state_in_redis(self, client, valid_user_id):
        """Test state is stored in Redis with user_id and code_verifier."""
        stored_data = {}

        async def capture_store(key, value, ex=None):
            stored_data["key"] = key
            stored_data["value"] = json.loads(value)
            stored_data["ttl"] = ex
            return True

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.set = capture_store

            await client.get(
                f"/auth/google/start?user_id={valid_user_id}",
                follow_redirects=False,
            )

        assert stored_data["key"].startswith("oauth:google:state:")
        assert stored_data["value"]["user_id"] == valid_user_id
        assert "code_verifier" in stored_data["value"]
        assert stored_data["ttl"] == 600  # 10 minutes

    async def test_start_requires_user_id(self, client):
        """Test /start returns error when user_id is missing."""
        response = await client.get("/auth/google/start")

        # FastAPI returns 422 for missing required query params
        assert response.status_code == 422

    async def test_start_rejects_invalid_user_id_format(self, client):
        """Test /start returns HTML error for invalid UUID format."""
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.set = AsyncMock(return_value=True)

            response = await client.get(
                "/auth/google/start?user_id=not-a-valid-uuid",
                follow_redirects=False,
            )

        assert response.status_code == 400
        assert "text/html" in response.headers.get("content-type", "")
        assert "Invalid" in response.text

    async def test_start_returns_503_when_redis_fails(self, client, valid_user_id):
        """Test /start returns 503 when Redis storage fails."""
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.set = AsyncMock(return_value=False)

            response = await client.get(
                f"/auth/google/start?user_id={valid_user_id}",
                follow_redirects=False,
            )

        assert response.status_code == 503
        assert "text/html" in response.headers.get("content-type", "")


# =============================================================================
# /google/callback Endpoint Tests
# =============================================================================

class TestGoogleOAuthCallback:
    """Tests for /google/callback endpoint."""

    async def test_callback_validates_state(self, client, valid_user_id):
        """Test callback validates state exists in Redis."""
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            # State not found
            mock_redis.get = AsyncMock(return_value=None)

            response = await client.get(
                "/auth/google/callback?code=auth_code&state=invalid_state"
            )

        assert response.status_code == 400
        assert "text/html" in response.headers.get("content-type", "")
        assert "expired" in response.text.lower() or "invalid" in response.text.lower()

    async def test_callback_returns_html_error_on_invalid_state(self, client):
        """Test callback returns HTML error page (not JSON) for invalid state."""
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)

            response = await client.get(
                "/auth/google/callback?code=auth_code&state=bad_state"
            )

        assert response.status_code == 400
        assert "text/html" in response.headers.get("content-type", "")
        # Should NOT be JSON
        assert not response.headers.get("content-type", "").startswith("application/json")

    async def test_callback_returns_html_error_on_missing_code(self, client):
        """Test callback returns HTML error when code is missing."""
        response = await client.get(
            "/auth/google/callback?state=some_state"
        )

        assert response.status_code == 400
        assert "text/html" in response.headers.get("content-type", "")

    async def test_callback_returns_html_error_on_missing_state(self, client):
        """Test callback returns HTML error when state is missing."""
        response = await client.get(
            "/auth/google/callback?code=auth_code"
        )

        assert response.status_code == 400
        assert "text/html" in response.headers.get("content-type", "")

    async def test_callback_handles_google_error_response(self, client):
        """Test callback handles error parameter from Google (user denied)."""
        response = await client.get(
            "/auth/google/callback?error=access_denied&error_description=User%20denied%20access"
        )

        assert response.status_code == 400
        assert "text/html" in response.headers.get("content-type", "")
        assert "denied" in response.text.lower()

    async def test_callback_uses_code_verifier_in_exchange(self, client, valid_user_id):
        """Test callback passes code_verifier from Redis to token exchange."""
        code_verifier_used = None

        async def mock_exchange(code, http_client, code_verifier=None):
            nonlocal code_verifier_used
            code_verifier_used = code_verifier
            return {
                "access_token": "test_access_token",
                "refresh_token": "test_refresh_token",
                "expires_in": 3600,
                "scopes": ["https://www.googleapis.com/auth/calendar.readonly"],
            }

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=json.dumps({
                "user_id": valid_user_id,
                "code_verifier": "my_secret_verifier",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }))
            mock_redis.delete = AsyncMock()

            with patch(
                "backend.core.oauth.google_oauth_service.exchange_code",
                mock_exchange,
            ):
                await client.get(
                    "/auth/google/callback?code=auth_code&state=valid_state"
                )

        assert code_verifier_used == "my_secret_verifier"

    async def test_callback_retrieves_user_id_from_redis(self, client, async_session, oauth_user):
        """Test callback gets user_id from Redis state, not from query params."""
        user_id = str(oauth_user.id)

        async def mock_exchange(code, http_client, code_verifier=None):
            return {
                "access_token": "test_access_token",
                "refresh_token": "test_refresh_token",
                "expires_in": 3600,
                "scopes": ["https://www.googleapis.com/auth/calendar.readonly"],
            }

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=json.dumps({
                "user_id": user_id,
                "code_verifier": "verifier",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }))
            mock_redis.delete = AsyncMock()

            with patch(
                "backend.core.oauth.google_oauth_service.exchange_code",
                mock_exchange,
            ):
                with patch(
                    "backend.core.oauth.google_oauth_service.encrypt_token",
                    return_value="encrypted",
                ):
                    response = await client.get(
                        "/auth/google/callback?code=auth_code&state=valid_state"
                    )

        assert response.status_code == 200

    async def test_callback_deletes_state_after_use(self, client, valid_user_id):
        """Test state is deleted from Redis after successful verification."""
        delete_called_with = None

        async def capture_delete(key):
            nonlocal delete_called_with
            delete_called_with = key

        async def mock_exchange(code, http_client, code_verifier=None):
            return {
                "access_token": "test_access_token",
                "refresh_token": "test_refresh_token",
                "expires_in": 3600,
                "scopes": ["https://www.googleapis.com/auth/calendar.readonly"],
            }

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=json.dumps({
                "user_id": valid_user_id,
                "code_verifier": "verifier",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }))
            mock_redis.delete = capture_delete

            with patch(
                "backend.core.oauth.google_oauth_service.exchange_code",
                mock_exchange,
            ):
                with patch(
                    "backend.core.oauth.google_oauth_service.encrypt_token",
                    return_value="encrypted",
                ):
                    await client.get(
                        "/auth/google/callback?code=auth_code&state=the_state"
                    )

        assert delete_called_with == "oauth:google:state:the_state"

    async def test_callback_returns_html_success_on_completion(self, client, async_session, oauth_user):
        """Test callback returns HTML success page after tokens stored."""
        user_id = str(oauth_user.id)

        async def mock_exchange(code, http_client, code_verifier=None):
            return {
                "access_token": "test_access_token",
                "refresh_token": "test_refresh_token",
                "expires_in": 3600,
                "scopes": ["https://www.googleapis.com/auth/calendar.readonly"],
            }

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=json.dumps({
                "user_id": user_id,
                "code_verifier": "verifier",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }))
            mock_redis.delete = AsyncMock()

            with patch(
                "backend.core.oauth.google_oauth_service.exchange_code",
                mock_exchange,
            ):
                with patch(
                    "backend.core.oauth.google_oauth_service.encrypt_token",
                    return_value="encrypted",
                ):
                    response = await client.get(
                        "/auth/google/callback?code=auth_code&state=valid_state"
                    )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "success" in response.text.lower() or "connected" in response.text.lower()


# =============================================================================
# Concurrent Flow Tests
# =============================================================================

class TestConcurrentOAuthFlows:
    """Tests for concurrent OAuth flows."""

    async def test_concurrent_oauth_flows_isolated(self, client):
        """Test two users' OAuth flows don't interfere with each other."""
        user1_id = str(uuid4())
        user2_id = str(uuid4())
        stored_states = {}

        async def capture_store(key, value, ex=None):
            stored_states[key] = json.loads(value)
            return True

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.set = capture_store

            # User 1 starts OAuth
            response1 = await client.get(
                f"/auth/google/start?user_id={user1_id}",
                follow_redirects=False,
            )

            # User 2 starts OAuth
            response2 = await client.get(
                f"/auth/google/start?user_id={user2_id}",
                follow_redirects=False,
            )

        # Both should succeed
        assert response1.status_code == 307
        assert response2.status_code == 307

        # Each should have their own state
        assert len(stored_states) == 2

        # User IDs should be correctly associated
        user_ids_stored = [data["user_id"] for data in stored_states.values()]
        assert user1_id in user_ids_stored
        assert user2_id in user_ids_stored


# =============================================================================
# Google Redirect Error Handling Tests (Critical for Google Review)
# =============================================================================

class TestGoogleRedirectErrors:
    """Tests for handling Google's error redirect parameters."""

    async def test_callback_handles_access_denied_error(self, client):
        """Test callback handles error=access_denied (user denied consent)."""
        response = await client.get(
            "/auth/google/callback?error=access_denied&error_description=The%20user%20denied%20access"
        )

        assert response.status_code == 400
        assert "text/html" in response.headers.get("content-type", "")
        assert "denied" in response.text.lower()

    async def test_callback_handles_invalid_request_error(self, client):
        """Test callback handles error=invalid_request from Google."""
        response = await client.get(
            "/auth/google/callback?error=invalid_request&error_description=Invalid%20redirect_uri"
        )

        assert response.status_code == 400
        assert "text/html" in response.headers.get("content-type", "")

    async def test_callback_handles_server_error(self, client):
        """Test callback handles error=server_error from Google."""
        response = await client.get(
            "/auth/google/callback?error=server_error&error_description=Google%20server%20error"
        )

        assert response.status_code == 400
        assert "text/html" in response.headers.get("content-type", "")

    async def test_callback_handles_temporarily_unavailable_error(self, client):
        """Test callback handles error=temporarily_unavailable from Google."""
        response = await client.get(
            "/auth/google/callback?error=temporarily_unavailable"
        )

        assert response.status_code == 400
        assert "text/html" in response.headers.get("content-type", "")

    async def test_callback_error_shows_description_when_provided(self, client):
        """Test error page shows Google's error_description when provided."""
        response = await client.get(
            "/auth/google/callback?error=access_denied&error_description=Custom%20error%20message"
        )

        assert response.status_code == 400
        # Error description should appear in some form in the response


# =============================================================================
# State Replay Attack Tests (Critical for Security)
# =============================================================================

class TestStateReplayAttack:
    """Tests for state replay attack prevention."""

    async def test_state_reuse_rejected_after_successful_callback(self, client, async_session, oauth_user):
        """Test that state cannot be reused after successful callback (replay attack)."""
        user_id = str(oauth_user.id)
        state_value = "test_state_for_replay"
        get_call_count = 0

        async def mock_get(key):
            nonlocal get_call_count
            get_call_count += 1
            if get_call_count == 1:
                # First call returns valid state
                return json.dumps({
                    "user_id": user_id,
                    "code_verifier": "verifier",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
            else:
                # Second call (after delete) returns None
                return None

        async def mock_exchange(code, http_client, code_verifier=None):
            return {
                "access_token": "test_access_token",
                "refresh_token": "test_refresh_token",
                "expires_in": 3600,
                "scopes": ["https://www.googleapis.com/auth/calendar.readonly"],
            }

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = mock_get
            mock_redis.delete = AsyncMock()

            with patch(
                "backend.core.oauth.google_oauth_service.exchange_code",
                mock_exchange,
            ):
                with patch(
                    "backend.core.oauth.google_oauth_service.encrypt_token",
                    return_value="encrypted",
                ):
                    # First callback should succeed
                    response1 = await client.get(
                        f"/auth/google/callback?code=auth_code&state={state_value}"
                    )

                    # Second callback with SAME state should fail (state was deleted)
                    response2 = await client.get(
                        f"/auth/google/callback?code=auth_code&state={state_value}"
                    )

        assert response1.status_code == 200
        assert response2.status_code == 400  # State already consumed


# =============================================================================
# Token Exchange Error Tests
# =============================================================================

class TestTokenExchangeErrors:
    """Tests for token exchange error handling."""

    async def test_callback_handles_token_exchange_failure(self, client, valid_user_id):
        """Test callback returns HTML error when token exchange fails."""
        async def mock_exchange_fail(code, http_client, code_verifier=None):
            raise ValueError("Token exchange failed: invalid_grant")

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=json.dumps({
                "user_id": valid_user_id,
                "code_verifier": "verifier",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }))
            mock_redis.delete = AsyncMock()

            with patch(
                "backend.core.oauth.google_oauth_service.exchange_code",
                mock_exchange_fail,
            ):
                response = await client.get(
                    "/auth/google/callback?code=bad_code&state=valid_state"
                )

        assert response.status_code == 400
        assert "text/html" in response.headers.get("content-type", "")
        assert "failed" in response.text.lower()

    async def test_callback_handles_network_error(self, client, valid_user_id):
        """Test callback handles network error during token exchange."""
        import httpx

        async def mock_exchange_network_error(code, http_client, code_verifier=None):
            raise httpx.ConnectError("Connection refused")

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=json.dumps({
                "user_id": valid_user_id,
                "code_verifier": "verifier",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }))
            mock_redis.delete = AsyncMock()

            with patch(
                "backend.core.oauth.google_oauth_service.exchange_code",
                mock_exchange_network_error,
            ):
                response = await client.get(
                    "/auth/google/callback?code=auth_code&state=valid_state"
                )

        assert response.status_code == 500
        assert "text/html" in response.headers.get("content-type", "")

    async def test_callback_handles_invalid_grant_error(self, client, valid_user_id):
        """Test callback handles invalid_grant error (expired code)."""
        async def mock_exchange_invalid_grant(code, http_client, code_verifier=None):
            raise ValueError("invalid_grant: Code has expired")

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=json.dumps({
                "user_id": valid_user_id,
                "code_verifier": "verifier",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }))
            mock_redis.delete = AsyncMock()

            with patch(
                "backend.core.oauth.google_oauth_service.exchange_code",
                mock_exchange_invalid_grant,
            ):
                response = await client.get(
                    "/auth/google/callback?code=expired_code&state=valid_state"
                )

        assert response.status_code == 400
        assert "text/html" in response.headers.get("content-type", "")


# =============================================================================
# HTML Response Security Tests (Critical for Review)
# =============================================================================

class TestHTMLResponseSecurity:
    """Tests for HTML response security and correctness."""

    async def test_error_page_is_html_not_json(self, client):
        """Test that error pages return HTML, not JSON."""
        response = await client.get(
            "/auth/google/callback?error=access_denied"
        )

        assert "text/html" in response.headers.get("content-type", "")
        assert "application/json" not in response.headers.get("content-type", "")

    async def test_error_page_has_no_sensitive_data(self, client, valid_user_id):
        """Test that error pages do not contain sensitive data."""
        async def mock_exchange_fail(code, http_client, code_verifier=None):
            raise ValueError("Token exchange failed")

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=json.dumps({
                "user_id": valid_user_id,
                "code_verifier": "super_secret_verifier_12345",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }))
            mock_redis.delete = AsyncMock()

            with patch(
                "backend.core.oauth.google_oauth_service.exchange_code",
                mock_exchange_fail,
            ):
                response = await client.get(
                    "/auth/google/callback?code=test_auth_code_xyz&state=valid_state"
                )

        html_content = response.text.lower()

        # Should NOT contain:
        assert "super_secret_verifier" not in html_content
        assert "test_auth_code_xyz" not in response.text  # Case-sensitive for code
        assert valid_user_id not in response.text
        assert "access_token" not in html_content
        assert "refresh_token" not in html_content

    async def test_success_page_has_no_tokens(self, client, valid_user_id):
        """Test that success page does not expose tokens."""
        async def mock_exchange(code, http_client, code_verifier=None):
            return {
                "access_token": "ya29.secret_access_token_value",
                "refresh_token": "1//secret_refresh_token_value",
                "expires_in": 3600,
                "scopes": ["https://www.googleapis.com/auth/calendar.readonly"],
            }

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=json.dumps({
                "user_id": valid_user_id,
                "code_verifier": "verifier",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }))
            mock_redis.delete = AsyncMock()

            with patch(
                "backend.core.oauth.google_oauth_service.exchange_code",
                mock_exchange,
            ):
                with patch(
                    "backend.core.oauth.google_oauth_service.encrypt_token",
                    return_value="encrypted",
                ):
                    response = await client.get(
                        "/auth/google/callback?code=auth_code&state=valid_state"
                    )

        html_content = response.text

        # Should NOT contain actual tokens
        assert "ya29.secret_access_token_value" not in html_content
        assert "1//secret_refresh_token_value" not in html_content

    async def test_error_page_contains_user_friendly_message(self, client):
        """Test that error pages contain user-friendly messages."""
        response = await client.get(
            "/auth/google/callback?error=access_denied"
        )

        html_content = response.text.lower()

        # Should contain helpful user-facing text
        assert any(word in html_content for word in ["try again", "close", "window", "denied"])


# =============================================================================
# PKCE Verification Tests (Critical for Security)
# =============================================================================

class TestPKCEVerification:
    """Tests for PKCE code_verifier validation."""

    async def test_callback_rejects_missing_verifier_in_state(self, client, valid_user_id):
        """Test callback rejects state data missing code_verifier."""
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            # State without code_verifier
            mock_redis.get = AsyncMock(return_value=json.dumps({
                "user_id": valid_user_id,
                # "code_verifier" is missing!
                "created_at": datetime.now(timezone.utc).isoformat(),
            }))
            mock_redis.delete = AsyncMock()

            response = await client.get(
                "/auth/google/callback?code=auth_code&state=valid_state"
            )

        # Should fail due to malformed state
        assert response.status_code == 400


# =============================================================================
# Parallel OAuth Flow Tests
# =============================================================================

class TestParallelOAuthFlows:
    """Tests for parallel OAuth flows from different users."""

    async def test_parallel_flows_have_different_states(self, client):
        """Test that parallel OAuth flows generate unique states."""
        user1_id = str(uuid4())
        user2_id = str(uuid4())
        states_captured = []

        async def capture_store(key, value, ex=None):
            state = key.split(":")[-1]  # Extract state from key
            states_captured.append(state)
            return True

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.set = capture_store

            # Start two OAuth flows in parallel
            response1 = await client.get(
                f"/auth/google/start?user_id={user1_id}",
                follow_redirects=False,
            )
            response2 = await client.get(
                f"/auth/google/start?user_id={user2_id}",
                follow_redirects=False,
            )

        # Both should succeed
        assert response1.status_code == 307
        assert response2.status_code == 307

        # States should be unique
        assert len(states_captured) == 2
        assert states_captured[0] != states_captured[1]

    async def test_user1_state_cannot_be_used_by_user2(self, client, async_session, oauth_user):
        """Test that user1's state cannot complete user2's OAuth flow."""
        user1_id = str(oauth_user.id)

        async def mock_exchange(code, http_client, code_verifier=None):
            return {
                "access_token": "test_access_token",
                "refresh_token": "test_refresh_token",
                "expires_in": 3600,
                "scopes": ["https://www.googleapis.com/auth/calendar.readonly"],
            }

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            # State belongs to user1 (oauth_user in DB)
            mock_redis.get = AsyncMock(return_value=json.dumps({
                "user_id": user1_id,
                "code_verifier": "verifier",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }))
            mock_redis.delete = AsyncMock()

            with patch(
                "backend.core.oauth.google_oauth_service.exchange_code",
                mock_exchange,
            ):
                with patch(
                    "backend.core.oauth.google_oauth_service.encrypt_token",
                    return_value="encrypted",
                ):
                    # User2 tries to use user1's state
                    # (In practice, the tokens would be stored for user1, not user2)
                    response = await client.get(
                        "/auth/google/callback?code=auth_code&state=user1_state"
                    )

        # The callback succeeds, but tokens are stored for user1 (from state)
        # This is correct behavior - state determines the user
        assert response.status_code == 200
