"""
Unit tests for Priority Guardian tool registry.

Tests the explicit TOOL_REGISTRY pattern:
- All expected tools are registered
- No duplicate names
- Each tool has required ToolDefinition fields
- list_tools returns proper MCP Tool format
"""

import pytest
from mcp import types as mcp_types


class TestToolRegistry:
    """Tests for TOOL_REGISTRY."""

    def test_all_expected_tools_present(self):
        """All expected tools are present in TOOL_REGISTRY."""
        from mcp_server.priority_guardian.tools import TOOL_REGISTRY

        # 7 public tools + 11 private tools = 18 total
        expected_tools = {
            # Public tools (7)
            "create_priority",
            "get_priorities",
            "render_weekly_report",
            "get_priority_events",
            "get_patterns",
            "onboarding_calendar_setup",
            "inspect_adapt",
            # Private widget tools (11)
            "connect_google_calendar",
            "disconnect_google_calendar",
            "add_priority",
            "update_priority",
            "delete_priority",
            "add_deliverable",
            "update_deliverable",
            "delete_deliverable",
            "add_goal",
            "update_goal",
            "delete_goal",
        }

        assert set(TOOL_REGISTRY.keys()) == expected_tools

    def test_no_duplicate_names(self):
        """Registry keys match tool definition names."""
        from mcp_server.priority_guardian.tools import TOOL_REGISTRY

        for key, tool in TOOL_REGISTRY.items():
            assert key == tool.name, f"Key '{key}' doesn't match tool.name '{tool.name}'"

    def test_tool_definitions_have_required_fields(self):
        """Each tool has all required ToolDefinition fields."""
        from mcp_server.priority_guardian.tools import TOOL_REGISTRY

        for name, tool in TOOL_REGISTRY.items():
            # Required fields
            assert isinstance(tool.name, str), f"{name}: name must be str"
            assert len(tool.name) > 0, f"{name}: name must be non-empty"

            assert isinstance(tool.description, str), f"{name}: description must be str"
            assert len(tool.description) > 0, f"{name}: description must be non-empty"

            assert isinstance(tool.input_schema, dict), f"{name}: input_schema must be dict"

            assert isinstance(tool.required_scopes, list), f"{name}: required_scopes must be list"

            assert tool.widget_uri is None or isinstance(tool.widget_uri, str), \
                f"{name}: widget_uri must be str or None"

            assert callable(tool.handle), f"{name}: handle must be callable"

            # Annotation fields
            assert isinstance(tool.read_only_hint, bool), f"{name}: read_only_hint must be bool"
            assert isinstance(tool.destructive_hint, bool), f"{name}: destructive_hint must be bool"
            assert isinstance(tool.open_world_hint, bool), f"{name}: open_world_hint must be bool"

    def test_get_tool_returns_correct_tool(self):
        """get_tool returns the correct tool definition."""
        from mcp_server.priority_guardian.tools import get_tool

        tool = get_tool("create_priority")
        assert tool is not None
        assert tool.name == "create_priority"

    def test_get_tool_returns_none_for_unknown(self):
        """get_tool returns None for unknown tool names."""
        from mcp_server.priority_guardian.tools import get_tool

        tool = get_tool("nonexistent_tool")
        assert tool is None


class TestListTools:
    """Tests for list_tools function."""

    @pytest.mark.asyncio
    async def test_returns_list_of_mcp_tools(self):
        """list_tools returns list of mcp_types.Tool."""
        from mcp_server.priority_guardian.tools import list_tools

        tools = await list_tools()

        assert isinstance(tools, list)
        # 7 public tools + 11 private tools = 18 total
        assert len(tools) == 18

        for tool in tools:
            assert isinstance(tool, mcp_types.Tool)

    @pytest.mark.asyncio
    async def test_tools_sorted_by_name(self):
        """list_tools returns tools sorted alphabetically by name."""
        from mcp_server.priority_guardian.tools import list_tools

        tools = await list_tools()

        names = [t.name for t in tools]
        assert names == sorted(names)

    @pytest.mark.asyncio
    async def test_tools_have_annotations(self):
        """Each tool has ToolAnnotations object."""
        from mcp_server.priority_guardian.tools import list_tools
        from mcp import types as mcp_types

        tools = await list_tools()

        for tool in tools:
            # MCP library stores annotations directly on Tool object
            annotations = getattr(tool, 'annotations', None)
            assert annotations is not None, f"Tool {tool.name} has no annotations"
            assert isinstance(annotations, mcp_types.ToolAnnotations)
            # Check fields exist (they may be True or False)
            assert hasattr(annotations, 'readOnlyHint')
            assert hasattr(annotations, 'destructiveHint')
            assert hasattr(annotations, 'openWorldHint')

    @pytest.mark.asyncio
    async def test_tools_have_security_schemes(self):
        """Each tool has meta with securitySchemes."""
        from mcp_server.priority_guardian.tools import list_tools

        tools = await list_tools()

        for tool in tools:
            meta = getattr(tool, 'meta', None) or getattr(tool, '_meta', None)
            assert "securitySchemes" in meta
            schemes = meta["securitySchemes"]
            assert len(schemes) > 0
            # PG tools require oauth2
            assert schemes[0]["type"] == "oauth2"
            assert "scopes" in schemes[0]

    @pytest.mark.asyncio
    async def test_tools_have_input_schema(self):
        """Each tool has an inputSchema."""
        from mcp_server.priority_guardian.tools import list_tools

        tools = await list_tools()

        for tool in tools:
            assert tool.inputSchema is not None
            assert isinstance(tool.inputSchema, dict)


class TestToolAnnotations:
    """Tests for specific tool annotation values."""

    def test_connect_google_calendar_annotations(self):
        """connect_google_calendar has correct annotations."""
        from mcp_server.priority_guardian.tools import get_tool

        tool = get_tool("connect_google_calendar")
        assert tool.read_only_hint is False  # Initiates OAuth
        assert tool.destructive_hint is False
        assert tool.open_world_hint is True  # External Google OAuth

    def test_disconnect_google_calendar_annotations(self):
        """disconnect_google_calendar has correct annotations."""
        from mcp_server.priority_guardian.tools import get_tool

        tool = get_tool("disconnect_google_calendar")
        assert tool.read_only_hint is False  # Revokes tokens
        assert tool.destructive_hint is False  # Can reconnect anytime
        assert tool.open_world_hint is True  # External Google OAuth

    def test_create_priority_annotations(self):
        """create_priority has correct annotations."""
        from mcp_server.priority_guardian.tools import get_tool

        tool = get_tool("create_priority")
        assert tool.read_only_hint is False  # Creates data
        assert tool.destructive_hint is False
        assert tool.open_world_hint is False  # No external systems

    def test_render_weekly_report_annotations(self):
        """render_weekly_report has correct annotations."""
        from mcp_server.priority_guardian.tools import get_tool

        tool = get_tool("render_weekly_report")
        assert tool.read_only_hint is True  # Pure read after Inc 77 split
        assert tool.destructive_hint is False
        assert tool.open_world_hint is True  # Calls Google Calendar API

    def test_render_weekly_report_has_widget_uri(self):
        """render_weekly_report has widget_uri set."""
        from mcp_server.priority_guardian.tools import get_tool

        tool = get_tool("render_weekly_report")
        assert tool.widget_uri is not None
        assert tool.widget_uri == "ui://widget/pg-dashboard-v12.html"

    def test_render_weekly_report_widget_accessible(self):
        """render_weekly_report has widget_accessible=True."""
        from mcp_server.priority_guardian.tools import get_tool

        tool = get_tool("render_weekly_report")
        assert tool.widget_accessible is True

    def test_get_priority_events_annotations(self):
        """get_priority_events has correct annotations (data tool, no widget)."""
        from mcp_server.priority_guardian.tools import get_tool

        tool = get_tool("get_priority_events")
        assert tool.read_only_hint is True  # Data fetch only
        assert tool.destructive_hint is False
        assert tool.open_world_hint is True  # Calls Google Calendar API

    def test_get_priority_events_no_widget_uri(self):
        """get_priority_events has widget_uri=None (data tool)."""
        from mcp_server.priority_guardian.tools import get_tool

        tool = get_tool("get_priority_events")
        assert tool.widget_uri is None  # Critical: no widget for data tool

    def test_get_priority_events_widget_not_accessible(self):
        """get_priority_events has widget_accessible=False."""
        from mcp_server.priority_guardian.tools import get_tool

        tool = get_tool("get_priority_events")
        assert tool.widget_accessible is False
