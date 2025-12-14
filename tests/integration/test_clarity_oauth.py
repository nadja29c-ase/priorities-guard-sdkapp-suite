"""
Clarity OAuth integration tests.

Tests end-to-end OAuth flow including discovery endpoints and auth enforcement.
These tests use the Clarity MCP server directly without external dependencies.
"""

import json
import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport
from mcp import types as mcp_types

from mcp_server.clarity.server import create_app, _call_tool_request
from mcp_server.clarity.config import MCP_SERVER_URL, OAUTH_ISSUER_URL, SCOPES_SUPPORTED


@pytest_asyncio.fixture
async def clarity_client():
    """Create async test client for Clarity MCP server."""
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        yield client


class TestClarityDiscoveryEndpoints:
    """Test OAuth discovery endpoints on Clarity MCP server."""

    @pytest.mark.asyncio
    async def test_oauth_protected_resource(self, clarity_client: AsyncClient):
        """GET /.well-known/oauth-protected-resource returns clarity scopes."""
        response = await clarity_client.get("/.well-known/oauth-protected-resource")

        assert response.status_code == 200
        data = response.json()

        # Explicit value assertions to prevent regression
        assert data["scopes_supported"] == SCOPES_SUPPORTED
        assert data["authorization_servers"] == [OAUTH_ISSUER_URL]
        assert data["resource"] == MCP_SERVER_URL

        # Sanity check: must use /oauth/pg, not /oauth/focused
        assert "/oauth/pg" in OAUTH_ISSUER_URL or "localhost" in OAUTH_ISSUER_URL

    @pytest.mark.asyncio
    async def test_oauth_protected_resource_mcp_suffix(self, clarity_client: AsyncClient):
        """GET /.well-known/oauth-protected-resource/mcp also works."""
        response = await clarity_client.get("/.well-known/oauth-protected-resource/mcp")

        assert response.status_code == 200
        data = response.json()

        # Same values as main endpoint
        assert data["scopes_supported"] == SCOPES_SUPPORTED
        assert data["authorization_servers"] == [OAUTH_ISSUER_URL]

    @pytest.mark.asyncio
    async def test_oauth_protected_resource_head(self, clarity_client: AsyncClient):
        """HEAD /.well-known/oauth-protected-resource works."""
        response = await clarity_client.head("/.well-known/oauth-protected-resource")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_oauth_protected_resource_options(self, clarity_client: AsyncClient):
        """OPTIONS /.well-known/oauth-protected-resource works."""
        response = await clarity_client.options("/.well-known/oauth-protected-resource")
        assert response.status_code == 200


class TestClarityAuthEnforcement:
    """Test OAuth auth enforcement on tool calls.

    These tests call the tool handler directly to avoid FastMCP session management complexity.
    """

    def _make_call_tool_request(self, tool_name: str, arguments: dict, meta: dict = None):
        """Build a CallToolRequest for testing."""
        params = MagicMock()
        params.name = tool_name
        params.arguments = arguments
        params._meta = meta

        request = MagicMock(spec=mcp_types.CallToolRequest)
        request.params = params
        return request

    @pytest.mark.asyncio
    async def test_tool_without_auth_returns_32001(self):
        """Tool call without auth returns error code -32001 (Unauthorized)."""
        # Call tool without Authorization header (no _meta)
        req = self._make_call_tool_request(
            "cluster_raw_thoughts",
            {
                "thoughts_exhausted": True,
                "clusters": [{"cluster_name": "Test", "thought_items": ["item1"]}]
            },
            meta=None  # No auth headers
        )

        result = await _call_tool_request(req)

        # Should return error with isError=True
        assert result.isError is True

        # Parse error content - should contain -32001
        assert len(result.content) > 0
        error_text = result.content[0].text
        error_data = json.loads(error_text)
        assert error_data["error"]["code"] == -32001
        assert "mcp/www_authenticate" in str(error_data)

    @pytest.mark.asyncio
    async def test_tool_with_wrong_scope_returns_32003(self):
        """Tool call with wrong scope returns error code -32003 (Forbidden)."""
        # Mock validate_jwt to return focused.write instead of clarity.write
        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.return_value = {
                "user_id": "user-123",
                "scopes": {"focused.write"},  # Wrong scope - should be clarity.write
                "jti": "token-id",
                "azp": "client-id"
            }

            req = self._make_call_tool_request(
                "cluster_raw_thoughts",
                {
                    "thoughts_exhausted": True,
                    "clusters": [{"cluster_name": "Test", "thought_items": ["item1"]}]
                },
                meta={"headers": {"authorization": "Bearer valid-token-wrong-scope"}}
            )

            result = await _call_tool_request(req)

        # Should return error with isError=True
        assert result.isError is True

        # Parse error content - should contain -32003
        assert len(result.content) > 0
        error_text = result.content[0].text
        error_data = json.loads(error_text)
        assert error_data["error"]["code"] == -32003
        assert "mcp/www_authenticate" in str(error_data)

    @pytest.mark.asyncio
    async def test_tool_with_valid_auth_succeeds(self):
        """Tool call with valid auth and correct scope succeeds."""
        # Mock validate_jwt to return valid token with clarity.write scope
        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.return_value = {
                "user_id": "user-123",
                "scopes": {"clarity.write"},  # Correct scope
                "jti": "token-id",
                "azp": "client-id"
            }

            req = self._make_call_tool_request(
                "cluster_raw_thoughts",
                {
                    "thoughts_exhausted": True,
                    "clusters": [{"cluster_name": "Test", "thought_items": ["item1"]}]
                },
                meta={"headers": {"authorization": "Bearer valid-token"}}
            )

            result = await _call_tool_request(req)

        # Should return success (no isError or isError=False)
        assert result.isError is not True

        # Should have structuredContent with clusters
        assert result.structuredContent is not None
        assert "clusters" in result.structuredContent
        assert len(result.structuredContent["clusters"]) == 1
