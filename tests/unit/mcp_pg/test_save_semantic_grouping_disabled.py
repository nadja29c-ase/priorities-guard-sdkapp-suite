"""
Unit tests verifying save_semantic_grouping is disabled (Increment 06-S).

Verifies:
- save_semantic_grouping not in TOOL_REGISTRY
- save_semantic_grouping not in TOOL_INVOCATION_MESSAGES
- Tool file still exists on disk (for future persistence increment)
- list_tools does not include save_semantic_grouping
"""

import os
import pytest


class TestSaveSemanticGroupingDisabled:
    """Tests for save_semantic_grouping being disabled."""

    def test_not_in_tool_registry(self):
        """save_semantic_grouping is not in TOOL_REGISTRY."""
        from mcp_server.priority_guardian.tools import TOOL_REGISTRY

        assert "save_semantic_grouping" not in TOOL_REGISTRY

    def test_not_in_tool_invocation_messages(self):
        """save_semantic_grouping is not in TOOL_INVOCATION_MESSAGES."""
        from mcp_server.priority_guardian.tools import TOOL_INVOCATION_MESSAGES

        assert "save_semantic_grouping" not in TOOL_INVOCATION_MESSAGES

    def test_tool_file_still_exists_on_disk(self):
        """Tool file exists on disk for future persistence increment."""
        # Get the path to the tool file
        from mcp_server.priority_guardian import tools
        tools_dir = os.path.dirname(tools.__file__)
        tool_file = os.path.join(tools_dir, "save_semantic_grouping.py")

        assert os.path.exists(tool_file), (
            f"save_semantic_grouping.py should exist at {tool_file} "
            "for future persistence increment"
        )

    def test_tool_file_has_content(self):
        """Tool file has meaningful content (not empty)."""
        from mcp_server.priority_guardian import tools
        tools_dir = os.path.dirname(tools.__file__)
        tool_file = os.path.join(tools_dir, "save_semantic_grouping.py")

        with open(tool_file, "r") as f:
            content = f.read()

        # Should have the tool definition
        assert "SAVE_SEMANTIC_GROUPING" in content
        assert "ToolDefinition" in content
        assert "save_semantic_grouping" in content

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


class TestGetWeeklyReportStillRegistered:
    """Verify get_weekly_report is still properly registered."""

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

    def test_has_correct_widget_accessible_value(self):
        """get_weekly_report has widget_accessible=False with TODO comment."""
        from mcp_server.priority_guardian.tools import get_tool

        tool = get_tool("get_weekly_report")

        # Currently False in simplified version
        assert tool.widget_accessible is False

    def test_has_no_widget_uri(self):
        """get_weekly_report has widget_uri=None (conversational only)."""
        from mcp_server.priority_guardian.tools import get_tool

        tool = get_tool("get_weekly_report")

        assert tool.widget_uri is None
