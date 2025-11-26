"""
Integration tests for Google OAuth flow (Increment 11 Part A).

Tests the full OAuth flow including:
- /google/start endpoint with PKCE
- /google/callback endpoint with state validation
- HTML error responses
- Redis state management
"""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from httpx import Response

from backend.main import app


@pytest.fixture
def client():
    """Create test client with proper lifespan handling."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def valid_user_id():
    """Generate a valid UUID for testing."""
    return str(uuid4())


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

    def test_start_redirects_to_google(self, client, valid_user_id):
        """Test /start endpoint redirects to Google authorization URL."""
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.set = AsyncMock(return_value=True)

            response = client.get(
                f"/auth/focused/google/start?user_id={valid_user_id}",
                follow_redirects=False,
            )

        assert response.status_code == 307
        location = response.headers.get("location")
        assert location is not None
        assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth")

    # Note: Full paths are /auth/focused/google/start and /auth/focused/google/callback
    # because main.py mounts oauth_google_router with prefix="/auth/focused/google"

    def test_start_includes_pkce_in_redirect(self, client, valid_user_id):
        """Test redirect URL includes PKCE code_challenge."""
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.set = AsyncMock(return_value=True)

            response = client.get(
                f"/auth/focused/google/start?user_id={valid_user_id}",
                follow_redirects=False,
            )

        location = response.headers.get("location")
        assert "code_challenge=" in location
        assert "code_challenge_method=S256" in location

    def test_start_includes_state_in_redirect(self, client, valid_user_id):
        """Test redirect URL includes state parameter."""
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.set = AsyncMock(return_value=True)

            response = client.get(
                f"/auth/focused/google/start?user_id={valid_user_id}",
                follow_redirects=False,
            )

        location = response.headers.get("location")
        assert "state=" in location

    def test_start_stores_state_in_redis(self, client, valid_user_id):
        """Test state is stored in Redis with user_id and code_verifier."""
        stored_data = {}

        async def capture_store(key, value, ex=None):
            stored_data["key"] = key
            stored_data["value"] = json.loads(value)
            stored_data["ttl"] = ex
            return True

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.set = capture_store

            client.get(
                f"/auth/focused/google/start?user_id={valid_user_id}",
                follow_redirects=False,
            )

        assert stored_data["key"].startswith("oauth:google:state:")
        assert stored_data["value"]["user_id"] == valid_user_id
        assert "code_verifier" in stored_data["value"]
        assert stored_data["ttl"] == 600  # 10 minutes

    def test_start_requires_user_id(self, client):
        """Test /start returns error when user_id is missing."""
        response = client.get("/auth/focused/google/start")

        # FastAPI returns 422 for missing required query params
        assert response.status_code == 422

    def test_start_rejects_invalid_user_id_format(self, client):
        """Test /start returns HTML error for invalid UUID format."""
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.set = AsyncMock(return_value=True)

            response = client.get(
                "/auth/focused/google/start?user_id=not-a-valid-uuid",
                follow_redirects=False,
            )

        assert response.status_code == 400
        assert "text/html" in response.headers.get("content-type", "")
        assert "Invalid" in response.text

    def test_start_returns_503_when_redis_fails(self, client, valid_user_id):
        """Test /start returns 503 when Redis storage fails."""
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.set = AsyncMock(return_value=False)

            response = client.get(
                f"/auth/focused/google/start?user_id={valid_user_id}",
                follow_redirects=False,
            )

        assert response.status_code == 503
        assert "text/html" in response.headers.get("content-type", "")


# =============================================================================
# /google/callback Endpoint Tests
# =============================================================================

class TestGoogleOAuthCallback:
    """Tests for /google/callback endpoint."""

    def test_callback_validates_state(self, client, valid_user_id):
        """Test callback validates state exists in Redis."""
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            # State not found
            mock_redis.get = AsyncMock(return_value=None)

            response = client.get(
                "/auth/focused/google/callback?code=auth_code&state=invalid_state"
            )

        assert response.status_code == 400
        assert "text/html" in response.headers.get("content-type", "")
        assert "expired" in response.text.lower() or "invalid" in response.text.lower()

    def test_callback_returns_html_error_on_invalid_state(self, client):
        """Test callback returns HTML error page (not JSON) for invalid state."""
        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=None)

            response = client.get(
                "/auth/focused/google/callback?code=auth_code&state=bad_state"
            )

        assert response.status_code == 400
        assert "text/html" in response.headers.get("content-type", "")
        # Should NOT be JSON
        assert not response.headers.get("content-type", "").startswith("application/json")

    def test_callback_returns_html_error_on_missing_code(self, client):
        """Test callback returns HTML error when code is missing."""
        response = client.get(
            "/auth/focused/google/callback?state=some_state"
        )

        assert response.status_code == 400
        assert "text/html" in response.headers.get("content-type", "")

    def test_callback_returns_html_error_on_missing_state(self, client):
        """Test callback returns HTML error when state is missing."""
        response = client.get(
            "/auth/focused/google/callback?code=auth_code"
        )

        assert response.status_code == 400
        assert "text/html" in response.headers.get("content-type", "")

    def test_callback_handles_google_error_response(self, client):
        """Test callback handles error parameter from Google (user denied)."""
        response = client.get(
            "/auth/focused/google/callback?error=access_denied&error_description=User%20denied%20access"
        )

        assert response.status_code == 400
        assert "text/html" in response.headers.get("content-type", "")
        assert "denied" in response.text.lower()

    def test_callback_uses_code_verifier_in_exchange(self, client, valid_user_id):
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
                "backend.apps.focused.routers.oauth_google_router.exchange_code",
                mock_exchange,
            ):
                client.get(
                    "/auth/focused/google/callback?code=auth_code&state=valid_state"
                )

        assert code_verifier_used == "my_secret_verifier"

    def test_callback_retrieves_user_id_from_redis(self, client, valid_user_id):
        """Test callback gets user_id from Redis state, not from query params."""
        stored_user_id = None

        async def mock_exchange(code, http_client, code_verifier=None):
            return {
                "access_token": "test_access_token",
                "refresh_token": "test_refresh_token",
                "expires_in": 3600,
                "scopes": ["https://www.googleapis.com/auth/calendar.readonly"],
            }

        with patch("backend.core.google_oauth.redis_client") as mock_redis:
            # user_id is "redis_user" in Redis, not "query_user"
            mock_redis.get = AsyncMock(return_value=json.dumps({
                "user_id": valid_user_id,
                "code_verifier": "verifier",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }))
            mock_redis.delete = AsyncMock()

            with patch(
                "backend.apps.focused.routers.oauth_google_router.exchange_code",
                mock_exchange,
            ):
                with patch(
                    "backend.apps.focused.routers.oauth_google_router.encrypt_token",
                    return_value="encrypted",
                ):
                    # Note: No user_id in query params - it comes from Redis
                    response = client.get(
                        "/auth/focused/google/callback?code=auth_code&state=valid_state"
                    )

        # Should succeed because user_id comes from Redis
        assert response.status_code == 200

    def test_callback_deletes_state_after_use(self, client, valid_user_id):
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
                "backend.apps.focused.routers.oauth_google_router.exchange_code",
                mock_exchange,
            ):
                with patch(
                    "backend.apps.focused.routers.oauth_google_router.encrypt_token",
                    return_value="encrypted",
                ):
                    client.get(
                        "/auth/focused/google/callback?code=auth_code&state=the_state"
                    )

        assert delete_called_with == "oauth:google:state:the_state"

    def test_callback_returns_html_success_on_completion(self, client, valid_user_id):
        """Test callback returns HTML success page after tokens stored."""
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
            mock_redis.delete = AsyncMock()

            with patch(
                "backend.apps.focused.routers.oauth_google_router.exchange_code",
                mock_exchange,
            ):
                with patch(
                    "backend.apps.focused.routers.oauth_google_router.encrypt_token",
                    return_value="encrypted",
                ):
                    response = client.get(
                        "/auth/focused/google/callback?code=auth_code&state=valid_state"
                    )

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "success" in response.text.lower() or "connected" in response.text.lower()


# =============================================================================
# Concurrent Flow Tests
# =============================================================================

class TestConcurrentOAuthFlows:
    """Tests for concurrent OAuth flows."""

    def test_concurrent_oauth_flows_isolated(self, client):
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
            response1 = client.get(
                f"/auth/focused/google/start?user_id={user1_id}",
                follow_redirects=False,
            )

            # User 2 starts OAuth
            response2 = client.get(
                f"/auth/focused/google/start?user_id={user2_id}",
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
# Token Exchange Error Tests
# =============================================================================

class TestTokenExchangeErrors:
    """Tests for token exchange error handling."""

    def test_callback_handles_token_exchange_failure(self, client, valid_user_id):
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
                "backend.apps.focused.routers.oauth_google_router.exchange_code",
                mock_exchange_fail,
            ):
                response = client.get(
                    "/auth/focused/google/callback?code=bad_code&state=valid_state"
                )

        assert response.status_code == 400
        assert "text/html" in response.headers.get("content-type", "")
        assert "failed" in response.text.lower()
