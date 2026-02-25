"""
Integration tests for inspect_adapt MCP tool (Increment 30).

Tests:
- Tool registration in TOOL_REGISTRY
- Tool appears in list_tools() output
- Full flow: call with valid data
"""

import pytest

from mcp_server.priority_guardian.tools import (
    TOOL_REGISTRY,
    list_tools,
)
from mcp_server.priority_guardian.tools.inspect_adapt import (
    INSPECT_ADAPT,
    handle,
    GUIDANCE_COMMIT_SUCCESS,
)


class TestToolRegistration:
    """Tests for tool registration."""

    def test_tool_registered(self):
        """INSPECT_ADAPT appears in TOOL_REGISTRY."""
        assert "inspect_adapt" in TOOL_REGISTRY
        assert TOOL_REGISTRY["inspect_adapt"] is INSPECT_ADAPT

    @pytest.mark.asyncio
    async def test_tool_listed(self):
        """inspect_adapt appears in list_tools() output with correct metadata."""
        tools = await list_tools()

        # Find inspect_adapt in the list
        inspect_adapt_tool = None
        for tool in tools:
            if tool.name == "inspect_adapt":
                inspect_adapt_tool = tool
                break

        assert inspect_adapt_tool is not None, "inspect_adapt not found in list_tools()"

        # Check description contains key phrases
        assert "inspect & adapt" in inspect_adapt_tool.description.lower()
        assert "action steps" in inspect_adapt_tool.description.lower()

        # Check input schema has required properties (no phase anymore)
        assert "reflection_items" in inspect_adapt_tool.inputSchema["properties"]
        assert "action_steps" in inspect_adapt_tool.inputSchema["properties"]
        assert "user_confirmed" in inspect_adapt_tool.inputSchema["properties"]

        # Verify phase is NOT in schema (single-call tool)
        assert "phase" not in inspect_adapt_tool.inputSchema["properties"]

        # Check meta has correct structure (Tool model uses 'meta' attribute)
        tool_meta = getattr(inspect_adapt_tool, "meta", None) or getattr(inspect_adapt_tool, "_meta", None)
        assert tool_meta is not None
        assert "annotations" in tool_meta
        assert tool_meta["annotations"]["readOnlyHint"] is True
        assert tool_meta["annotations"]["destructiveHint"] is False

        # Check invocation messages are present
        assert "openai/toolInvocation/invoking" in tool_meta
        assert "openai/toolInvocation/invoked" in tool_meta

    def test_tool_has_required_scopes(self):
        """inspect_adapt requires pg.access scope."""
        assert INSPECT_ADAPT.required_scopes == ["pg.access"]

    def test_tool_has_no_widget(self):
        """inspect_adapt has no widget_uri (LLM narrates conversationally)."""
        assert INSPECT_ADAPT.widget_uri is None
        assert INSPECT_ADAPT.widget_accessible is False


class TestFullFlow:
    """Tests for full flow."""

    @pytest.mark.asyncio
    async def test_full_flow(self):
        """Call with valid data including proper id linkage, succeeds."""
        user_id = "test-user-123"
        correlation_id = "corr-789"

        args = {
            "reflection_items": [
                {
                    "id": "r1",
                    "user_reflection_verbatim": "I blocked the first 2 hours of every morning for P1 work",
                    "description": "Morning 2-hour block dedicated to P1",
                    "lens": "helped",
                },
                {
                    "id": "r2",
                    "user_reflection_verbatim": "I kept skipping Spanish because evenings were too packed",
                    "description": "Evening schedule too busy for Spanish practice",
                    "lens": "hindered",
                },
            ],
            "action_steps": [
                {
                    "user_action_verbatim": "I'll keep the morning block, it's working",
                    "action": "Continue morning 2-hour P1 block",
                    "derived_from_id": "r1",
                },
                {
                    "user_action_verbatim": "I'll try 20 minutes at lunch instead of evenings",
                    "action": "Move Spanish practice to 20-minute lunch slot",
                    "derived_from_id": "r2",
                },
            ],
            "user_confirmed": True,
        }

        result = await handle(user_id, correlation_id, args)

        assert result.isError is not True
        assert result.structuredContent["success"] is True
        assert result.structuredContent["completed"] is True
        assert result.structuredContent["assistant_guidance"] == GUIDANCE_COMMIT_SUCCESS
        assert "2 action step(s) confirmed" in result.content[0].text

        # Verify the data was passed through
        assert len(result.structuredContent["reflection_items"]) == 2
        assert len(result.structuredContent["action_steps"]) == 2

        # Verify id linkage is preserved
        action_step_ids = [s["derived_from_id"] for s in result.structuredContent["action_steps"]]
        assert "r1" in action_step_ids
        assert "r2" in action_step_ids
