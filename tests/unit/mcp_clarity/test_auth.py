"""
Clarity MCP authentication unit tests.

Tests JWT validation, scope enforcement, and OAuth discovery for Clarity tools.
"""

import pytest
import jwt
from unittest.mock import AsyncMock, patch

from mcp_server.clarity.mcp_auth import (
    authenticate_request,
    extract_bearer_token,
    check_scopes,
    extract_or_generate_correlation_id,
    UnauthorizedError,
    InsufficientScopeError,
    build_unauthorized_meta,
    build_forbidden_meta,
)
from mcp_server.clarity.discovery import oauth_protected_resource
from mcp_server.clarity.config import MCP_SERVER_URL, OAUTH_ISSUER_URL, SCOPES_SUPPORTED, TOOL_SCOPES


class TestExtractBearerToken:
    """Test Bearer token extraction from Authorization header."""

    def test_valid_bearer_token(self):
        """Valid Bearer token extracted correctly."""
        token = extract_bearer_token("Bearer abc123")
        assert token == "abc123"

    def test_missing_header(self):
        """Missing header returns None."""
        assert extract_bearer_token(None) is None

    def test_empty_header(self):
        """Empty header returns None."""
        assert extract_bearer_token("") is None

    def test_wrong_scheme(self):
        """Non-Bearer scheme returns None."""
        assert extract_bearer_token("Basic abc123") is None

    def test_malformed_header(self):
        """Malformed header returns None."""
        assert extract_bearer_token("Bearer") is None
        assert extract_bearer_token("Bearertoken") is None

    def test_case_insensitive_bearer(self):
        """Bearer scheme is case insensitive."""
        assert extract_bearer_token("bearer abc123") == "abc123"
        assert extract_bearer_token("BEARER abc123") == "abc123"


class TestCheckScopes:
    """Test scope validation."""

    def test_has_required_scope(self):
        """Token with required scope passes."""
        assert check_scopes({"clarity.write", "other"}, ["clarity.write"]) is True

    def test_missing_required_scope(self):
        """Token without required scope fails."""
        assert check_scopes({"focused.write"}, ["clarity.write"]) is False

    def test_empty_required_scopes(self):
        """Empty required scopes always passes."""
        assert check_scopes(set(), []) is True

    def test_multiple_required_scopes(self):
        """All required scopes must be present."""
        assert check_scopes({"a", "b", "c"}, ["a", "b"]) is True
        assert check_scopes({"a", "c"}, ["a", "b"]) is False


class TestUnknownToolHandling:
    """Test behavior with unknown or unmapped tool names.

    Security critical: unknown tools must fail closed, not silently pass.
    """

    @pytest.mark.asyncio
    async def test_unknown_tool_raises_error(self):
        """Unknown tool name must raise InsufficientScopeError (fail closed)."""
        meta = {"headers": {"authorization": "Bearer validtoken"}}

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.return_value = {
                "user_id": "user-123",
                "scopes": {"clarity.write"},
                "jti": "token-id",
                "azp": "client-id"
            }

            # Unknown tool should fail, not silently pass
            with pytest.raises(InsufficientScopeError):
                await authenticate_request("unknown_tool_name", meta)

    @pytest.mark.asyncio
    async def test_typo_in_tool_name_raises_error(self):
        """Typo in tool name must raise error, not bypass auth."""
        meta = {"headers": {"authorization": "Bearer validtoken"}}

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.return_value = {
                "user_id": "user-123",
                "scopes": {"clarity.write"},
                "jti": "token-id",
                "azp": "client-id"
            }

            # Typo: "cluster_raw_thought" instead of "organize_thoughts"
            with pytest.raises(InsufficientScopeError):
                await authenticate_request("cluster_raw_thought", meta)

    @pytest.mark.asyncio
    async def test_empty_tool_name_raises_error(self):
        """Empty tool name must raise error."""
        meta = {"headers": {"authorization": "Bearer validtoken"}}

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.return_value = {
                "user_id": "user-123",
                "scopes": {"clarity.write"},
                "jti": "token-id",
                "azp": "client-id"
            }

            with pytest.raises(InsufficientScopeError):
                await authenticate_request("", meta)


class TestAzpClientIdHandling:
    """Test azp (authorized party / client_id) handling.

    NOTE: azp validation was REMOVED because dynamic client registration
    assigns different client_ids per user. The azp claim is still extracted
    and returned for logging/auditing purposes, but is not validated.
    See remove_azp.md for details.
    """

    @pytest.mark.asyncio
    async def test_azp_returned_in_auth_context(self):
        """Valid auth returns azp in context for logging/auditing."""
        meta = {"headers": {"authorization": "Bearer validtoken"}}

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.return_value = {
                "user_id": "user-123",
                "scopes": {"clarity.write"},
                "jti": "token-id",
                "azp": "chatgpt-client-xyz"
            }

            result = await authenticate_request("organize_thoughts", meta)

            assert "azp" in result
            assert result["azp"] == "chatgpt-client-xyz"

    @pytest.mark.asyncio
    async def test_any_azp_value_accepted(self):
        """Any azp value is accepted (no validation)."""
        meta = {"headers": {"authorization": "Bearer validtoken"}}

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            # Any azp value should work - no validation
            mock_validate.return_value = {
                "user_id": "user-123",
                "scopes": {"clarity.write"},
                "jti": "token-id",
                "azp": "any-random-client-id-12345"
            }

            result = await authenticate_request("organize_thoughts", meta)

            # Should succeed with any azp
            assert result["azp"] == "any-random-client-id-12345"
            assert result["user_id"] == "user-123"

    @pytest.mark.asyncio
    async def test_missing_azp_accepted(self):
        """Token without azp claim is accepted (azp not required)."""
        meta = {"headers": {"authorization": "Bearer validtoken"}}

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            # No azp in return value
            mock_validate.return_value = {
                "user_id": "user-123",
                "scopes": {"clarity.write"},
                "jti": "token-id",
                "azp": None  # No azp
            }

            result = await authenticate_request("organize_thoughts", meta)

            # Should succeed even without azp
            assert result["azp"] is None
            assert result["user_id"] == "user-123"


class TestJWTValidationFailures:
    """Test JWT validation failure paths.

    Critical: All JWT failures must result in UnauthorizedError, not leaked exceptions.
    """

    @pytest.mark.asyncio
    async def test_expired_jwt_raises_unauthorized(self):
        """Expired JWT raises UnauthorizedError."""
        meta = {"headers": {"authorization": "Bearer expiredtoken"}}

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.side_effect = jwt.ExpiredSignatureError("Token expired")

            with pytest.raises(UnauthorizedError) as exc_info:
                await authenticate_request("organize_thoughts", meta)

            assert "expired" in exc_info.value.description.lower()

    @pytest.mark.asyncio
    async def test_invalid_signature_raises_unauthorized(self):
        """Invalid JWT signature raises UnauthorizedError."""
        meta = {"headers": {"authorization": "Bearer tampered"}}

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.side_effect = jwt.InvalidSignatureError("Signature verification failed")

            with pytest.raises(UnauthorizedError):
                await authenticate_request("organize_thoughts", meta)

    @pytest.mark.asyncio
    async def test_invalid_token_raises_unauthorized(self):
        """Malformed/invalid JWT raises UnauthorizedError."""
        meta = {"headers": {"authorization": "Bearer notajwt"}}

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.side_effect = jwt.InvalidTokenError("Not a valid JWT")

            with pytest.raises(UnauthorizedError):
                await authenticate_request("organize_thoughts", meta)

    @pytest.mark.asyncio
    async def test_decode_error_raises_unauthorized(self):
        """JWT decode error raises UnauthorizedError."""
        meta = {"headers": {"authorization": "Bearer garbled"}}

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.side_effect = jwt.DecodeError("Unable to decode")

            with pytest.raises(UnauthorizedError):
                await authenticate_request("organize_thoughts", meta)

    @pytest.mark.asyncio
    async def test_invalid_issuer_raises_unauthorized(self):
        """JWT with wrong issuer raises UnauthorizedError."""
        meta = {"headers": {"authorization": "Bearer wrongissuer"}}

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.side_effect = jwt.InvalidIssuerError("Invalid issuer")

            with pytest.raises(UnauthorizedError):
                await authenticate_request("organize_thoughts", meta)

    @pytest.mark.asyncio
    async def test_invalid_audience_raises_unauthorized(self):
        """JWT with wrong audience raises UnauthorizedError."""
        meta = {"headers": {"authorization": "Bearer wrongaudience"}}

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.side_effect = jwt.InvalidAudienceError("Invalid audience")

            with pytest.raises(UnauthorizedError):
                await authenticate_request("organize_thoughts", meta)

    @pytest.mark.asyncio
    async def test_generic_exception_raises_unauthorized(self):
        """Unexpected exception during validation raises UnauthorizedError (fail closed)."""
        meta = {"headers": {"authorization": "Bearer validtoken"}}

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.side_effect = Exception("Unexpected JWKS fetch failure")

            with pytest.raises(UnauthorizedError):
                await authenticate_request("organize_thoughts", meta)

    @pytest.mark.asyncio
    async def test_jwt_errors_dont_leak_internal_details(self):
        """JWT errors should not leak internal error messages to client."""
        meta = {"headers": {"authorization": "Bearer badtoken"}}

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            # Simulate an error with sensitive info
            mock_validate.side_effect = jwt.InvalidTokenError(
                "kid 'secret-key-id-123' not found in JWKS at https://internal.example.com/jwks"
            )

            with pytest.raises(UnauthorizedError) as exc_info:
                await authenticate_request("organize_thoughts", meta)

            # The error description should be generic, not expose internal URLs/key IDs
            assert exc_info.value.error == "invalid_token"
            assert "internal.example.com" not in exc_info.value.description


class TestAuthenticateRequest:
    """Test full authentication flow."""

    @pytest.mark.asyncio
    async def test_missing_authorization_header(self):
        """Missing Authorization header raises UnauthorizedError."""
        meta = {"headers": {}}

        with pytest.raises(UnauthorizedError):
            await authenticate_request("organize_thoughts", meta)

    @pytest.mark.asyncio
    async def test_none_token_never_reaches_validate_jwt(self):
        """Verify None token is caught before reaching validate_jwt (defense in depth)."""
        meta = {"headers": {"authorization": "Bearer"}}  # Malformed - no token after Bearer

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            with pytest.raises(UnauthorizedError):
                await authenticate_request("organize_thoughts", meta)

            # validate_jwt should NEVER be called with None
            mock_validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_token_never_reaches_validate_jwt(self):
        """Verify empty token is caught before reaching validate_jwt."""
        meta = {"headers": {"authorization": "Bearer "}}  # Space but no token

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            with pytest.raises(UnauthorizedError):
                await authenticate_request("organize_thoughts", meta)

            mock_validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_jwt_not_called_when_token_extraction_fails(self):
        """If no bearer token, validate_jwt should never be called.

        Defense-in-depth: Ensures auth short-circuits before JWT validation
        when token extraction fails. Prevents future refactors from
        reintroducing fail-open behavior.
        """
        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            with pytest.raises(UnauthorizedError):
                await authenticate_request("organize_thoughts", {})
            mock_validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_headers_dict(self):
        """Missing headers dict raises UnauthorizedError."""
        meta = {}

        with pytest.raises(UnauthorizedError):
            await authenticate_request("organize_thoughts", meta)

    @pytest.mark.asyncio
    async def test_none_meta(self):
        """None meta raises UnauthorizedError."""
        with pytest.raises(UnauthorizedError):
            await authenticate_request("organize_thoughts", None)

    @pytest.mark.asyncio
    async def test_non_dict_meta_raises_unauthorized(self):
        """Non-dict meta raises UnauthorizedError (defensive guard)."""
        # meta could be a string, list, or other type if FastMCP changes
        with pytest.raises(UnauthorizedError):
            await authenticate_request("organize_thoughts", "not a dict")

        with pytest.raises(UnauthorizedError):
            await authenticate_request("organize_thoughts", ["list", "meta"])

    @pytest.mark.asyncio
    async def test_non_dict_headers_raises_unauthorized(self):
        """Non-dict headers value raises UnauthorizedError (defensive guard)."""
        # headers value could be malformed
        meta = {"headers": "not a dict"}
        with pytest.raises(UnauthorizedError):
            await authenticate_request("organize_thoughts", meta)

        meta = {"headers": ["list", "headers"]}
        with pytest.raises(UnauthorizedError):
            await authenticate_request("organize_thoughts", meta)

    @pytest.mark.asyncio
    async def test_invalid_token_format(self):
        """Invalid token format raises UnauthorizedError."""
        meta = {"headers": {"authorization": "InvalidFormat"}}

        with pytest.raises(UnauthorizedError):
            await authenticate_request("organize_thoughts", meta)

    @pytest.mark.asyncio
    async def test_wrong_scope_raises_insufficient(self):
        """Valid token with wrong scope raises InsufficientScopeError."""
        meta = {"headers": {"authorization": "Bearer validtoken"}}

        # Mock validate_jwt to return focused.write instead of clarity.write
        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.return_value = {
                "user_id": "user-123",
                "scopes": {"focused.write"},  # Wrong scope
                "jti": "token-id",
                "azp": "client-id"
            }

            with pytest.raises(InsufficientScopeError):
                await authenticate_request("organize_thoughts", meta)

    @pytest.mark.asyncio
    async def test_valid_token_returns_context(self):
        """Valid token with correct scope returns auth context."""
        meta = {"headers": {"authorization": "Bearer validtoken"}}

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.return_value = {
                "user_id": "user-123",
                "scopes": {"clarity.write"},
                "jti": "token-id",
                "azp": "client-id"
            }

            result = await authenticate_request("organize_thoughts", meta)

            assert result["user_id"] == "user-123"
            assert "correlation_id" in result
            assert "clarity.write" in result["scopes"]

    @pytest.mark.asyncio
    async def test_case_insensitive_header_keys(self):
        """Authorization header lookup is case insensitive."""
        meta = {"headers": {"Authorization": "Bearer validtoken"}}

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.return_value = {
                "user_id": "user-123",
                "scopes": {"clarity.write"},
                "jti": "token-id",
                "azp": "client-id"
            }

            result = await authenticate_request("organize_thoughts", meta)
            assert result["user_id"] == "user-123"


class TestOAuthResourceDiscovery:
    """Test OAuth Protected Resource discovery endpoint."""

    @pytest.mark.asyncio
    async def test_discovery_returns_resource_url(self):
        """Discovery returns correct resource URL (MCP server URL)."""
        result = await oauth_protected_resource()

        assert "resource" in result
        assert result["resource"] == MCP_SERVER_URL

    @pytest.mark.asyncio
    async def test_discovery_points_to_oauth_pg_authorization_server(self):
        """Discovery points to /oauth/pg as the authorization server."""
        result = await oauth_protected_resource()

        assert "authorization_servers" in result
        assert len(result["authorization_servers"]) == 1
        assert result["authorization_servers"][0] == OAUTH_ISSUER_URL
        # Should point to /oauth/pg (not /oauth/focused)
        assert "/oauth/pg" in OAUTH_ISSUER_URL or "localhost" in OAUTH_ISSUER_URL

    @pytest.mark.asyncio
    async def test_discovery_advertises_clarity_write_scope(self):
        """Discovery advertises clarity.write scope."""
        result = await oauth_protected_resource()

        assert "scopes_supported" in result
        assert "clarity.write" in result["scopes_supported"]

    @pytest.mark.asyncio
    async def test_discovery_uses_config_scopes(self):
        """Discovery returns scopes from config."""
        result = await oauth_protected_resource()

        assert result["scopes_supported"] == SCOPES_SUPPORTED

    @pytest.mark.asyncio
    async def test_discovery_response_structure(self):
        """Discovery response has all required RFC 9728 fields."""
        result = await oauth_protected_resource()

        # RFC 9728 required fields for oauth-protected-resource
        assert "resource" in result
        assert "authorization_servers" in result
        assert "scopes_supported" in result

        # Types
        assert isinstance(result["resource"], str)
        assert isinstance(result["authorization_servers"], list)
        assert isinstance(result["scopes_supported"], list)


class TestMetaBuilders:
    """Test _meta builders for CallToolResult responses.

    Per OpenAI MCP Authentication spec, _meta["mcp/www_authenticate"] must contain
    RFC 7235 challenge strings, not JSON objects.
    """

    def test_unauthorized_meta_structure(self):
        """Test 401 meta has correct flat structure for CallToolResult._meta."""
        result = build_unauthorized_meta()

        # Should be flat dict, not nested error envelope
        assert "mcp/www_authenticate" in result
        assert "error" not in result  # No JSON-RPC envelope

    def test_unauthorized_meta_rfc7235_format(self):
        """Test WWW-Authenticate is RFC 7235 challenge string."""
        result = build_unauthorized_meta()

        www_auth = result["mcp/www_authenticate"]
        assert len(www_auth) == 1
        assert isinstance(www_auth[0], str)  # String, not dict
        assert www_auth[0].startswith("Bearer ")
        assert "resource_metadata=" in www_auth[0]
        assert "oauth-protected-resource" in www_auth[0]
        assert 'error="invalid_token"' in www_auth[0]

    def test_unauthorized_meta_resource_metadata_url(self):
        """Unauthorized meta points to correct discovery URL."""
        result = build_unauthorized_meta()

        www_auth = result["mcp/www_authenticate"][0]
        assert f"{MCP_SERVER_URL}/.well-known/oauth-protected-resource" in www_auth

    def test_forbidden_meta_structure(self):
        """Test 403 meta has correct flat structure for CallToolResult._meta."""
        result = build_forbidden_meta()

        # Should be flat dict, not nested error envelope
        assert "mcp/www_authenticate" in result
        assert "error" not in result  # No JSON-RPC envelope

    def test_forbidden_meta_rfc7235_format(self):
        """Test 403 WWW-Authenticate is RFC 7235 challenge string."""
        result = build_forbidden_meta()

        www_auth = result["mcp/www_authenticate"]
        assert len(www_auth) == 1
        assert isinstance(www_auth[0], str)  # String, not dict
        assert www_auth[0].startswith("Bearer ")
        assert "oauth-protected-resource" in www_auth[0]
        assert 'error="insufficient_scope"' in www_auth[0]

    def test_forbidden_meta_resource_metadata_url(self):
        """Forbidden meta points to correct discovery URL."""
        result = build_forbidden_meta()

        www_auth = result["mcp/www_authenticate"][0]
        assert f"{MCP_SERVER_URL}/.well-known/oauth-protected-resource" in www_auth

    def test_invalid_params_error_structure(self):
        """build_invalid_params_error returns correct JSON-RPC structure."""
        from mcp_server.clarity.mcp_auth import build_invalid_params_error

        error = build_invalid_params_error()

        # Must have error object
        assert "error" in error
        assert isinstance(error["error"], dict)

        # Error must have code and message
        assert error["error"]["code"] == -32602
        assert error["error"]["message"] == "Invalid parameters"

        # No data when no details provided
        assert "data" not in error["error"]

    def test_invalid_params_error_with_message(self):
        """build_invalid_params_error accepts custom message."""
        from mcp_server.clarity.mcp_auth import build_invalid_params_error

        error = build_invalid_params_error(message="Custom error message")

        assert error["error"]["message"] == "Custom error message"

    def test_invalid_params_error_with_details(self):
        """build_invalid_params_error includes details when provided."""
        from mcp_server.clarity.mcp_auth import build_invalid_params_error

        error = build_invalid_params_error(
            message="Invalid input format",
            details="Expected 'clusters' array"
        )

        assert "data" in error["error"]
        assert error["error"]["data"]["details"] == "Expected 'clusters' array"

    def test_invalid_params_error_no_oauth_metadata(self):
        """Invalid params error does NOT include OAuth metadata (not an auth error)."""
        from mcp_server.clarity.mcp_auth import build_invalid_params_error

        error = build_invalid_params_error()

        # Should NOT have _meta or www_authenticate (this is a validation error, not auth)
        if "data" in error["error"]:
            assert "_meta" not in error["error"]["data"]


class TestExceptionAttributes:
    """Test exception class attributes (interface contract)."""

    def test_unauthorized_error_attributes(self):
        """UnauthorizedError has expected attributes."""
        exc = UnauthorizedError(error="invalid_token", description="Token expired")

        assert hasattr(exc, "error")
        assert hasattr(exc, "description")
        assert exc.error == "invalid_token"
        assert exc.description == "Token expired"
        assert str(exc) == "Token expired"  # __init__ calls super().__init__(description)

    def test_insufficient_scope_error_attributes(self):
        """InsufficientScopeError has expected attributes."""
        exc = InsufficientScopeError(
            required_scopes=["clarity.write"],
            actual_scopes=["focused.read"]
        )

        assert hasattr(exc, "error")
        assert hasattr(exc, "description")
        assert hasattr(exc, "required_scopes")
        assert hasattr(exc, "actual_scopes")

        assert exc.error == "insufficient_scope"
        assert exc.required_scopes == ["clarity.write"]
        assert exc.actual_scopes == ["focused.read"]
        assert "clarity.write" in exc.description
        assert "focused.read" in exc.description


class TestToolScopeConfig:
    """Test TOOL_SCOPES configuration (config correctness)."""

    def test_organize_thoughts_requires_clarity_write(self):
        """organize_thoughts tool requires clarity.write scope."""
        assert "organize_thoughts" in TOOL_SCOPES
        assert "clarity.write" in TOOL_SCOPES["organize_thoughts"]

    def test_all_tools_have_scopes(self):
        """All registered tools have at least one scope."""
        for tool_name, scopes in TOOL_SCOPES.items():
            assert isinstance(scopes, list), f"{tool_name} scopes should be a list"
            assert len(scopes) > 0, f"{tool_name} should have at least one scope"

    def test_scopes_are_strings(self):
        """All scope values are strings."""
        for tool_name, scopes in TOOL_SCOPES.items():
            for scope in scopes:
                assert isinstance(scope, str), f"Scope '{scope}' in {tool_name} should be string"

    def test_no_focused_scopes_in_clarity_tools(self):
        """Clarity tools should not require focused.* scopes."""
        for tool_name, scopes in TOOL_SCOPES.items():
            for scope in scopes:
                assert not scope.startswith("focused."), \
                    f"Clarity tool '{tool_name}' should not require focused scope '{scope}'"


class TestCorrelationId:
    """Test correlation ID generation and extraction."""

    def test_generates_uuid_when_meta_is_none(self):
        """Generates UUID when meta is None."""
        correlation_id = extract_or_generate_correlation_id(None)

        assert correlation_id is not None
        assert isinstance(correlation_id, str)
        assert len(correlation_id) == 36  # UUID format: 8-4-4-4-12

    def test_generates_uuid_when_meta_empty(self):
        """Generates UUID when meta is empty dict."""
        correlation_id = extract_or_generate_correlation_id({})

        assert correlation_id is not None
        assert len(correlation_id) == 36

    def test_extracts_correlation_id_from_meta(self):
        """Extracts correlation_id from meta if present."""
        expected_id = "test-correlation-123"
        meta = {"correlation_id": expected_id}

        correlation_id = extract_or_generate_correlation_id(meta)

        assert correlation_id == expected_id

    def test_generates_uuid_when_correlation_id_empty_string(self):
        """Generates UUID when correlation_id is empty string."""
        meta = {"correlation_id": ""}

        correlation_id = extract_or_generate_correlation_id(meta)

        # Should generate new UUID, not use empty string
        assert correlation_id != ""
        assert len(correlation_id) == 36

    def test_generates_uuid_when_correlation_id_none(self):
        """Generates UUID when correlation_id is None."""
        meta = {"correlation_id": None}

        correlation_id = extract_or_generate_correlation_id(meta)

        assert correlation_id is not None
        assert len(correlation_id) == 36

    @pytest.mark.asyncio
    async def test_correlation_id_returned_in_auth_context(self):
        """authenticate_request returns correlation_id in context."""
        meta = {
            "headers": {"authorization": "Bearer validtoken"},
            "correlation_id": "request-correlation-456"
        }

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.return_value = {
                "user_id": "user-123",
                "scopes": {"clarity.write"},
                "jti": "token-id",
                "azp": "client-id"
            }

            result = await authenticate_request("organize_thoughts", meta)

        assert "correlation_id" in result
        assert result["correlation_id"] == "request-correlation-456"
