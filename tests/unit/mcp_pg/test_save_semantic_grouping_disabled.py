"""
Unit tests verifying save_semantic_grouping is deleted (Increment 07).

Verifies:
- save_semantic_grouping NOT in TOOL_REGISTRY
- save_semantic_grouping NOT in TOOL_INVOCATION_MESSAGES
- Tool file does NOT exist on disk (deleted in Increment 07)
- list_tools does not include save_semantic_grouping
- get_weekly_report IS still registered with widget_uri and widget_accessible=True
"""

import os
import pytest


class TestSaveSemanticGroupingDeleted:
    """Tests for save_semantic_grouping being deleted."""

    def test_not_in_tool_registry(self):
        """save_semantic_grouping is not in TOOL_REGISTRY."""
        from mcp_server.priority_guardian.tools import TOOL_REGISTRY

        assert "save_semantic_grouping" not in TOOL_REGISTRY

    def test_not_in_tool_invocation_messages(self):
        """save_semantic_grouping is not in TOOL_INVOCATION_MESSAGES."""
        from mcp_server.priority_guardian.tools import TOOL_INVOCATION_MESSAGES

        assert "save_semantic_grouping" not in TOOL_INVOCATION_MESSAGES

    def test_tool_file_does_not_exist_on_disk(self):
        """Tool file has been deleted from disk."""
        from mcp_server.priority_guardian import tools
        tools_dir = os.path.dirname(tools.__file__)
        tool_file = os.path.join(tools_dir, "save_semantic_grouping.py")

        assert not os.path.exists(tool_file), (
            f"save_semantic_grouping.py should be deleted but exists at {tool_file}"
        )

    @pytest.mark.asyncio
    async def test_not_in_list_tools(self):
        """list_tools does not include save_semantic_grouping."""
        from mcp_server.priority_guardian.tools import list_tools

        tools = await list_tools()
        tool_names = [t.name for t in tools]

        assert "save_semantic_grouping" not in tool_names

    def test_get_tool_returns_none(self):
        """get_tool returns None for save_semantic_grouping."""
        from mcp_server.priority_guardian.tools import get_tool

        tool = get_tool("save_semantic_grouping")

        assert tool is None


class TestGetWeeklyReportRegistration:
    """Verify get_weekly_report is properly registered with widget support."""

    def test_in_tool_registry(self):
        """get_weekly_report is in TOOL_REGISTRY."""
        from mcp_server.priority_guardian.tools import TOOL_REGISTRY

        assert "get_weekly_report" in TOOL_REGISTRY

    def test_in_tool_invocation_messages(self):
        """get_weekly_report is in TOOL_INVOCATION_MESSAGES."""
        from mcp_server.priority_guardian.tools import TOOL_INVOCATION_MESSAGES

        assert "get_weekly_report" in TOOL_INVOCATION_MESSAGES

    @pytest.mark.asyncio
    async def test_in_list_tools(self):
        """list_tools includes get_weekly_report."""
        from mcp_server.priority_guardian.tools import list_tools

        tools = await list_tools()
        tool_names = [t.name for t in tools]

        assert "get_weekly_report" in tool_names

    def test_has_widget_uri(self):
        """get_weekly_report has widget_uri set (not None)."""
        from mcp_server.priority_guardian.tools import get_tool

        tool = get_tool("get_weekly_report")

        assert tool.widget_uri is not None
        assert tool.widget_uri == "ui://widget/pg-dashboard.html"

    def test_has_widget_accessible_true(self):
        """get_weekly_report has widget_accessible=True."""
        from mcp_server.priority_guardian.tools import get_tool

        tool = get_tool("get_weekly_report")

        assert tool.widget_accessible is True

    def test_has_semantic_groupings_in_schema(self):
        """get_weekly_report input schema includes semantic_groupings parameter."""
        from mcp_server.priority_guardian.tools import get_tool

        tool = get_tool("get_weekly_report")
        properties = tool.input_schema.get("properties", {})

        assert "semantic_groupings" in properties
        assert properties["semantic_groupings"]["type"] == "array"
