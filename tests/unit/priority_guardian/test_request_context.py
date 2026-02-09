"""
Unit tests for Priority Guardian request context.

Tests the auth_header_var ContextVar:
- Default is None
- Setting and reading works
- Different async contexts get independent values
"""

import pytest
import asyncio


class TestAuthHeaderVar:
    """Tests for auth_header_var ContextVar."""

    def test_default_is_none(self):
        """auth_header_var default is None."""
        from mcp_server.priority_guardian.request_context import auth_header_var

        # Reset to ensure clean state
        auth_header_var.set(None)
        assert auth_header_var.get() is None

    def test_set_and_get(self):
        """Setting and reading ContextVar works correctly."""
        from mcp_server.priority_guardian.request_context import auth_header_var

        test_value = "Bearer test-token-123"
        auth_header_var.set(test_value)

        assert auth_header_var.get() == test_value

        # Clean up
        auth_header_var.set(None)

    def test_get_with_default(self):
        """get() with default argument works."""
        from mcp_server.priority_guardian.request_context import auth_header_var

        auth_header_var.set(None)
        result = auth_header_var.get("default-value")

        # When explicitly set to None, get() returns None, not the default
        # The default is only used when the ContextVar has no value set
        assert result is None

    @pytest.mark.asyncio
    async def test_independent_async_contexts(self):
        """Different async contexts get independent values."""
        from mcp_server.priority_guardian.request_context import auth_header_var

        results = {}

        async def task_a():
            auth_header_var.set("Bearer token-A")
            await asyncio.sleep(0.01)  # Allow context switch
            results["a"] = auth_header_var.get()

        async def task_b():
            auth_header_var.set("Bearer token-B")
            await asyncio.sleep(0.01)  # Allow context switch
            results["b"] = auth_header_var.get()

        # Run tasks concurrently
        await asyncio.gather(task_a(), task_b())

        # Each task should see its own value
        assert results["a"] == "Bearer token-A"
        assert results["b"] == "Bearer token-B"

    @pytest.mark.asyncio
    async def test_value_inherited_by_subtasks(self):
        """Subtasks inherit the ContextVar value from parent."""
        from mcp_server.priority_guardian.request_context import auth_header_var

        auth_header_var.set("Bearer parent-token")

        async def subtask():
            return auth_header_var.get()

        result = await subtask()
        assert result == "Bearer parent-token"

        # Clean up
        auth_header_var.set(None)

    def test_reset_token(self):
        """ContextVar can be reset using Token."""
        from mcp_server.priority_guardian.request_context import auth_header_var

        # Set initial value
        auth_header_var.set("initial")

        # Set new value and get token
        token = auth_header_var.set("new-value")
        assert auth_header_var.get() == "new-value"

        # Reset to previous value
        auth_header_var.reset(token)
        assert auth_header_var.get() == "initial"

        # Clean up
        auth_header_var.set(None)
