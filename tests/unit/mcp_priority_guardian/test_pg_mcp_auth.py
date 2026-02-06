"""
Priority Guardian MCP authentication helper function tests.

Tests MCP auth helper functions without complex JWT/JWKS mocking:
- Header extraction
- Token parsing
- Scope checking
- Error building
"""

import pytest
import time
from unittest.mock import Mock, AsyncMock, patch

from mcp_server.priority_guardian.mcp_auth import (
    extract_authorization_header,
    extract_bearer_token,
    check_scopes,
    extract_or_generate_correlation_id,
    build_unauthorized_error,
    build_forbidden_error,
    UnauthorizedError,
    InsufficientScopeError,
)


# =============================================================================
# Test: Header Extraction
# =============================================================================

class TestHeaderExtraction:
    """Test Authorization header extraction - critical for MCP."""

    def test_extract_header_standard_case(self):
        """Test standard Authorization header."""
        headers = {"Authorization": "Bearer eyJ..."}
        result = extract_authorization_header(headers)
        assert result == "Bearer eyJ..."

    def test_extract_header_lowercase(self):
        """Test lowercase 'authorization' header."""
        headers = {"authorization": "Bearer eyJ..."}
        result = extract_authorization_header(headers)
        assert result == "Bearer eyJ..."

    def test_extract_header_mixed_case(self):
        """Test mixed case header (case-insensitive)."""
        headers = {"AuThOrIzAtIoN": "Bearer eyJ..."}
        result = extract_authorization_header(headers)
        assert result == "Bearer eyJ..."

    def test_extract_header_missing(self):
        """Test missing Authorization header."""
        headers = {"Content-Type": "application/json"}
        result = extract_authorization_header(headers)
        assert result is None

    def test_extract_bearer_token_valid(self):
        """Test extracting token from valid Bearer header."""
        result = extract_bearer_token("Bearer eyJhbGciOiJSUzI1NiJ9...")
        assert result == "eyJhbGciOiJSUzI1NiJ9..."

    def test_extract_bearer_token_lowercase(self):
        """Test 'bearer' lowercase."""
        result = extract_bearer_token("bearer token123")
        assert result == "token123"

    def test_extract_bearer_token_invalid_scheme(self):
        """Test non-Bearer scheme."""
        result = extract_bearer_token("Basic token123")
        assert result is None

    def test_extract_bearer_token_no_token(self):
        """Test Bearer without token."""
        result = extract_bearer_token("Bearer")
        assert result is None

    def test_extract_bearer_token_empty(self):
        """Test Bearer with empty token."""
        result = extract_bearer_token("Bearer ")
        assert result is None

    def test_extract_bearer_token_none(self):
        """Test None input."""
        result = extract_bearer_token(None)
        assert result is None


# =============================================================================
# Test: Scope Enforcement
# =============================================================================

class TestScopeEnforcement:
    """Test scope checking logic - critical for authorization."""

    def test_check_scopes_all_present(self):
        """Test all required scopes are present."""
        token_scopes = {"pg.access", "other.scope"}
        required = ["pg.access"]
        assert check_scopes(token_scopes, required) is True

    def test_check_scopes_exact_match(self):
        """Test exact match of scopes."""
        token_scopes = {"pg.access"}
        required = ["pg.access"]
        assert check_scopes(token_scopes, required) is True

    def test_check_scopes_missing_one(self):
        """Test missing one required scope."""
        token_scopes = {"other.scope"}
        required = ["pg.access"]
        assert check_scopes(token_scopes, required) is False

    def test_check_scopes_missing_all(self):
        """Test missing all required scopes."""
        token_scopes = {"focused.read"}
        required = ["pg.access"]
        assert check_scopes(token_scopes, required) is False

    def test_check_scopes_empty_required(self):
        """Test no scopes required."""
        token_scopes = {"pg.access"}
        required = []
        assert check_scopes(token_scopes, required) is True

    def test_check_scopes_empty_token(self):
        """Test token has no scopes."""
        token_scopes = set()
        required = ["pg.access"]
        assert check_scopes(token_scopes, required) is False

    def test_check_scopes_both_empty(self):
        """Test both token and required are empty."""
        token_scopes = set()
        required = []
        assert check_scopes(token_scopes, required) is True


# =============================================================================
# Test: Correlation ID
# =============================================================================

class TestCorrelationID:
    """Test correlation ID extraction and generation."""

    def test_extract_existing_correlation_id(self):
        """Test extracting correlation_id from metadata."""
        meta = {"correlation_id": "existing-123"}
        result = extract_or_generate_correlation_id(meta)
        assert result == "existing-123"

    def test_generate_when_missing(self):
        """Test generating new correlation_id when missing."""
        meta = {"headers": {}}
        result = extract_or_generate_correlation_id(meta)
        # Should be UUID format
        assert len(result) == 36
        assert result.count("-") == 4

    def test_generate_when_meta_none(self):
        """Test generating when metadata is None."""
        result = extract_or_generate_correlation_id(None)
        assert len(result) == 36

    def test_generate_when_empty_string(self):
        """Test generating when correlation_id is empty string."""
        meta = {"correlation_id": ""}
        result = extract_or_generate_correlation_id(meta)
        assert len(result) == 36

    def test_generate_unique_ids(self):
        """Test that generated IDs are unique."""
        id1 = extract_or_generate_correlation_id(None)
        id2 = extract_or_generate_correlation_id(None)
        assert id1 != id2


# =============================================================================
# Test: Error Builders
# =============================================================================

class TestErrorBuilders:
    """Test MCP-compliant error response builders."""

    def test_unauthorized_error_structure(self):
        """Test 401 error has correct JSON-RPC structure."""
        result = build_unauthorized_error("invalid_token", "Token expired")

        assert "error" in result
        assert result["error"]["code"] == -32001
        assert result["error"]["message"] == "Unauthorized"

        data = result["error"]["data"]
        assert "_meta" in data
        assert "mcp/www_authenticate" in data["_meta"]

    def test_unauthorized_error_oauth_discovery(self):
        """Test WWW-Authenticate includes OAuth discovery URL."""
        result = build_unauthorized_error("invalid_token", "Missing token")

        www_auth = result["error"]["data"]["_meta"]["mcp/www_authenticate"]
        assert len(www_auth) == 1
        assert www_auth[0]["type"] == "oauth2"
        assert "oauth-protected-resource" in www_auth[0]["resource_metadata"]

    def test_forbidden_error_structure(self):
        """Test 403 error has correct JSON-RPC structure."""
        result = build_forbidden_error(
            required_scopes=["pg.access"],
            actual_scopes=["other.scope"]
        )

        assert result["error"]["code"] == -32003
        assert result["error"]["message"] == "Forbidden"

        data = result["error"]["data"]
        assert "_meta" in data
        assert "mcp/www_authenticate" in data["_meta"]

    def test_forbidden_error_oauth_discovery(self):
        """Test 403 includes OAuth discovery URL."""
        result = build_forbidden_error(
            required_scopes=["pg.access"],
            actual_scopes=[]
        )

        www_auth = result["error"]["data"]["_meta"]["mcp/www_authenticate"]
        assert www_auth[0]["type"] == "oauth2"
        assert "oauth-protected-resource" in www_auth[0]["resource_metadata"]


# =============================================================================
# Test: Exception Classes
# =============================================================================

class TestExceptionClasses:
    """Test custom exception classes."""

    def test_unauthorized_error_attributes(self):
        """Test UnauthorizedError has correct attributes."""
        exc = UnauthorizedError("invalid_token", "Token expired")

        assert exc.error == "invalid_token"
        assert exc.description == "Token expired"
        assert str(exc) == "Token expired"

    def test_insufficient_scope_error_attributes(self):
        """Test InsufficientScopeError has correct attributes."""
        exc = InsufficientScopeError(
            required_scopes=["pg.access"],
            actual_scopes=["other.scope"]
        )

        assert exc.error == "insufficient_scope"
        assert exc.required_scopes == ["pg.access"]
        assert exc.actual_scopes == ["other.scope"]
        assert "pg.access" in exc.description


# =============================================================================
# Test: JWKS Cache Basics (Non-async parts)
# =============================================================================

class TestJWKSCacheBasics:
    """Test JWKS cache logic without async complexity."""

    def test_cache_empty_initially(self):
        """Test cache starts empty."""
        from mcp_server.priority_guardian.mcp_auth import JWKSCache
        cache = JWKSCache()

        assert cache._jwks is None
        assert cache._fetched_at is None

    def test_cache_valid_check_fresh(self):
        """Test cache is valid when fresh."""
        from mcp_server.priority_guardian.mcp_auth import JWKSCache
        cache = JWKSCache()

        cache._jwks = {"keys": []}
        cache._fetched_at = time.time()

        assert cache.is_cache_valid() is True

    def test_cache_valid_check_stale(self):
        """Test cache is invalid when > 24h old."""
        from mcp_server.priority_guardian.mcp_auth import JWKSCache
        cache = JWKSCache()

        cache._jwks = {"keys": []}
        cache._fetched_at = time.time() - (25 * 3600)  # 25 hours ago

        assert cache.is_cache_valid() is False

    def test_cache_too_old_check(self):
        """Test cache is too old when > 7 days."""
        from mcp_server.priority_guardian.mcp_auth import JWKSCache
        cache = JWKSCache()

        cache._jwks = {"keys": []}
        cache._fetched_at = time.time() - (8 * 24 * 3600)  # 8 days ago

        assert cache.is_cache_too_old() is True

    def test_cache_not_too_old_when_recent(self):
        """Test cache not too old when recent."""
        from mcp_server.priority_guardian.mcp_auth import JWKSCache
        cache = JWKSCache()

        cache._jwks = {"keys": []}
        cache._fetched_at = time.time() - (25 * 3600)  # 25 hours ago (stale but usable)

        assert cache.is_cache_too_old() is False


# =============================================================================
# Test: Tool Scope Mappings (Configuration)
# =============================================================================

class TestToolScopeMappings:
    """Test tool scope configuration is correct."""

    def test_connect_google_calendar_scope(self):
        """Test connect_google_calendar requires pg.access."""
        from mcp_server.priority_guardian.config import TOOL_SCOPES

        assert "connect_google_calendar" in TOOL_SCOPES
        assert TOOL_SCOPES["connect_google_calendar"] == ["pg.access"]

    def test_disconnect_google_calendar_scope(self):
        """Test disconnect_google_calendar requires pg.access."""
        from mcp_server.priority_guardian.config import TOOL_SCOPES

        assert "disconnect_google_calendar" in TOOL_SCOPES
        assert TOOL_SCOPES["disconnect_google_calendar"] == ["pg.access"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
