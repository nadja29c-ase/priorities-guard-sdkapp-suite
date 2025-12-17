"""
Unit tests for Clarity MCP tool registry.
"""

import pytest

from mcp_server.clarity.tools import TOOL_REGISTRY, get_tool, register_tool, list_tools
from mcp_server.clarity.tools.base import ToolDefinition


class TestToolRegistry:
    """Tests for tool registration and discovery."""

    def test_organize_thoughts_registered(self):
        """organize_thoughts tool should be in registry after import."""
        assert "organize_thoughts" in TOOL_REGISTRY

    def test_registry_returns_none_for_unknown(self):
        """get_tool should return None for unknown tool names."""
        result = get_tool("nonexistent_tool_that_does_not_exist")
        assert result is None

    def test_tool_definition_has_required_fields(self):
        """Tool definitions should have all required fields."""
        tool = get_tool("organize_thoughts")
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

    def test_organize_thoughts_has_widget_uri(self):
        """organize_thoughts should have a widget_uri (produces widget)."""
        tool = get_tool("organize_thoughts")
        assert tool is not None
        assert tool.widget_uri is not None
        assert "clarity-clusters" in tool.widget_uri

    def test_organize_thoughts_requires_clarity_write_scope(self):
        """organize_thoughts should require clarity.write scope."""
        tool = get_tool("organize_thoughts")
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


class TestSaveBoardRegistration:
    """Tests for save_board tool registration."""

    def test_save_board_registered(self):
        """save_board tool should be in registry."""
        assert "save_board" in TOOL_REGISTRY

    def test_save_board_widget_accessible(self):
        """save_board should be widget_accessible (for window.openai.callTool)."""
        tool = get_tool("save_board")
        assert tool is not None
        assert tool.widget_accessible is True

    def test_save_board_has_widget_uri(self):
        """save_board should have widget_uri (produces widget output)."""
        tool = get_tool("save_board")
        assert tool is not None
        assert tool.widget_uri is not None
        assert "clarity-clusters" in tool.widget_uri

    @pytest.mark.asyncio
    async def test_save_board_has_full_widget_meta(self):
        """save_board should have full widget meta including outputTemplate."""
        tools = await list_tools()
        save_board_tool = next((t for t in tools if t.name == "save_board"), None)
        assert save_board_tool is not None
        assert save_board_tool.meta is not None
        assert "openai/outputTemplate" in save_board_tool.meta
        assert save_board_tool.meta.get("openai/widgetAccessible") is True
        assert save_board_tool.meta.get("openai/resultCanProduceWidget") is True

    @pytest.mark.asyncio
    async def test_widget_producing_tools_have_full_meta(self):
        """Tools with widget_uri should have full meta including outputTemplate."""
        tools = await list_tools()
        organize_thoughts_tool = next((t for t in tools if t.name == "organize_thoughts"), None)
        assert organize_thoughts_tool is not None
        assert organize_thoughts_tool.meta is not None
        assert "openai/outputTemplate" in organize_thoughts_tool.meta
        assert organize_thoughts_tool.meta.get("openai/widgetAccessible") is True
        assert organize_thoughts_tool.meta.get("openai/resultCanProduceWidget") is True
