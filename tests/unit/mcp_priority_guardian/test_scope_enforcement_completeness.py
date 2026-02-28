"""
Unit tests for Priority Guardian scope enforcement completeness.

Tests verify:
- Every registered tool has required_scopes defined
- enforce_tool_scope resolves every registered tool
- Insufficient scopes are rejected
- Unknown tools fail closed (UnauthorizedError)
- No raw token values are logged
"""

import pytest
from structlog.testing import capture_logs
from unittest.mock import patch


class TestScopeEnforcementCompleteness:
    """Tests for scope enforcement using TOOL_REGISTRY as single source of truth."""

    def test_every_registered_tool_has_required_scopes(self):
        """Every tool in TOOL_REGISTRY has non-empty required_scopes."""
        from mcp_server.priority_guardian.tools import TOOL_REGISTRY
        from mcp_server.priority_guardian.config import SCOPES_SUPPORTED

        for tool_name, tool_def in TOOL_REGISTRY.items():
            # Every tool must have required_scopes as a non-empty list
            assert isinstance(tool_def.required_scopes, list), \
                f"{tool_name}: required_scopes must be a list"
            assert len(tool_def.required_scopes) > 0, \
                f"{tool_name}: required_scopes must not be empty"

            # Every scope in required_scopes must exist in SCOPES_SUPPORTED
            for scope in tool_def.required_scopes:
                assert scope in SCOPES_SUPPORTED, \
                    f"{tool_name}: scope '{scope}' not in SCOPES_SUPPORTED"

    def test_enforce_tool_scope_resolves_every_registered_tool(self):
        """enforce_tool_scope can resolve every tool in TOOL_REGISTRY."""
        from mcp_server.priority_guardian.tools import TOOL_REGISTRY
        from mcp_server.priority_guardian.mcp_auth import enforce_tool_scope

        # All PG tools require pg.access
        valid_scopes = {"pg.access"}

        for tool_name in TOOL_REGISTRY.keys():
            # Should not raise any exception
            enforce_tool_scope(tool_name, valid_scopes, "test-corr")

    def test_enforce_tool_scope_rejects_insufficient_scopes(self):
        """enforce_tool_scope raises InsufficientScopeError for wrong scopes."""
        from mcp_server.priority_guardian.mcp_auth import (
            enforce_tool_scope,
            InsufficientScopeError,
        )

        wrong_scopes = {"wrong.scope"}

        with pytest.raises(InsufficientScopeError) as exc_info:
            enforce_tool_scope("get_patterns", wrong_scopes, "test-corr")

        # Verify error contains correct required scopes
        assert exc_info.value.required_scopes == ["pg.access"]

    def test_enforce_tool_scope_unknown_tool_fails_closed(self):
        """enforce_tool_scope raises UnauthorizedError for unknown tools."""
        from mcp_server.priority_guardian.mcp_auth import (
            enforce_tool_scope,
            UnauthorizedError,
        )

        valid_scopes = {"pg.access"}

        with pytest.raises(UnauthorizedError) as exc_info:
            enforce_tool_scope("nonexistent_tool", valid_scopes, "test-corr")

        # Should be invalid_token error (not scope error)
        assert exc_info.value.error == "invalid_token"

    def test_enforce_tool_scope_does_not_log_token_values(self):
        """enforce_tool_scope logs scope names but not raw token strings."""
        from mcp_server.priority_guardian.mcp_auth import (
            enforce_tool_scope,
            InsufficientScopeError,
        )

        # Use a distinctive scope name we can search for
        wrong_scopes = {"wrong.scope.12345"}

        with capture_logs() as cap_logs:
            try:
                enforce_tool_scope("get_patterns", wrong_scopes, "test-corr")
            except InsufficientScopeError:
                pass

        # Find log entries from scope enforcement
        scope_logs = [
            log for log in cap_logs
            if "scope.enforcement" in log.get("event", "")
        ]

        # Should have logged something
        assert len(scope_logs) > 0

        # Check that logs contain scope names (acceptable)
        log_str = str(scope_logs)
        assert "pg.access" in log_str or "wrong.scope" in log_str

        # Check that logs don't contain raw JWT tokens
        # (JWT tokens start with "eyJ" and contain two dots)
        assert "eyJ" not in log_str
        assert "Bearer" not in log_str
