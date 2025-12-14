"""
Unit tests for Clarity MCP tool registry.
"""

import pytest

from mcp_server.clarity.tools import TOOL_REGISTRY, get_tool, register_tool
from mcp_server.clarity.tools.base import ToolDefinition


class TestToolRegistry:
    """Tests for tool registration and discovery."""

    def test_cluster_raw_thoughts_registered(self):
        """cluster_raw_thoughts tool should be in registry after import."""
        assert "cluster_raw_thoughts" in TOOL_REGISTRY

    def test_registry_returns_none_for_unknown(self):
        """get_tool should return None for unknown tool names."""
        result = get_tool("nonexistent_tool_that_does_not_exist")
        assert result is None

    def test_tool_definition_has_required_fields(self):
        """Tool definitions should have all required fields."""
        tool = get_tool("cluster_raw_thoughts")
        assert tool is not None

        # Check required fields
        assert isinstance(tool.name, str)
        assert len(tool.name) > 0

        assert isinstance(tool.description, str)
        assert len(tool.description) > 0

        assert isinstance(tool.input_schema, dict)
        assert "properties" in tool.input_schema

        assert isinstance(tool.required_scopes, list)
        assert len(tool.required_scopes) > 0

        assert callable(tool.handle)

    def test_cluster_raw_thoughts_has_widget_uri(self):
        """cluster_raw_thoughts should have a widget_uri (produces widget)."""
        tool = get_tool("cluster_raw_thoughts")
        assert tool is not None
        assert tool.widget_uri is not None
        assert "clarity-clusters" in tool.widget_uri

    def test_cluster_raw_thoughts_requires_clarity_write_scope(self):
        """cluster_raw_thoughts should require clarity.write scope."""
        tool = get_tool("cluster_raw_thoughts")
        assert tool is not None
        assert "clarity.write" in tool.required_scopes


class TestRegisterTool:
    """Tests for the register_tool function."""

    def test_register_new_tool(self):
        """Should be able to register a new tool."""
        # Create a dummy tool
        async def dummy_handle(user_id, correlation_id, arguments):
            return {"result": "ok"}

        dummy_tool = ToolDefinition(
            name="test_dummy_tool",
            description="A test tool",
            input_schema={"type": "object"},
            required_scopes=["test.scope"],
            widget_uri=None,
            handle=dummy_handle,
        )

        # Register it
        register_tool(dummy_tool)

        # Verify it's in the registry
        retrieved = get_tool("test_dummy_tool")
        assert retrieved is not None
        assert retrieved.name == "test_dummy_tool"
        assert retrieved.description == "A test tool"

        # Clean up (remove from registry)
        del TOOL_REGISTRY["test_dummy_tool"]
