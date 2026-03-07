"""
Unit tests for list_tools() in Priority Guardian MCP server.

Tests Increment 47: ToolAnnotations must be proper typed object, not dict.
"""

import pytest
from mcp import types as mcp_types


@pytest.mark.asyncio
async def test_list_tools_annotations_are_tool_annotations_type():
    """
    All returned Tools must have annotations as ToolAnnotations instance, not dict.
    """
    from mcp_server.priority_guardian.tools import list_tools

    tools = await list_tools()

    assert len(tools) > 0, "Expected at least one tool"

    for tool in tools:
        assert isinstance(tool.annotations, mcp_types.ToolAnnotations), (
            f"Tool '{tool.name}' annotations should be ToolAnnotations, "
            f"got {type(tool.annotations)}"
        )


@pytest.mark.asyncio
async def test_list_tools_meta_does_not_contain_annotations():
    """
    The _meta dict should NOT contain 'annotations' key (annotations belong at Tool level).
    """
    from mcp_server.priority_guardian.tools import list_tools

    tools = await list_tools()

    for tool in tools:
        meta = getattr(tool, "_meta", {}) or {}
        assert "annotations" not in meta, (
            f"Tool '{tool.name}' _meta should not contain 'annotations' key"
        )


@pytest.mark.asyncio
async def test_list_tools_annotations_match_tool_definitions():
    """
    Tool.annotations fields should match values declared on ToolDefinition.
    """
    from mcp_server.priority_guardian.tools import list_tools, TOOL_REGISTRY

    tools = await list_tools()

    for tool in tools:
        tool_def = TOOL_REGISTRY.get(tool.name)
        assert tool_def is not None, f"Tool '{tool.name}' not found in registry"

        assert tool.annotations.readOnlyHint == tool_def.read_only_hint, (
            f"Tool '{tool.name}' readOnlyHint mismatch: "
            f"expected {tool_def.read_only_hint}, got {tool.annotations.readOnlyHint}"
        )
        assert tool.annotations.destructiveHint == tool_def.destructive_hint, (
            f"Tool '{tool.name}' destructiveHint mismatch: "
            f"expected {tool_def.destructive_hint}, got {tool.annotations.destructiveHint}"
        )
        assert tool.annotations.openWorldHint == tool_def.open_world_hint, (
            f"Tool '{tool.name}' openWorldHint mismatch: "
            f"expected {tool_def.open_world_hint}, got {tool.annotations.openWorldHint}"
        )
