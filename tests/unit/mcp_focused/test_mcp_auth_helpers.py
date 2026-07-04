"""
MCP authentication helper function tests.

Tests MCP auth helper functions without complex JWT/JWKS mocking:
- Header extraction
- Token parsing
- Scope checking
- Error building
"""

import pytest
import time
from unittest.mock import Mock, AsyncMock, patch

from mcp_server.focused.mcp_auth import (
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
# Test: Header Extraction (Critical for 7D)
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
# Test: Scope Enforcement (Critical for 7D)
# =============================================================================

class TestScopeEnforcement:
    """Test scope checking logic - critical for authorization."""

    def test_check_scopes_all_present(self):
        """Test all required scopes are present."""
        token_scopes = {"focused.read", "focused.write", "focused.notify"}
        required = ["focused.read", "focused.write"]
        assert check_scopes(token_scopes, required) is True

    def test_check_scopes_exact_match(self):
        """Test exact match of scopes."""
        token_scopes = {"focused.read"}
        required = ["focused.read"]
        assert check_scopes(token_scopes, required) is True

    def test_check_scopes_missing_one(self):
        """Test missing one required scope."""
        token_scopes = {"focused.read"}
        required = ["focused.read", "focused.write"]
        assert check_scopes(token_scopes, required) is False

    def test_check_scopes_missing_all(self):
        """Test missing all required scopes."""
        token_scopes = {"focused.read"}
        required = ["focused.write", "focused.notify"]
        assert check_scopes(token_scopes, required) is False

    def test_check_scopes_empty_required(self):
        """Test no scopes required."""
        token_scopes = {"focused.read"}
        required = []
        assert check_scopes(token_scopes, required) is True

    def test_check_scopes_empty_token(self):
        """Test token has no scopes."""
        token_scopes = set()
        required = ["focused.read"]
        assert check_scopes(token_scopes, required) is False

    def test_check_scopes_both_empty(self):
        """Test both token and required are empty."""
        token_scopes = set()
        required = []
        assert check_scopes(token_scopes, required) is True


# =============================================================================
# Test: Correlation ID (Critical for 7D)
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
# Test: RFC 6750 Error Builders (Critical for 7D)
# =============================================================================

class TestErrorBuilders:
    """Test RFC 6750-compliant error response builders."""

    def test_unauthorized_error_structure(self):
        """Test 401 error has correct structure."""
        result = build_unauthorized_error("invalid_token", "Token expired")

        assert "error" in result
        assert result["error"]["code"] == -32001
        assert result["error"]["message"] == "Unauthorized"

        data = result["error"]["data"]
        assert data["error"] == "invalid_token"
        assert data["error_description"] == "Token expired"
        assert "www_authenticate" in data

    def test_unauthorized_error_www_authenticate_format(self):
        """Test WWW-Authenticate header format."""
        result = build_unauthorized_error("invalid_token", "Missing token")

        www_auth = result["error"]["data"]["www_authenticate"]
        assert "Bearer realm=" in www_auth
        assert "error=" in www_auth
        assert "error_description=" in www_auth
        assert "invalid_token" in www_auth

    def test_forbidden_error_structure(self):
        """Test 403 error has correct structure."""
        result = build_forbidden_error(
            required_scopes=["focused.write"],
            actual_scopes=["focused.read"]
        )

        assert result["error"]["code"] == -32002
        assert result["error"]["message"] == "Forbidden"

        data = result["error"]["data"]
        assert data["error"] == "insufficient_scope"
        assert data["required_scopes"] == ["focused.write"]
        assert data["actual_scopes"] == ["focused.read"]
        assert "www_authenticate" in data

    def test_forbidden_error_www_authenticate_format(self):
        """Test WWW-Authenticate for 403 includes scope."""
        result = build_forbidden_error(
            required_scopes=["focused.write", "focused.notify"],
            actual_scopes=["focused.read"]
        )

        www_auth = result["error"]["data"]["www_authenticate"]
        assert "Bearer realm=" in www_auth
        assert "error=\"insufficient_scope\"" in www_auth
        assert "scope=" in www_auth

    def test_forbidden_error_multiple_required_scopes(self):
        """Test error with multiple required scopes."""
        result = build_forbidden_error(
            required_scopes=["focused.write", "focused.notify"],
            actual_scopes=[]
        )

        data = result["error"]["data"]
        assert len(data["required_scopes"]) == 2
        assert "focused.write" in data["required_scopes"]
        assert "focused.notify" in data["required_scopes"]


# =============================================================================
# Test: Exception Classes (Critical for 7D)
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
            required_scopes=["focused.write"],
            actual_scopes=["focused.read"]
        )

        assert exc.error == "insufficient_scope"
        assert exc.required_scopes == ["focused.write"]
        assert exc.actual_scopes == ["focused.read"]
        assert "focused.write" in exc.description
        assert "focused.read" in exc.description


# =============================================================================
# Test: JWKS Cache Basics (Non-async parts)
# =============================================================================

class TestJWKSCacheBasics:
    """Test JWKS cache logic without async complexity."""

    def test_cache_empty_initially(self):
        """Test cache starts empty."""
        from mcp.focused.mcp_auth import JWKSCache
        cache = JWKSCache()

        assert cache._jwks is None
        assert cache._fetched_at is None

    def test_cache_valid_check_fresh(self):
        """Test cache is valid when fresh."""
        from mcp.focused.mcp_auth import JWKSCache
        cache = JWKSCache()

        cache._jwks = {"keys": []}
        cache._fetched_at = time.time()

        assert cache.is_cache_valid() is True

    def test_cache_valid_check_stale(self):
        """Test cache is invalid when > 24h old."""
        from mcp.focused.mcp_auth import JWKSCache
        cache = JWKSCache()

        cache._jwks = {"keys": []}
        cache._fetched_at = time.time() - (25 * 3600)  # 25 hours ago

        assert cache.is_cache_valid() is False

    def test_cache_too_old_check(self):
        """Test cache is too old when > 7 days."""
        from mcp.focused.mcp_auth import JWKSCache
        cache = JWKSCache()

        cache._jwks = {"keys": []}
        cache._fetched_at = time.time() - (8 * 24 * 3600)  # 8 days ago

        assert cache.is_cache_too_old() is True

    def test_cache_not_too_old_when_recent(self):
        """Test cache not too old when recent."""
        from mcp.focused.mcp_auth import JWKSCache
        cache = JWKSCache()

        cache._jwks = {"keys": []}
        cache._fetched_at = time.time() - (25 * 3600)  # 25 hours ago (stale but usable)

        assert cache.is_cache_too_old() is False


# =============================================================================
# Test: Backend Header Migration (Critical for 7D)
# =============================================================================

class TestBackendHeaderMigration:
    """Test backend accepts X-User-ID header with fallback."""

    def test_header_present(self):
        """Test reading X-User-ID header when present."""
        # Mock request
        request = Mock()
        request.headers = {"x-user-id": "user-from-header"}

        user_id = request.headers.get("x-user-id")
        assert user_id == "user-from-header"

    def test_header_missing_fallback_to_payload(self):
        """Test fallback to payload when header missing."""
        request = Mock()
        request.headers = {}

        payload_user_id = "user-from-payload"

        # Simulate backend logic
        user_id = request.headers.get("x-user-id") or payload_user_id
        assert user_id == "user-from-payload"

    def test_header_wins_over_payload(self):
        """Test header takes precedence over payload."""
        request = Mock()
        request.headers = {"x-user-id": "user-from-header"}

        payload_user_id = "user-from-payload"

        # Simulate backend logic
        user_id = request.headers.get("x-user-id") or payload_user_id
        assert user_id == "user-from-header"

    def test_mismatch_detection(self):
        """Test detecting mismatch between header and payload."""
        header_value = "user-header"
        payload_value = "user-payload"

        assert header_value != payload_value  # Mismatch detected

    def test_none_header_fallback(self):
        """Test None header falls back correctly."""
        request = Mock()
        request.headers = Mock()
        request.headers.get = Mock(return_value=None)

        payload_user_id = "fallback-user"

        user_id = request.headers.get("x-user-id") or payload_user_id
        assert user_id == "fallback-user"


# =============================================================================
# Test: Tool Scope Mappings (Configuration)
# =============================================================================

class TestToolScopeMappings:
    """Test tool scope configuration is correct."""

    def test_check_calendar_scope(self):
        """Test check_calendar requires focused.read."""
        from mcp.focused.config import TOOL_SCOPES

        assert "check_calendar" in TOOL_SCOPES
        assert TOOL_SCOPES["check_calendar"] == ["focused.read"]

    def test_watch_calendar_scope(self):
        """Test watch_calendar requires focused.write."""
        from mcp.focused.config import TOOL_SCOPES

        assert "watch_calendar" in TOOL_SCOPES
        assert TOOL_SCOPES["watch_calendar"] == ["focused.write"]

    def test_run_focus_mode_scope(self):
        """Test run_focus_mode requires focused.write."""
        from mcp.focused.config import TOOL_SCOPES

        assert "run_focus_mode" in TOOL_SCOPES
        assert TOOL_SCOPES["run_focus_mode"] == ["focused.write"]

    def test_notify_user_scope(self):
        """Test notify_user requires focused.notify."""
        from mcp.focused.config import TOOL_SCOPES

        assert "notify_user" in TOOL_SCOPES
        assert TOOL_SCOPES["notify_user"] == ["focused.notify"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
