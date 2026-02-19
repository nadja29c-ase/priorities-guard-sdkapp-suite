"""
Integration tests for Priority Guardian auth header flow.

Tests the full flow from middleware to mcp_auth:
- Middleware captures Authorization header from HTTP scope
- auth_header_var is set correctly
- mcp_auth.authenticate_request reads from ContextVar
- Auth failure when no Authorization header present
"""

import pytest
from unittest.mock import AsyncMock, patch


class TestMiddlewareAuthCapture:
    """Tests for middleware Authorization header capture."""

    @pytest.mark.asyncio
    async def test_middleware_captures_auth_header(self):
        """Middleware sets auth_header_var from HTTP scope."""
        from mcp_server.priority_guardian.server import MCPContentTypeAndAcceptFixMiddleware
        from mcp_server.priority_guardian.request_context import auth_header_var

        # Reset ContextVar
        auth_header_var.set(None)

        # Create mock inner app that checks the ContextVar
        captured_value = None

        async def mock_app(scope, receive, send):
            nonlocal captured_value
            captured_value = auth_header_var.get()

        middleware = MCPContentTypeAndAcceptFixMiddleware(mock_app, auth_header_var)

        # Simulate HTTP POST to /mcp with Authorization header
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/mcp",
            "headers": [
                (b"authorization", b"Bearer test-token-xyz"),
                (b"content-type", b"application/json"),
            ],
        }

        await middleware(scope, AsyncMock(), AsyncMock())

        assert captured_value == "Bearer test-token-xyz"

    @pytest.mark.asyncio
    async def test_middleware_does_not_set_when_no_auth_header(self):
        """Middleware doesn't set auth_header_var when no Authorization header."""
        from mcp_server.priority_guardian.server import MCPContentTypeAndAcceptFixMiddleware
        from mcp_server.priority_guardian.request_context import auth_header_var

        # Reset ContextVar
        auth_header_var.set(None)

        captured_value = "sentinel"

        async def mock_app(scope, receive, send):
            nonlocal captured_value
            captured_value = auth_header_var.get()

        middleware = MCPContentTypeAndAcceptFixMiddleware(mock_app, auth_header_var)

        # Simulate HTTP POST to /mcp WITHOUT Authorization header
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/mcp",
            "headers": [
                (b"content-type", b"application/json"),
            ],
        }

        await middleware(scope, AsyncMock(), AsyncMock())

        # Should remain None (not set)
        assert captured_value is None


class TestMcpAuthReadsFromContextVar:
    """Tests that mcp_auth reads from ContextVar."""

    @pytest.mark.asyncio
    async def test_authenticate_request_reads_from_contextvar(self):
        """authenticate_request reads auth header from auth_header_var."""
        from mcp_server.priority_guardian.request_context import auth_header_var
        from mcp_server.priority_guardian.mcp_auth import authenticate_request

        # Set a valid-looking auth header in ContextVar
        auth_header_var.set("Bearer mock-jwt-token")

        # Mock JWT validation to succeed
        mock_validated = {
            "user_id": "user-123",
            "scopes": {"pg.access"},
            "jti": "token-id",
            "azp": "client-id",
        }

        with patch(
            "mcp_server.priority_guardian.mcp_auth.validate_jwt",
            new_callable=AsyncMock,
            return_value=mock_validated,
        ) as mock_validate, patch(
            "mcp_server.priority_guardian.mcp_auth.enforce_tool_scope",
        ) as mock_enforce:
            result = await authenticate_request("create_priority", {})

        assert result["user_id"] == "user-123"
        mock_validate.assert_called_once()
        mock_enforce.assert_called_once()

        # Clean up
        auth_header_var.set(None)

    @pytest.mark.asyncio
    async def test_authenticate_fails_when_insufficient_scopes(self):
        """authenticate_request raises InsufficientScopeError when scopes are insufficient."""
        from mcp_server.priority_guardian.request_context import auth_header_var
        from mcp_server.priority_guardian.mcp_auth import (
            authenticate_request,
            InsufficientScopeError,
        )

        # Set a valid-looking auth header in ContextVar
        auth_header_var.set("Bearer mock-jwt-token")

        # Mock JWT validation to succeed but with insufficient scopes
        mock_validated = {
            "user_id": "user-123",
            "scopes": {"some.other.scope"},  # Missing pg.access
            "jti": "token-id",
            "azp": "client-id",
        }

        with patch(
            "mcp_server.priority_guardian.mcp_auth.validate_jwt",
            new_callable=AsyncMock,
            return_value=mock_validated,
        ):
            with pytest.raises(InsufficientScopeError) as exc_info:
                await authenticate_request("create_priority", {})

        assert "scope" in str(exc_info.value).lower()

        # Clean up
        auth_header_var.set(None)

    @pytest.mark.asyncio
    async def test_authenticate_fails_when_no_auth_header(self):
        """authenticate_request raises UnauthorizedError when no auth header."""
        from mcp_server.priority_guardian.request_context import auth_header_var
        from mcp_server.priority_guardian.mcp_auth import (
            authenticate_request,
            UnauthorizedError,
        )

        # Ensure no auth header in ContextVar
        auth_header_var.set(None)

        with pytest.raises(UnauthorizedError) as exc_info:
            await authenticate_request("create_priority", {})

        assert "Missing Authorization header" in str(exc_info.value)


class TestEndToEndAuthFlow:
    """End-to-end tests for auth flow through dispatcher."""

    @pytest.mark.asyncio
    async def test_dispatcher_uses_auth_from_contextvar(self):
        """Dispatcher gets user_id from authenticate_request which reads ContextVar."""
        from mcp_server.priority_guardian.handlers.tools import call_tool_request
        from mcp_server.priority_guardian.request_context import auth_header_var
        from mcp import types as mcp_types

        # Set auth header in ContextVar (simulating middleware)
        auth_header_var.set("Bearer valid-token")

        request = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name="create_priority",
                arguments={
                    "user_priority_name_verbatim": "I need to finish the test",
                    "name": "Test",
                    "user_priority_type_verbatim": "it has a hard deadline",
                    "type": "deadline",
                    "deadline": "2026-12-31",
                },
            ),
        )

        # Mock validate_jwt to succeed
        mock_validated = {
            "user_id": "user-from-jwt",
            "scopes": {"pg.access"},
            "jti": "token-id",
            "azp": "client-id",
        }

        mock_backend_response = {
            "success": True,
            "data": {
                "priority": {
                    "id": "p-123",
                    "name": "Test",
                    "type": "deadline",
                    "calendar_keyword": "P1",
                    "status": "active",
                    "deadline": "2026-12-31",
                    "weekly_hour_target": None,
                    "checkpoint_date": None,
                    "deliverables": [],
                    "goals": [],
                    "created_at": "2026-02-09T00:00:00Z",
                },
                "active_priority_count": 1,
                "available_keywords": ["P2", "P3"],
            },
        }

        mock_get_response = {
            "success": True,
            "data": {
                "priorities": [
                    {
                        "id": "p-123",
                        "name": "Test",
                        "type": "deadline",
                        "calendar_keyword": "P1",
                        "status": "active",
                        "deadline": "2026-12-31",
                        "deliverables": [],
                        "goals": [],
                        "created_at": "2026-02-09T00:00:00Z",
                        "updated_at": "2026-02-09T00:00:00Z",
                    },
                ],
                "google_connection": {"connected": False},
                "available_keywords": ["P2", "P3"],
            },
        }

        with patch(
            "mcp_server.priority_guardian.mcp_auth.validate_jwt",
            new_callable=AsyncMock,
            return_value=mock_validated,
        ), patch(
            "mcp_server.priority_guardian.tools.create_priority.backend_post",
            new_callable=AsyncMock,
            return_value=mock_backend_response,
        ), patch(
            "mcp_server.priority_guardian.tools.create_priority.backend_get",
            new_callable=AsyncMock,
            return_value=mock_get_response,
        ):
            result = await call_tool_request(request)

        # Should succeed (not auth error)
        assert not result.isError
        assert "P1" in result.content[0].text

        # Clean up
        auth_header_var.set(None)
