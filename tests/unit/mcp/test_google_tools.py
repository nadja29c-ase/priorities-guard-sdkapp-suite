"""
Unit tests for shared Google connection MCP tools (Increment 18).

Tests:
- connect_google_calendar_logic function
- disconnect_google_calendar_logic function
- Tool scope mappings

KNOWN SECURITY ISSUE - MUST FIX IN INCREMENT 19 OR 20:
=======================================================
disconnect_google_calendar_logic silently reports success even when the
backend returns an error (e.g., token revocation failed). This is dangerous:

    - User believes they revoked access, but Google token remains active
    - UI shows "disconnected" but access persists
    - Audit trail is misleading
    - User trust is violated

See: test_disconnect_response_error_status
See: test_disconnect_response_status_none

The fix should:
1. Check backend response for error/failure status
2. Return success=False with appropriate error message
3. Consider retry logic for transient failures
4. Log the failure for operational visibility
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from mcp_server.shared.google_tools import (
    connect_google_calendar_logic,
    disconnect_google_calendar_logic,
    CONNECT_GOOGLE_CALENDAR_DESCRIPTION,
    DISCONNECT_GOOGLE_CALENDAR_DESCRIPTION,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_auth_context():
    """Return a mock auth context."""
    return {
        "user_id": "test-user-123",
        "correlation_id": "corr-456",
        "scopes": {"focused.write"},
    }


@pytest.fixture
def mock_authenticate():
    """Create a mock authenticate function."""
    async def _authenticate(tool_name, meta):
        return {
            "user_id": "test-user-123",
            "correlation_id": "corr-456",
            "scopes": {"focused.write"},
        }
    return _authenticate


@pytest.fixture
def mock_logger():
    """Create a mock logger."""
    logger = MagicMock()
    logger.info = MagicMock()
    logger.warning = MagicMock()
    logger.error = MagicMock()
    return logger


# =============================================================================
# connect_google_calendar_logic Tests
# =============================================================================

class TestConnectGoogleCalendarLogic:
    """Tests for connect_google_calendar_logic function."""

    @pytest.mark.asyncio
    async def test_returns_connected_when_already_connected(
        self, mock_authenticate, mock_logger
    ):
        """Test returns connected status when user already has Google connection."""
        async def mock_get(path, user_id, correlation_id):
            return {
                "connected": True,
                "connected_at": "2025-01-15T10:30:00Z",
                "scopes": ["https://www.googleapis.com/auth/calendar.readonly"],
            }

        result = await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=mock_get,
            backend_post_fn=AsyncMock(),
            logger=mock_logger,
        )

        data = json.loads(result)
        assert data["success"] is True
        assert data["data"]["status"] == "connected"
        assert data["data"]["connected_at"] == "2025-01-15T10:30:00Z"
        assert "already connected" in data["data"]["message"].lower()

    @pytest.mark.asyncio
    async def test_returns_connect_url_when_not_connected(
        self, mock_authenticate, mock_logger
    ):
        """Test returns connect URL when user is not connected."""
        async def mock_get(path, user_id, correlation_id):
            return {"connected": False}

        async def mock_post(path, payload, user_id, correlation_id):
            return {
                "token": "opaque_token_123",
                "connect_url": "https://example.com/start?token=opaque_token_123",
                "expires_in": 600,
            }

        result = await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=mock_get,
            backend_post_fn=mock_post,
            logger=mock_logger,
        )

        data = json.loads(result)
        assert data["success"] is True
        assert data["data"]["status"] == "not_connected"
        assert "connect_url" in data["data"]
        assert data["data"]["expires_in"] == 600
        assert "10 minutes" in data["data"]["message"]

    @pytest.mark.asyncio
    async def test_calls_connection_status_endpoint(
        self, mock_authenticate, mock_logger
    ):
        """Test calls the correct backend endpoint for status check."""
        called_path = None

        async def mock_get(path, user_id, correlation_id):
            nonlocal called_path
            called_path = path
            return {"connected": True, "connected_at": None}

        await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=mock_get,
            backend_post_fn=AsyncMock(),
            logger=mock_logger,
        )

        assert called_path == "/api/focused/google/connection-status"

    @pytest.mark.asyncio
    async def test_calls_initiate_endpoint_when_not_connected(
        self, mock_authenticate, mock_logger
    ):
        """Test calls initiate endpoint only when not connected."""
        post_called_path = None

        async def mock_get(path, user_id, correlation_id):
            return {"connected": False}

        async def mock_post(path, payload, user_id, correlation_id):
            nonlocal post_called_path
            post_called_path = path
            return {"token": "t", "connect_url": "url", "expires_in": 600}

        await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=mock_get,
            backend_post_fn=mock_post,
            logger=mock_logger,
        )

        assert post_called_path == "/api/focused/google/initiate-connection"

    @pytest.mark.asyncio
    async def test_does_not_call_initiate_when_connected(
        self, mock_authenticate, mock_logger
    ):
        """Test does not call initiate endpoint when already connected."""
        post_called = False

        async def mock_get(path, user_id, correlation_id):
            return {"connected": True, "connected_at": "2025-01-01"}

        async def mock_post(path, payload, user_id, correlation_id):
            nonlocal post_called
            post_called = True
            return {}

        await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=mock_get,
            backend_post_fn=mock_post,
            logger=mock_logger,
        )

        assert post_called is False

    @pytest.mark.asyncio
    async def test_passes_user_id_to_backend(
        self, mock_logger
    ):
        """Test passes authenticated user_id to backend calls."""
        received_user_id = None

        async def mock_auth(tool_name, meta):
            return {"user_id": "specific-user-789", "correlation_id": "c"}

        async def mock_get(path, user_id, correlation_id):
            nonlocal received_user_id
            received_user_id = user_id
            return {"connected": True, "connected_at": None}

        await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_auth,
            backend_get_fn=mock_get,
            backend_post_fn=AsyncMock(),
            logger=mock_logger,
        )

        assert received_user_id == "specific-user-789"

    @pytest.mark.asyncio
    async def test_passes_correlation_id_to_backend_get(
        self, mock_logger
    ):
        """Test passes correlation_id from auth to backend GET calls."""
        received_correlation_id = None

        async def mock_auth(tool_name, meta):
            return {"user_id": "user-123", "correlation_id": "corr-trace-abc-123"}

        async def mock_get(path, user_id, correlation_id):
            nonlocal received_correlation_id
            received_correlation_id = correlation_id
            return {"connected": True, "connected_at": None}

        await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_auth,
            backend_get_fn=mock_get,
            backend_post_fn=AsyncMock(),
            logger=mock_logger,
        )

        assert received_correlation_id == "corr-trace-abc-123"

    @pytest.mark.asyncio
    async def test_passes_correlation_id_to_backend_post(
        self, mock_logger
    ):
        """Test passes correlation_id from auth to backend POST calls."""
        received_correlation_id = None

        async def mock_auth(tool_name, meta):
            return {"user_id": "user-123", "correlation_id": "corr-trace-xyz-789"}

        async def mock_get(path, user_id, correlation_id):
            return {"connected": False}

        async def mock_post(path, payload, user_id, correlation_id):
            nonlocal received_correlation_id
            received_correlation_id = correlation_id
            return {"token": "t", "connect_url": "url", "expires_in": 600}

        await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_auth,
            backend_get_fn=mock_get,
            backend_post_fn=mock_post,
            logger=mock_logger,
        )

        assert received_correlation_id == "corr-trace-xyz-789"

    @pytest.mark.asyncio
    async def test_passes_both_user_id_and_correlation_id_to_backend(
        self, mock_logger
    ):
        """Test both user_id and correlation_id are correctly propagated."""
        captured_get = {"user_id": None, "correlation_id": None}
        captured_post = {"user_id": None, "correlation_id": None}

        async def mock_auth(tool_name, meta):
            return {"user_id": "user-abc", "correlation_id": "corr-def"}

        async def mock_get(path, user_id, correlation_id):
            captured_get["user_id"] = user_id
            captured_get["correlation_id"] = correlation_id
            return {"connected": False}

        async def mock_post(path, payload, user_id, correlation_id):
            captured_post["user_id"] = user_id
            captured_post["correlation_id"] = correlation_id
            return {"token": "t", "connect_url": "url", "expires_in": 600}

        await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_auth,
            backend_get_fn=mock_get,
            backend_post_fn=mock_post,
            logger=mock_logger,
        )

        # Verify GET call
        assert captured_get["user_id"] == "user-abc"
        assert captured_get["correlation_id"] == "corr-def"

        # Verify POST call
        assert captured_post["user_id"] == "user-abc"
        assert captured_post["correlation_id"] == "corr-def"


# =============================================================================
# disconnect_google_calendar_logic Tests
# =============================================================================

class TestDisconnectGoogleCalendarLogic:
    """Tests for disconnect_google_calendar_logic function."""

    @pytest.mark.asyncio
    async def test_requires_confirmation(self, mock_authenticate, mock_logger):
        """Test returns error when confirm=False."""
        result = await disconnect_google_calendar_logic(
            confirm=False,
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=AsyncMock(),
            backend_post_fn=AsyncMock(),
            logger=mock_logger,
        )

        data = json.loads(result)
        assert data["success"] is False
        assert data["error"]["code"] == "CONFIRMATION_REQUIRED"
        assert "confirm=true" in data["error"]["message"]

    @pytest.mark.asyncio
    async def test_returns_not_connected_when_no_connection(
        self, mock_authenticate, mock_logger
    ):
        """Test returns not_connected when user has no Google connection."""
        async def mock_get(path, user_id, correlation_id):
            return {"connected": False}

        result = await disconnect_google_calendar_logic(
            confirm=True,
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=mock_get,
            backend_post_fn=AsyncMock(),
            logger=mock_logger,
        )

        data = json.loads(result)
        assert data["success"] is True
        assert data["data"]["status"] == "not_connected"

    @pytest.mark.asyncio
    async def test_calls_disconnect_endpoint_when_connected(
        self, mock_authenticate, mock_logger
    ):
        """Test calls disconnect endpoint when user is connected."""
        post_called_path = None

        async def mock_get(path, user_id, correlation_id):
            return {"connected": True}

        async def mock_post(path, payload, user_id, correlation_id):
            nonlocal post_called_path
            post_called_path = path
            return {"status": "disconnected"}

        result = await disconnect_google_calendar_logic(
            confirm=True,
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=mock_get,
            backend_post_fn=mock_post,
            logger=mock_logger,
        )

        assert post_called_path == "/api/focused/disconnect"
        data = json.loads(result)
        assert data["success"] is True
        assert data["data"]["status"] == "disconnected"

    @pytest.mark.asyncio
    async def test_does_not_call_disconnect_without_confirmation(
        self, mock_authenticate, mock_logger
    ):
        """Test does not call disconnect when confirm=False."""
        post_called = False

        async def mock_post(path, payload, user_id, correlation_id):
            nonlocal post_called
            post_called = True
            return {}

        await disconnect_google_calendar_logic(
            confirm=False,
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=AsyncMock(),
            backend_post_fn=mock_post,
            logger=mock_logger,
        )

        assert post_called is False

    @pytest.mark.asyncio
    async def test_does_not_call_disconnect_when_not_connected(
        self, mock_authenticate, mock_logger
    ):
        """Test does not call disconnect when already not connected."""
        post_called = False

        async def mock_get(path, user_id, correlation_id):
            return {"connected": False}

        async def mock_post(path, payload, user_id, correlation_id):
            nonlocal post_called
            post_called = True
            return {}

        await disconnect_google_calendar_logic(
            confirm=True,
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=mock_get,
            backend_post_fn=mock_post,
            logger=mock_logger,
        )

        assert post_called is False

    @pytest.mark.asyncio
    async def test_returns_success_message_after_disconnect(
        self, mock_authenticate, mock_logger
    ):
        """Test returns user-friendly success message after disconnect."""
        async def mock_get(path, user_id, correlation_id):
            return {"connected": True}

        async def mock_post(path, payload, user_id, correlation_id):
            return {"status": "disconnected"}

        result = await disconnect_google_calendar_logic(
            confirm=True,
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=mock_get,
            backend_post_fn=mock_post,
            logger=mock_logger,
        )

        data = json.loads(result)
        assert "disconnected" in data["data"]["message"].lower()
        assert "removed" in data["data"]["message"].lower()

    @pytest.mark.asyncio
    async def test_passes_correlation_id_to_backend(
        self, mock_logger
    ):
        """Test passes correlation_id from auth to backend calls."""
        captured_get = {"correlation_id": None}
        captured_post = {"correlation_id": None}

        async def mock_auth(tool_name, meta):
            return {"user_id": "user-123", "correlation_id": "disconnect-corr-id"}

        async def mock_get(path, user_id, correlation_id):
            captured_get["correlation_id"] = correlation_id
            return {"connected": True}

        async def mock_post(path, payload, user_id, correlation_id):
            captured_post["correlation_id"] = correlation_id
            return {"status": "disconnected"}

        await disconnect_google_calendar_logic(
            confirm=True,
            meta={},
            authenticate_fn=mock_auth,
            backend_get_fn=mock_get,
            backend_post_fn=mock_post,
            logger=mock_logger,
        )

        assert captured_get["correlation_id"] == "disconnect-corr-id"
        assert captured_post["correlation_id"] == "disconnect-corr-id"


# =============================================================================
# Tool Description Tests
# =============================================================================

class TestToolDescriptions:
    """Tests for tool descriptions."""

    def test_connect_description_mentions_connection(self):
        """Test connect tool description mentions connection status."""
        assert "connection" in CONNECT_GOOGLE_CALENDAR_DESCRIPTION.lower()

    def test_connect_description_mentions_link(self):
        """Test connect tool description mentions secure link."""
        assert "link" in CONNECT_GOOGLE_CALENDAR_DESCRIPTION.lower()

    def test_disconnect_description_mentions_confirmation(self):
        """Test disconnect tool description mentions confirmation."""
        assert "confirm" in DISCONNECT_GOOGLE_CALENDAR_DESCRIPTION.lower()

    def test_disconnect_description_mentions_revoke(self):
        """Test disconnect tool description mentions revoking access."""
        assert "revoke" in DISCONNECT_GOOGLE_CALENDAR_DESCRIPTION.lower()


# =============================================================================
# Tool Scope Mapping Tests
# =============================================================================

class TestToolScopeMappings:
    """Tests for tool scope configuration."""

    def test_connect_google_calendar_scope(self):
        """Test connect_google_calendar requires focused.write."""
        from mcp_server.focused.config import TOOL_SCOPES

        assert "connect_google_calendar" in TOOL_SCOPES
        assert TOOL_SCOPES["connect_google_calendar"] == ["focused.write"]

    def test_disconnect_google_calendar_scope(self):
        """Test disconnect_google_calendar requires focused.write."""
        from mcp_server.focused.config import TOOL_SCOPES

        assert "disconnect_google_calendar" in TOOL_SCOPES
        assert TOOL_SCOPES["disconnect_google_calendar"] == ["focused.write"]


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_connect_with_none_connected_at(
        self, mock_authenticate, mock_logger
    ):
        """Test handles None connected_at gracefully."""
        async def mock_get(path, user_id, correlation_id):
            return {"connected": True, "connected_at": None}

        result = await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=mock_get,
            backend_post_fn=AsyncMock(),
            logger=mock_logger,
        )

        data = json.loads(result)
        assert data["success"] is True
        assert data["data"]["connected_at"] is None

    def test_confirm_is_required_parameter(self):
        """Test that confirm is a required parameter (no default).

        The function signature is `confirm: bool` without a default,
        enforcing callers to explicitly pass True or False.
        This is intentional - dangerous operations should require explicit intent.
        """
        import inspect

        sig = inspect.signature(disconnect_google_calendar_logic)
        confirm_param = sig.parameters["confirm"]

        # Verify confirm has no default (is required)
        assert confirm_param.default is inspect.Parameter.empty, \
            "confirm should be a required parameter with no default"

        # Verify it's a bool type annotation
        assert confirm_param.annotation is bool


# =============================================================================
# Backend Failure / Error Handling Tests
# =============================================================================

class TestBackendErrorHandling:
    """Tests for backend failure scenarios.

    These tests verify that exceptions from backend functions bubble up
    (not swallowed), so handle_mcp_errors decorator can convert them
    to standardized error responses.
    """

    @pytest.mark.asyncio
    async def test_connect_backend_get_raises_bubbles_up(
        self, mock_authenticate, mock_logger
    ):
        """Test backend_get_fn exception bubbles up (not swallowed)."""
        async def mock_get_raises(path, user_id, correlation_id):
            raise Exception("Backend connection failed")

        with pytest.raises(Exception, match="Backend connection failed"):
            await connect_google_calendar_logic(
                meta={},
                authenticate_fn=mock_authenticate,
                backend_get_fn=mock_get_raises,
                backend_post_fn=AsyncMock(),
                logger=mock_logger,
            )

    @pytest.mark.asyncio
    async def test_connect_backend_post_raises_bubbles_up(
        self, mock_authenticate, mock_logger
    ):
        """Test backend_post_fn exception bubbles up (not swallowed)."""
        async def mock_get(path, user_id, correlation_id):
            return {"connected": False}

        async def mock_post_raises(path, payload, user_id, correlation_id):
            raise Exception("Backend POST failed")

        with pytest.raises(Exception, match="Backend POST failed"):
            await connect_google_calendar_logic(
                meta={},
                authenticate_fn=mock_authenticate,
                backend_get_fn=mock_get,
                backend_post_fn=mock_post_raises,
                logger=mock_logger,
            )

    @pytest.mark.asyncio
    async def test_disconnect_backend_get_raises_bubbles_up(
        self, mock_authenticate, mock_logger
    ):
        """Test backend_get_fn exception bubbles up in disconnect."""
        async def mock_get_raises(path, user_id, correlation_id):
            raise Exception("Backend GET failed")

        with pytest.raises(Exception, match="Backend GET failed"):
            await disconnect_google_calendar_logic(
                confirm=True,
                meta={},
                authenticate_fn=mock_authenticate,
                backend_get_fn=mock_get_raises,
                backend_post_fn=AsyncMock(),
                logger=mock_logger,
            )

    @pytest.mark.asyncio
    async def test_disconnect_backend_post_raises_bubbles_up(
        self, mock_authenticate, mock_logger
    ):
        """Test backend_post_fn exception bubbles up in disconnect."""
        async def mock_get(path, user_id, correlation_id):
            return {"connected": True}

        async def mock_post_raises(path, payload, user_id, correlation_id):
            raise Exception("Disconnect POST failed")

        with pytest.raises(Exception, match="Disconnect POST failed"):
            await disconnect_google_calendar_logic(
                confirm=True,
                meta={},
                authenticate_fn=mock_authenticate,
                backend_get_fn=mock_get,
                backend_post_fn=mock_post_raises,
                logger=mock_logger,
            )

    @pytest.mark.asyncio
    async def test_connect_httpx_timeout_bubbles_up(
        self, mock_authenticate, mock_logger
    ):
        """Test httpx timeout exception bubbles up."""
        import httpx

        async def mock_get_timeout(path, user_id, correlation_id):
            raise httpx.TimeoutException("Request timed out")

        with pytest.raises(httpx.TimeoutException):
            await connect_google_calendar_logic(
                meta={},
                authenticate_fn=mock_authenticate,
                backend_get_fn=mock_get_timeout,
                backend_post_fn=AsyncMock(),
                logger=mock_logger,
            )

    @pytest.mark.asyncio
    async def test_connect_httpx_http_error_bubbles_up(
        self, mock_authenticate, mock_logger
    ):
        """Test httpx HTTP error bubbles up."""
        import httpx

        async def mock_get_http_error(path, user_id, correlation_id):
            # Simulate 500 Internal Server Error
            raise httpx.HTTPStatusError(
                "Server error",
                request=httpx.Request("GET", "http://test"),
                response=httpx.Response(500),
            )

        with pytest.raises(httpx.HTTPStatusError):
            await connect_google_calendar_logic(
                meta={},
                authenticate_fn=mock_authenticate,
                backend_get_fn=mock_get_http_error,
                backend_post_fn=AsyncMock(),
                logger=mock_logger,
            )

    @pytest.mark.asyncio
    async def test_authenticate_raises_bubbles_up(
        self, mock_logger
    ):
        """Test authentication exception bubbles up."""
        async def mock_auth_raises(tool_name, meta):
            raise PermissionError("Invalid token")

        with pytest.raises(PermissionError, match="Invalid token"):
            await connect_google_calendar_logic(
                meta={},
                authenticate_fn=mock_auth_raises,
                backend_get_fn=AsyncMock(),
                backend_post_fn=AsyncMock(),
                logger=mock_logger,
            )


# =============================================================================
# Malformed Backend Response Tests
# =============================================================================

class TestMalformedBackendResponses:
    """Tests for handling malformed backend responses.

    These test what happens when backend returns unexpected data.
    The logic functions should either:
    1. Raise KeyError (bubble up for handle_mcp_errors decorator)
    2. Handle gracefully with safe defaults

    IMPORTANT: KeyError exceptions are safe because the @handle_mcp_errors
    decorator (in server.py) catches all exceptions and wraps them in:

        {
            "success": False,
            "error": {
                "code": "MCP_ERROR",
                "message": "An unexpected error occurred"
            }
        }

    So KeyError will NOT crash tool execution or expose raw exceptions
    to ChatGPT consumers.
    """

    @pytest.mark.asyncio
    async def test_connect_missing_connected_key_treated_as_false(
        self, mock_authenticate, mock_logger
    ):
        """Test missing 'connected' key is treated as not connected (falsy)."""
        async def mock_get(path, user_id, correlation_id):
            return {}  # Missing 'connected' key

        async def mock_post(path, payload, user_id, correlation_id):
            return {
                "token": "abc",
                "connect_url": "http://test",
                "expires_in": 600,
            }

        # Missing 'connected' → .get("connected") returns None → falsy → not connected
        result = await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=mock_get,
            backend_post_fn=mock_post,
            logger=mock_logger,
        )

        data = json.loads(result)
        assert data["data"]["status"] == "not_connected"

    @pytest.mark.asyncio
    async def test_connect_missing_connect_url_raises(
        self, mock_authenticate, mock_logger
    ):
        """Test missing 'connect_url' in initiate response raises KeyError."""
        async def mock_get(path, user_id, correlation_id):
            return {"connected": False}

        async def mock_post(path, payload, user_id, correlation_id):
            return {"token": "abc"}  # Missing connect_url and expires_in

        with pytest.raises(KeyError):
            await connect_google_calendar_logic(
                meta={},
                authenticate_fn=mock_authenticate,
                backend_get_fn=mock_get,
                backend_post_fn=mock_post,
                logger=mock_logger,
            )

    @pytest.mark.asyncio
    async def test_connect_wrong_type_connected_treated_as_truthy(
        self, mock_authenticate, mock_logger
    ):
        """Test non-bool 'connected' is treated as truthy/falsy."""
        async def mock_get(path, user_id, correlation_id):
            return {"connected": "yes", "connected_at": None}  # String instead of bool

        # "yes" is truthy, so should return connected status
        result = await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=mock_get,
            backend_post_fn=AsyncMock(),
            logger=mock_logger,
        )

        data = json.loads(result)
        assert data["success"] is True
        assert data["data"]["status"] == "connected"

    @pytest.mark.asyncio
    async def test_connect_connected_zero_treated_as_false(
        self, mock_authenticate, mock_logger
    ):
        """Test connected=0 is treated as falsy."""
        async def mock_get(path, user_id, correlation_id):
            return {"connected": 0}  # 0 instead of False

        async def mock_post(path, payload, user_id, correlation_id):
            return {
                "token": "abc",
                "connect_url": "http://test",
                "expires_in": 600,
            }

        result = await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=mock_get,
            backend_post_fn=mock_post,
            logger=mock_logger,
        )

        data = json.loads(result)
        assert data["data"]["status"] == "not_connected"

    @pytest.mark.asyncio
    async def test_connect_expires_in_none_included_in_response(
        self, mock_authenticate, mock_logger
    ):
        """Test expires_in=None is passed through (may cause issues downstream)."""
        async def mock_get(path, user_id, correlation_id):
            return {"connected": False}

        async def mock_post(path, payload, user_id, correlation_id):
            return {
                "token": "abc",
                "connect_url": "http://test",
                "expires_in": None,  # None instead of int
            }

        result = await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=mock_get,
            backend_post_fn=mock_post,
            logger=mock_logger,
        )

        data = json.loads(result)
        assert data["data"]["expires_in"] is None

    @pytest.mark.asyncio
    async def test_disconnect_missing_connected_key_treated_as_false(
        self, mock_authenticate, mock_logger
    ):
        """Test missing 'connected' key is treated as not connected."""
        async def mock_get(path, user_id, correlation_id):
            return {}  # Missing 'connected' key

        # Missing 'connected' → .get("connected") returns None → falsy → not connected
        result = await disconnect_google_calendar_logic(
            confirm=True,
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=mock_get,
            backend_post_fn=AsyncMock(),
            logger=mock_logger,
        )

        data = json.loads(result)
        assert data["data"]["status"] == "not_connected"

    # -------------------------------------------------------------------------
    # initiate-connection malformed responses
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_connect_missing_expires_in_raises(
        self, mock_authenticate, mock_logger
    ):
        """Test missing 'expires_in' in initiate response raises KeyError."""
        async def mock_get(_path, _user_id, _correlation_id):
            return {"connected": False}

        async def mock_post(_path, _payload, _user_id, _correlation_id):
            return {"token": "abc", "connect_url": "http://test"}  # Missing expires_in

        with pytest.raises(KeyError):
            await connect_google_calendar_logic(
                meta={},
                authenticate_fn=mock_authenticate,
                backend_get_fn=mock_get,
                backend_post_fn=mock_post,
                logger=mock_logger,
            )

    @pytest.mark.asyncio
    async def test_connect_expires_in_wrong_type_string_passed_through(
        self, mock_authenticate, mock_logger
    ):
        """Test expires_in as string is passed through unchanged."""
        async def mock_get(_path, _user_id, _correlation_id):
            return {"connected": False}

        async def mock_post(_path, _payload, _user_id, _correlation_id):
            return {
                "token": "abc",
                "connect_url": "http://test",
                "expires_in": "600",  # String instead of int
            }

        result = await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=mock_get,
            backend_post_fn=mock_post,
            logger=mock_logger,
        )

        data = json.loads(result)
        # String "600" passed through - downstream must handle type coercion
        assert data["data"]["expires_in"] == "600"

    @pytest.mark.asyncio
    async def test_connect_initiate_returns_empty_dict_raises(
        self, mock_authenticate, mock_logger
    ):
        """Test initiate-connection returning {} raises KeyError."""
        async def mock_get(_path, _user_id, _correlation_id):
            return {"connected": False}

        async def mock_post(_path, _payload, _user_id, _correlation_id):
            return {}  # Empty response

        with pytest.raises(KeyError):
            await connect_google_calendar_logic(
                meta={},
                authenticate_fn=mock_authenticate,
                backend_get_fn=mock_get,
                backend_post_fn=mock_post,
                logger=mock_logger,
            )

    @pytest.mark.asyncio
    async def test_connect_connect_url_empty_string_passed_through(
        self, mock_authenticate, mock_logger
    ):
        """Test connect_url as empty string is passed through."""
        async def mock_get(_path, _user_id, _correlation_id):
            return {"connected": False}

        async def mock_post(_path, _payload, _user_id, _correlation_id):
            return {
                "token": "abc",
                "connect_url": "",  # Empty string
                "expires_in": 600,
            }

        result = await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=mock_get,
            backend_post_fn=mock_post,
            logger=mock_logger,
        )

        data = json.loads(result)
        assert data["data"]["connect_url"] == ""

    @pytest.mark.asyncio
    async def test_connect_token_wrong_type_integer_passed_through(
        self, mock_authenticate, mock_logger
    ):
        """Test token as integer instead of string is passed through.

        The logic function does NOT use the token value - it only extracts
        connect_url and expires_in for the response. The token is returned
        by the backend but not included in the MCP response.

        If the backend returns a malformed token, the logic won't fail here,
        but downstream consumers may fail when they try to use it.
        """
        async def mock_get(_path, _user_id, _correlation_id):
            return {"connected": False}

        async def mock_post(_path, _payload, _user_id, _correlation_id):
            return {
                "token": 1234,  # Integer instead of string
                "connect_url": "http://test",
                "expires_in": 600,
            }

        # Should not raise - token is not used in the response
        result = await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=mock_get,
            backend_post_fn=mock_post,
            logger=mock_logger,
        )

        data = json.loads(result)
        # Logic returns connect_url and expires_in, NOT token
        assert data["success"] is True
        assert data["data"]["status"] == "not_connected"
        assert data["data"]["connect_url"] == "http://test"
        assert data["data"]["expires_in"] == 600
        # Token is not exposed in response (it's embedded in connect_url)
        assert "token" not in data["data"]

    @pytest.mark.asyncio
    async def test_connect_token_none_passed_through(
        self, mock_authenticate, mock_logger
    ):
        """Test token as None instead of string is passed through.

        Similar to integer case - token is not used by logic function.
        """
        async def mock_get(_path, _user_id, _correlation_id):
            return {"connected": False}

        async def mock_post(_path, _payload, _user_id, _correlation_id):
            return {
                "token": None,  # None instead of string
                "connect_url": "http://test",
                "expires_in": 600,
            }

        result = await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=mock_get,
            backend_post_fn=mock_post,
            logger=mock_logger,
        )

        data = json.loads(result)
        assert data["success"] is True
        assert "token" not in data["data"]

    @pytest.mark.asyncio
    async def test_connect_missing_token_key_no_crash(
        self, mock_authenticate, mock_logger
    ):
        """Test missing 'token' key in initiate response doesn't crash.

        The logic function extracts connect_url and expires_in, not token.
        Token is not a required key for the MCP response to be built.
        """
        async def mock_get(_path, _user_id, _correlation_id):
            return {"connected": False}

        async def mock_post(_path, _payload, _user_id, _correlation_id):
            return {
                # "token": missing entirely
                "connect_url": "http://test",
                "expires_in": 600,
            }

        result = await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=mock_get,
            backend_post_fn=mock_post,
            logger=mock_logger,
        )

        data = json.loads(result)
        assert data["success"] is True
        assert data["data"]["connect_url"] == "http://test"
        assert data["data"]["expires_in"] == 600

    @pytest.mark.asyncio
    async def test_connect_initiate_extra_fields_ignored(
        self, mock_authenticate, mock_logger
    ):
        """Test extra unexpected fields in initiate response are handled."""
        async def mock_get(_path, _user_id, _correlation_id):
            return {"connected": False}

        async def mock_post(_path, _payload, _user_id, _correlation_id):
            return {
                "token": "abc",
                "connect_url": "http://test",
                "expires_in": 600,
                "extra_field": "unexpected",
                "debug_info": {"request_id": "req-123"},
                "deprecated_field": None,
            }

        result = await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=mock_get,
            backend_post_fn=mock_post,
            logger=mock_logger,
        )

        data = json.loads(result)
        assert data["success"] is True
        assert data["data"]["status"] == "not_connected"
        assert data["data"]["connect_url"] == "http://test"
        assert data["data"]["expires_in"] == 600
        # Extra fields should not appear in response
        assert "extra_field" not in data["data"]
        assert "debug_info" not in data["data"]
        assert "deprecated_field" not in data["data"]

    # -------------------------------------------------------------------------
    # disconnect endpoint malformed responses
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_disconnect_response_empty_dict_no_crash(
        self, mock_authenticate, mock_logger
    ):
        """Test disconnect endpoint returning {} doesn't crash."""
        async def mock_get(_path, _user_id, _correlation_id):
            return {"connected": True}

        async def mock_post(_path, _payload, _user_id, _correlation_id):
            return {}  # Empty response from disconnect

        # Should not raise - disconnect may return empty on success
        result = await disconnect_google_calendar_logic(
            confirm=True,
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=mock_get,
            backend_post_fn=mock_post,
            logger=mock_logger,
        )

        data = json.loads(result)
        assert data["success"] is True
        assert data["data"]["status"] == "disconnected"

    @pytest.mark.asyncio
    async def test_disconnect_response_missing_status_key(
        self, mock_authenticate, mock_logger
    ):
        """Test disconnect response without 'status' key."""
        async def mock_get(_path, _user_id, _correlation_id):
            return {"connected": True}

        async def mock_post(_path, _payload, _user_id, _correlation_id):
            return {"message": "Success"}  # Has message but no status

        result = await disconnect_google_calendar_logic(
            confirm=True,
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=mock_get,
            backend_post_fn=mock_post,
            logger=mock_logger,
        )

        data = json.loads(result)
        # Should still report success (action was attempted)
        assert data["success"] is True
        assert data["data"]["status"] == "disconnected"

    @pytest.mark.asyncio
    async def test_disconnect_response_error_status(
        self, mock_authenticate, mock_logger
    ):
        """Test disconnect response with error status.

        KNOWN LIMITATION / FUTURE IMPROVEMENT:
        --------------------------------------
        Currently, the logic does NOT inspect the backend response status.
        If the disconnect endpoint returns {"status": "error"}, the MCP tool
        still reports success to the user.

        This means:
        - Token revocation can fail silently
        - User receives false success message
        - Database record is deleted even if Google token wasn't revoked

        This is dangerous but currently expected behavior. A future improvement
        should:
        1. Check backend response for error status
        2. Return success=False with appropriate error message
        3. Consider retry logic for transient failures

        See: Increment 18 design decision - "fire and forget" disconnect
        """
        async def mock_get(_path, _user_id, _correlation_id):
            return {"connected": True}

        async def mock_post(_path, _payload, _user_id, _correlation_id):
            return {"status": "error", "message": "Token revocation failed"}

        result = await disconnect_google_calendar_logic(
            confirm=True,
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=mock_get,
            backend_post_fn=mock_post,
            logger=mock_logger,
        )

        data = json.loads(result)
        # KNOWN LIMITATION: Backend errors are silently ignored
        # The logic doesn't inspect the status value from disconnect endpoint
        assert data["success"] is True
        assert data["data"]["status"] == "disconnected"

    @pytest.mark.asyncio
    async def test_disconnect_response_status_none(
        self, mock_authenticate, mock_logger
    ):
        """Test disconnect response with status=None.

        Documents: Logic does NOT validate response types.
        Even if backend returns {"status": None}, MCP returns "disconnected".
        """
        async def mock_get(_path, _user_id, _correlation_id):
            return {"connected": True}

        async def mock_post(_path, _payload, _user_id, _correlation_id):
            return {"status": None}  # None instead of string

        result = await disconnect_google_calendar_logic(
            confirm=True,
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=mock_get,
            backend_post_fn=mock_post,
            logger=mock_logger,
        )

        data = json.loads(result)
        # Logic ignores backend response entirely - always returns "disconnected"
        assert data["success"] is True
        assert data["data"]["status"] == "disconnected"

    # -------------------------------------------------------------------------
    # connection-status malformed responses
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_connect_status_connected_at_wrong_type(
        self, mock_authenticate, mock_logger
    ):
        """Test connected_at as non-string is passed through."""
        async def mock_get(_path, _user_id, _correlation_id):
            return {
                "connected": True,
                "connected_at": 1704067200,  # Unix timestamp instead of ISO string
            }

        result = await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=mock_get,
            backend_post_fn=AsyncMock(),
            logger=mock_logger,
        )

        data = json.loads(result)
        assert data["data"]["connected_at"] == 1704067200

    @pytest.mark.asyncio
    async def test_connect_status_scopes_not_included_in_response(
        self, mock_authenticate, mock_logger
    ):
        """Test scopes from backend are not included in MCP response.

        The logic function only extracts 'connected' and 'connected_at'.
        Scopes are not exposed to the MCP client.
        """
        async def mock_get(_path, _user_id, _correlation_id):
            return {
                "connected": True,
                "connected_at": "2025-01-01",
                "scopes": ["calendar.readonly"],
            }

        result = await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=mock_get,
            backend_post_fn=AsyncMock(),
            logger=mock_logger,
        )

        data = json.loads(result)
        # Scopes intentionally not included in response
        assert "scopes" not in data["data"]
        assert data["data"]["status"] == "connected"
        assert data["data"]["connected_at"] == "2025-01-01"

    @pytest.mark.asyncio
    async def test_connect_status_extra_fields_ignored(
        self, mock_authenticate, mock_logger
    ):
        """Test extra unexpected fields in status response are handled."""
        async def mock_get(_path, _user_id, _correlation_id):
            return {
                "connected": True,
                "connected_at": "2025-01-01",
                "scopes": ["calendar.readonly"],
                "extra_field": "unexpected",
                "another": {"nested": "value"},
            }

        result = await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_authenticate,
            backend_get_fn=mock_get,
            backend_post_fn=AsyncMock(),
            logger=mock_logger,
        )

        data = json.loads(result)
        assert data["success"] is True
        assert data["data"]["status"] == "connected"


# =============================================================================
# Malformed Auth Context Tests
# =============================================================================

class TestMalformedAuthContext:
    """Tests for handling malformed auth context from authenticate_fn.

    These tests document what happens when authenticate_fn returns
    incomplete or malformed auth context. This is a realistic bug scenario
    if the auth layer has issues.

    IMPORTANT: KeyError exceptions are safe because the @handle_mcp_errors
    decorator catches all exceptions and returns a standardized error.
    """

    @pytest.mark.asyncio
    async def test_connect_auth_missing_user_id_raises_keyerror(
        self, mock_logger
    ):
        """Test missing user_id in auth context raises KeyError.

        Realistic bug scenario: authenticate_fn returns correlation_id
        but forgets to include user_id.
        """
        async def mock_auth_missing_user_id(_tool_name, _meta):
            return {"correlation_id": "corr-123"}  # Missing user_id

        with pytest.raises(KeyError, match="user_id"):
            await connect_google_calendar_logic(
                meta={},
                authenticate_fn=mock_auth_missing_user_id,
                backend_get_fn=AsyncMock(),
                backend_post_fn=AsyncMock(),
                logger=mock_logger,
            )

    @pytest.mark.asyncio
    async def test_connect_auth_missing_correlation_id_raises_keyerror(
        self, mock_logger
    ):
        """Test missing correlation_id in auth context raises KeyError."""
        async def mock_auth_missing_corr(_tool_name, _meta):
            return {"user_id": "user-123"}  # Missing correlation_id

        with pytest.raises(KeyError, match="correlation_id"):
            await connect_google_calendar_logic(
                meta={},
                authenticate_fn=mock_auth_missing_corr,
                backend_get_fn=AsyncMock(),
                backend_post_fn=AsyncMock(),
                logger=mock_logger,
            )

    @pytest.mark.asyncio
    async def test_connect_auth_returns_empty_dict_raises_keyerror(
        self, mock_logger
    ):
        """Test empty auth context raises KeyError."""
        async def mock_auth_empty(_tool_name, _meta):
            return {}

        with pytest.raises(KeyError):
            await connect_google_calendar_logic(
                meta={},
                authenticate_fn=mock_auth_empty,
                backend_get_fn=AsyncMock(),
                backend_post_fn=AsyncMock(),
                logger=mock_logger,
            )

    @pytest.mark.asyncio
    async def test_disconnect_auth_missing_user_id_raises_keyerror(
        self, mock_logger
    ):
        """Test missing user_id in auth context raises KeyError for disconnect."""
        async def mock_auth_missing_user_id(_tool_name, _meta):
            return {"correlation_id": "corr-123"}

        with pytest.raises(KeyError, match="user_id"):
            await disconnect_google_calendar_logic(
                confirm=True,
                meta={},
                authenticate_fn=mock_auth_missing_user_id,
                backend_get_fn=AsyncMock(),
                backend_post_fn=AsyncMock(),
                logger=mock_logger,
            )

    @pytest.mark.asyncio
    async def test_connect_auth_user_id_none_propagates(
        self, mock_logger
    ):
        """Test user_id=None is passed through (may cause downstream issues).

        The logic doesn't validate that user_id is a non-None string.
        None will be passed to backend functions.
        """
        async def mock_auth_none_user_id(_tool_name, _meta):
            return {"user_id": None, "correlation_id": "corr-123"}

        received_user_id = None

        async def mock_get(_path, user_id, _correlation_id):
            nonlocal received_user_id
            received_user_id = user_id
            return {"connected": True, "connected_at": "2025-01-01"}

        await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_auth_none_user_id,
            backend_get_fn=mock_get,
            backend_post_fn=AsyncMock(),
            logger=mock_logger,
        )

        # None is passed through - no validation
        assert received_user_id is None

    @pytest.mark.asyncio
    async def test_connect_auth_user_id_wrong_type_propagates(
        self, mock_logger
    ):
        """Test user_id with wrong type (int) is passed through."""
        async def mock_auth_int_user_id(_tool_name, _meta):
            return {"user_id": 12345, "correlation_id": "corr-123"}

        received_user_id = None

        async def mock_get(_path, user_id, _correlation_id):
            nonlocal received_user_id
            received_user_id = user_id
            return {"connected": True, "connected_at": "2025-01-01"}

        await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_auth_int_user_id,
            backend_get_fn=mock_get,
            backend_post_fn=AsyncMock(),
            logger=mock_logger,
        )

        # Integer is passed through - no type validation
        assert received_user_id == 12345


# =============================================================================
# Meta Propagation Tests
# =============================================================================

class TestMetaPropagation:
    """Tests for meta parameter propagation to authenticate_fn.

    Ensures meta dict from tool call is passed unchanged to authenticate_fn.
    Important for OpenAI security metadata and request context.
    """

    @pytest.mark.asyncio
    async def test_connect_passes_meta_to_authenticate_fn(self, mock_logger):
        """Test connect_google_calendar passes meta unchanged to authenticate_fn."""
        received_meta = None

        async def mock_auth(_tool_name, meta):
            nonlocal received_meta
            received_meta = meta
            return {"user_id": "user-123", "correlation_id": "corr-456"}

        async def mock_get(_path, _user_id, _correlation_id):
            return {"connected": True, "connected_at": None}

        input_meta = {
            "openai_conversation_id": "conv-abc-123",
            "request_id": "req-xyz-789",
            "custom_field": {"nested": "value"},
        }

        await connect_google_calendar_logic(
            meta=input_meta,
            authenticate_fn=mock_auth,
            backend_get_fn=mock_get,
            backend_post_fn=AsyncMock(),
            logger=mock_logger,
        )

        assert received_meta is input_meta  # Same object reference
        assert received_meta == input_meta  # Same content

    @pytest.mark.asyncio
    async def test_connect_passes_empty_meta(self, mock_logger):
        """Test connect_google_calendar passes empty meta dict unchanged."""
        received_meta = None

        async def mock_auth(_tool_name, meta):
            nonlocal received_meta
            received_meta = meta
            return {"user_id": "user-123", "correlation_id": "corr-456"}

        async def mock_get(_path, _user_id, _correlation_id):
            return {"connected": True, "connected_at": None}

        await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_auth,
            backend_get_fn=mock_get,
            backend_post_fn=AsyncMock(),
            logger=mock_logger,
        )

        assert received_meta == {}

    @pytest.mark.asyncio
    async def test_disconnect_passes_meta_to_authenticate_fn(self, mock_logger):
        """Test disconnect_google_calendar passes meta unchanged to authenticate_fn."""
        received_meta = None

        async def mock_auth(_tool_name, meta):
            nonlocal received_meta
            received_meta = meta
            return {"user_id": "user-123", "correlation_id": "corr-456"}

        input_meta = {
            "openai_ephemeral_user_id": "ephemeral-user-abc",
            "ip_address": "192.168.1.1",
        }

        await disconnect_google_calendar_logic(
            confirm=False,  # Will return early but still calls authenticate
            meta=input_meta,
            authenticate_fn=mock_auth,
            backend_get_fn=AsyncMock(),
            backend_post_fn=AsyncMock(),
            logger=mock_logger,
        )

        assert received_meta is input_meta
        assert received_meta == input_meta

    @pytest.mark.asyncio
    async def test_connect_passes_tool_name_to_authenticate_fn(self, mock_logger):
        """Test connect_google_calendar passes correct tool_name to authenticate_fn."""
        received_tool_name = None

        async def mock_auth(tool_name, _meta):
            nonlocal received_tool_name
            received_tool_name = tool_name
            return {"user_id": "user-123", "correlation_id": "corr-456"}

        async def mock_get(_path, _user_id, _correlation_id):
            return {"connected": True, "connected_at": None}

        await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_auth,
            backend_get_fn=mock_get,
            backend_post_fn=AsyncMock(),
            logger=mock_logger,
        )

        assert received_tool_name == "connect_google_calendar"

    @pytest.mark.asyncio
    async def test_disconnect_passes_tool_name_to_authenticate_fn(self, mock_logger):
        """Test disconnect_google_calendar passes correct tool_name to authenticate_fn."""
        received_tool_name = None

        async def mock_auth(tool_name, _meta):
            nonlocal received_tool_name
            received_tool_name = tool_name
            return {"user_id": "user-123", "correlation_id": "corr-456"}

        await disconnect_google_calendar_logic(
            confirm=False,
            meta={},
            authenticate_fn=mock_auth,
            backend_get_fn=AsyncMock(),
            backend_post_fn=AsyncMock(),
            logger=mock_logger,
        )

        assert received_tool_name == "disconnect_google_calendar"

    @pytest.mark.asyncio
    async def test_meta_not_modified_by_logic(self, mock_logger):
        """Test that logic functions don't modify the meta dict."""
        async def mock_auth(_tool_name, _meta):
            return {"user_id": "user-123", "correlation_id": "corr-456"}

        async def mock_get(_path, _user_id, _correlation_id):
            return {"connected": True, "connected_at": None}

        input_meta = {"key": "value", "nested": {"a": 1}}
        original_meta = {"key": "value", "nested": {"a": 1}}  # Copy for comparison

        await connect_google_calendar_logic(
            meta=input_meta,
            authenticate_fn=mock_auth,
            backend_get_fn=mock_get,
            backend_post_fn=AsyncMock(),
            logger=mock_logger,
        )

        assert input_meta == original_meta  # Not modified


# =============================================================================
# Scope Enforcement Tests
# =============================================================================

class TestScopeEnforcement:
    """Tests documenting scope enforcement behavior.

    The logic functions do NOT enforce scopes themselves.
    Scope enforcement happens in the auth layer (authenticate_fn).

    These tests document what happens when:
    - Auth returns no scopes
    - Auth returns wrong scopes
    - Auth returns read-only scopes

    Current behavior: Logic functions ignore scopes entirely.
    They trust that authenticate_fn has already enforced access.
    """

    @pytest.mark.asyncio
    async def test_connect_proceeds_without_scopes_in_auth_context(
        self, mock_logger
    ):
        """Test connect proceeds even if auth context has no scopes.

        Documents: Logic function does NOT check scopes.
        Scope enforcement is the responsibility of authenticate_fn.
        """
        async def mock_auth_no_scopes(_tool_name, _meta):
            return {
                "user_id": "user-123",
                "correlation_id": "corr-456",
                # No "scopes" key at all
            }

        async def mock_get(_path, _user_id, _correlation_id):
            return {"connected": True, "connected_at": "2025-01-01"}

        # Should NOT raise - logic doesn't check scopes
        result = await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_auth_no_scopes,
            backend_get_fn=mock_get,
            backend_post_fn=AsyncMock(),
            logger=mock_logger,
        )

        data = json.loads(result)
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_connect_proceeds_with_empty_scopes(
        self, mock_logger
    ):
        """Test connect proceeds even with empty scopes set."""
        async def mock_auth_empty_scopes(_tool_name, _meta):
            return {
                "user_id": "user-123",
                "correlation_id": "corr-456",
                "scopes": set(),  # Empty scopes
            }

        async def mock_get(_path, _user_id, _correlation_id):
            return {"connected": True, "connected_at": "2025-01-01"}

        result = await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_auth_empty_scopes,
            backend_get_fn=mock_get,
            backend_post_fn=AsyncMock(),
            logger=mock_logger,
        )

        data = json.loads(result)
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_connect_proceeds_with_read_only_scope(
        self, mock_logger
    ):
        """Test connect proceeds even with only read scope (no write).

        Documents: Logic does NOT enforce focused.write requirement.
        The TOOL_SCOPES config is used by a higher layer.
        """
        async def mock_auth_read_only(_tool_name, _meta):
            return {
                "user_id": "user-123",
                "correlation_id": "corr-456",
                "scopes": {"focused.read"},  # Only read, no write
            }

        async def mock_get(_path, _user_id, _correlation_id):
            return {"connected": True, "connected_at": "2025-01-01"}

        result = await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_auth_read_only,
            backend_get_fn=mock_get,
            backend_post_fn=AsyncMock(),
            logger=mock_logger,
        )

        data = json.loads(result)
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_disconnect_proceeds_with_wrong_scopes(
        self, mock_logger
    ):
        """Test disconnect proceeds with unrelated scopes."""
        async def mock_auth_wrong_scopes(_tool_name, _meta):
            return {
                "user_id": "user-123",
                "correlation_id": "corr-456",
                "scopes": {"calendar.read", "email.write"},  # Wrong scopes entirely
            }

        # confirm=False returns early, but still calls authenticate
        result = await disconnect_google_calendar_logic(
            confirm=False,
            meta={},
            authenticate_fn=mock_auth_wrong_scopes,
            backend_get_fn=AsyncMock(),
            backend_post_fn=AsyncMock(),
            logger=mock_logger,
        )

        data = json.loads(result)
        # Returned confirmation error, not scope error
        assert data["success"] is False
        assert data["error"]["code"] == "CONFIRMATION_REQUIRED"

    @pytest.mark.asyncio
    async def test_scope_enforcement_happens_in_authenticate_fn(
        self, mock_logger
    ):
        """Test that scope errors should be raised by authenticate_fn.

        If authenticate_fn raises PermissionError for scope issues,
        it bubbles up (same as test_authenticate_raises_bubbles_up).
        """
        async def mock_auth_raises_scope_error(_tool_name, _meta):
            raise PermissionError("Insufficient scope: requires focused.write")

        with pytest.raises(PermissionError, match="Insufficient scope"):
            await connect_google_calendar_logic(
                meta={},
                authenticate_fn=mock_auth_raises_scope_error,
                backend_get_fn=AsyncMock(),
                backend_post_fn=AsyncMock(),
                logger=mock_logger,
            )

    @pytest.mark.asyncio
    async def test_tool_scopes_config_not_used_by_logic(
        self, mock_logger
    ):
        """Document that TOOL_SCOPES config is not used inside logic functions.

        TOOL_SCOPES is declarative config for external enforcement.
        The logic functions themselves don't import or check it.
        """
        from mcp_server.focused.config import TOOL_SCOPES

        # Verify the config exists and specifies write scope
        assert TOOL_SCOPES["connect_google_calendar"] == ["focused.write"]
        assert TOOL_SCOPES["disconnect_google_calendar"] == ["focused.write"]

        # But logic function works without any scopes
        async def mock_auth_no_scopes(_tool_name, _meta):
            return {"user_id": "user-123", "correlation_id": "corr-456"}

        async def mock_get(_path, _user_id, _correlation_id):
            return {"connected": True, "connected_at": None}

        # Still works - config is for external enforcement only
        result = await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_auth_no_scopes,
            backend_get_fn=mock_get,
            backend_post_fn=AsyncMock(),
            logger=mock_logger,
        )

        data = json.loads(result)
        assert data["success"] is True


# =============================================================================
# Logger Semantics Tests
# =============================================================================

class TestLoggerSemantics:
    """Tests for structured logging behavior.

    Verifies that:
    - Correct events are logged at each step
    - correlation_id and user_id are included in all log calls
    - Appropriate log levels are used (info for normal flow)

    WARNING: Log Taxonomy is Frozen by These Tests
    -----------------------------------------------
    These tests enforce exact event names:
    - tool.connect_google_calendar.start
    - tool.connect_google_calendar.already_connected
    - tool.connect_google_calendar.url_generated
    - tool.disconnect_google_calendar.start
    - tool.disconnect_google_calendar.confirmation_required
    - tool.disconnect_google_calendar.not_connected
    - tool.disconnect_google_calendar.success

    Renaming these events will break tests. This is intentional:
    - Log events are part of the observability contract
    - Dashboards, alerts, and log queries depend on stable event names
    - Changes should be deliberate and coordinated with ops tooling

    If you need to rename events, update both implementation and tests together.
    """

    @pytest.fixture
    def tracking_logger(self):
        """Create a logger that tracks all calls with their arguments."""
        logger = MagicMock()
        logger.info_calls = []
        logger.warning_calls = []
        logger.error_calls = []

        def track_info(event, **kwargs):
            logger.info_calls.append({"event": event, **kwargs})

        def track_warning(event, **kwargs):
            logger.warning_calls.append({"event": event, **kwargs})

        def track_error(event, **kwargs):
            logger.error_calls.append({"event": event, **kwargs})

        logger.info = MagicMock(side_effect=track_info)
        logger.warning = MagicMock(side_effect=track_warning)
        logger.error = MagicMock(side_effect=track_error)

        return logger

    # -------------------------------------------------------------------------
    # connect_google_calendar logging
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_connect_already_connected_logs_start_and_already_connected(
        self, tracking_logger
    ):
        """Test connect logs start event and already_connected event."""
        async def mock_auth(_tool_name, _meta):
            return {"user_id": "user-abc", "correlation_id": "corr-xyz"}

        async def mock_get(_path, _user_id, _correlation_id):
            return {"connected": True, "connected_at": "2025-01-01"}

        await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_auth,
            backend_get_fn=mock_get,
            backend_post_fn=AsyncMock(),
            logger=tracking_logger,
        )

        # Should have exactly 2 info calls
        assert len(tracking_logger.info_calls) == 2

        # First call: start event
        start_call = tracking_logger.info_calls[0]
        assert start_call["event"] == "tool.connect_google_calendar.start"
        assert start_call["correlation_id"] == "corr-xyz"
        assert start_call["user_id"] == "user-abc"

        # Second call: already_connected event
        connected_call = tracking_logger.info_calls[1]
        assert connected_call["event"] == "tool.connect_google_calendar.already_connected"
        assert connected_call["correlation_id"] == "corr-xyz"
        assert connected_call["user_id"] == "user-abc"

    @pytest.mark.asyncio
    async def test_connect_not_connected_logs_start_and_url_generated(
        self, tracking_logger
    ):
        """Test connect logs start event and url_generated event."""
        async def mock_auth(_tool_name, _meta):
            return {"user_id": "user-123", "correlation_id": "corr-456"}

        async def mock_get(_path, _user_id, _correlation_id):
            return {"connected": False}

        async def mock_post(_path, _payload, _user_id, _correlation_id):
            return {"token": "t", "connect_url": "http://test", "expires_in": 600}

        await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_auth,
            backend_get_fn=mock_get,
            backend_post_fn=mock_post,
            logger=tracking_logger,
        )

        # Should have exactly 2 info calls
        assert len(tracking_logger.info_calls) == 2

        # First call: start event
        assert tracking_logger.info_calls[0]["event"] == "tool.connect_google_calendar.start"

        # Second call: url_generated event
        url_call = tracking_logger.info_calls[1]
        assert url_call["event"] == "tool.connect_google_calendar.url_generated"
        assert url_call["correlation_id"] == "corr-456"
        assert url_call["user_id"] == "user-123"

    # -------------------------------------------------------------------------
    # disconnect_google_calendar logging
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_disconnect_without_confirm_logs_start_and_confirmation_required(
        self, tracking_logger
    ):
        """Test disconnect without confirm logs appropriate events."""
        async def mock_auth(_tool_name, _meta):
            return {"user_id": "user-abc", "correlation_id": "corr-xyz"}

        await disconnect_google_calendar_logic(
            confirm=False,
            meta={},
            authenticate_fn=mock_auth,
            backend_get_fn=AsyncMock(),
            backend_post_fn=AsyncMock(),
            logger=tracking_logger,
        )

        # Should have exactly 2 info calls (start + confirmation_required)
        assert len(tracking_logger.info_calls) == 2

        # First call: start event with confirm=False
        start_call = tracking_logger.info_calls[0]
        assert start_call["event"] == "tool.disconnect_google_calendar.start"
        assert start_call["confirm"] is False
        assert start_call["correlation_id"] == "corr-xyz"

        # Second call: confirmation_required event
        confirm_call = tracking_logger.info_calls[1]
        assert confirm_call["event"] == "tool.disconnect_google_calendar.confirmation_required"
        assert confirm_call["correlation_id"] == "corr-xyz"

    @pytest.mark.asyncio
    async def test_disconnect_not_connected_logs_not_connected_event(
        self, tracking_logger
    ):
        """Test disconnect when not connected logs not_connected event."""
        async def mock_auth(_tool_name, _meta):
            return {"user_id": "user-123", "correlation_id": "corr-456"}

        async def mock_get(_path, _user_id, _correlation_id):
            return {"connected": False}

        await disconnect_google_calendar_logic(
            confirm=True,
            meta={},
            authenticate_fn=mock_auth,
            backend_get_fn=mock_get,
            backend_post_fn=AsyncMock(),
            logger=tracking_logger,
        )

        # Should have exactly 2 info calls (start + not_connected)
        assert len(tracking_logger.info_calls) == 2

        # Second call: not_connected event
        not_connected_call = tracking_logger.info_calls[1]
        assert not_connected_call["event"] == "tool.disconnect_google_calendar.not_connected"
        assert not_connected_call["user_id"] == "user-123"

    @pytest.mark.asyncio
    async def test_disconnect_success_logs_success_event(
        self, tracking_logger
    ):
        """Test successful disconnect logs success event."""
        async def mock_auth(_tool_name, _meta):
            return {"user_id": "user-abc", "correlation_id": "corr-xyz"}

        async def mock_get(_path, _user_id, _correlation_id):
            return {"connected": True}

        async def mock_post(_path, _payload, _user_id, _correlation_id):
            return {"status": "disconnected"}

        await disconnect_google_calendar_logic(
            confirm=True,
            meta={},
            authenticate_fn=mock_auth,
            backend_get_fn=mock_get,
            backend_post_fn=mock_post,
            logger=tracking_logger,
        )

        # Should have exactly 2 info calls (start + success)
        assert len(tracking_logger.info_calls) == 2

        # Second call: success event
        success_call = tracking_logger.info_calls[1]
        assert success_call["event"] == "tool.disconnect_google_calendar.success"
        assert success_call["correlation_id"] == "corr-xyz"
        assert success_call["user_id"] == "user-abc"

    # -------------------------------------------------------------------------
    # Correlation ID consistency
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_all_log_calls_include_correlation_id(
        self, tracking_logger
    ):
        """Test that every log call includes correlation_id."""
        async def mock_auth(_tool_name, _meta):
            return {"user_id": "u", "correlation_id": "trace-id-12345"}

        async def mock_get(_path, _user_id, _correlation_id):
            return {"connected": True}

        await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_auth,
            backend_get_fn=mock_get,
            backend_post_fn=AsyncMock(),
            logger=tracking_logger,
        )

        for call in tracking_logger.info_calls:
            assert "correlation_id" in call, f"Missing correlation_id in {call}"
            assert call["correlation_id"] == "trace-id-12345"

    @pytest.mark.asyncio
    async def test_all_log_calls_include_user_id(
        self, tracking_logger
    ):
        """Test that every log call includes user_id."""
        async def mock_auth(_tool_name, _meta):
            return {"user_id": "user-id-67890", "correlation_id": "c"}

        async def mock_get(_path, _user_id, _correlation_id):
            return {"connected": False}

        async def mock_post(_path, _payload, _user_id, _correlation_id):
            return {"token": "t", "connect_url": "url", "expires_in": 600}

        await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_auth,
            backend_get_fn=mock_get,
            backend_post_fn=mock_post,
            logger=tracking_logger,
        )

        for call in tracking_logger.info_calls:
            assert "user_id" in call, f"Missing user_id in {call}"
            assert call["user_id"] == "user-id-67890"

    # -------------------------------------------------------------------------
    # No warning/error logs in normal flow
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_connect_success_no_warning_or_error_logs(
        self, tracking_logger
    ):
        """Test that successful connect doesn't log warnings or errors."""
        async def mock_auth(_tool_name, _meta):
            return {"user_id": "u", "correlation_id": "c"}

        async def mock_get(_path, _user_id, _correlation_id):
            return {"connected": True, "connected_at": None}

        await connect_google_calendar_logic(
            meta={},
            authenticate_fn=mock_auth,
            backend_get_fn=mock_get,
            backend_post_fn=AsyncMock(),
            logger=tracking_logger,
        )

        assert len(tracking_logger.warning_calls) == 0
        assert len(tracking_logger.error_calls) == 0

    @pytest.mark.asyncio
    async def test_disconnect_success_no_warning_or_error_logs(
        self, tracking_logger
    ):
        """Test that successful disconnect doesn't log warnings or errors."""
        async def mock_auth(_tool_name, _meta):
            return {"user_id": "u", "correlation_id": "c"}

        async def mock_get(_path, _user_id, _correlation_id):
            return {"connected": True}

        async def mock_post(_path, _payload, _user_id, _correlation_id):
            return {}

        await disconnect_google_calendar_logic(
            confirm=True,
            meta={},
            authenticate_fn=mock_auth,
            backend_get_fn=mock_get,
            backend_post_fn=mock_post,
            logger=tracking_logger,
        )

        assert len(tracking_logger.warning_calls) == 0
        assert len(tracking_logger.error_calls) == 0