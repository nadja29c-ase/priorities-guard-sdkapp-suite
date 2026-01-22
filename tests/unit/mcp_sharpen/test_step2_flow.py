"""
Integration tests for Step 2 tool flow.

Tests tool registration, annotations, and schema requirements.
"""

import pytest


# ============================================================================
# Tool Registration Tests
# ============================================================================


class TestToolRegistration:
    """Tests for Step 2 tool registration and discovery."""

    def test_tool_2_1_listed_in_registry(self):
        """identify_e2e_deliverables is registered in tool registry."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        assert "identify_e2e_deliverables" in TOOL_REGISTRY

    def test_tool_2_2_listed_in_registry(self):
        """select_focus_deliverable is registered in tool registry."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        assert "select_focus_deliverable" in TOOL_REGISTRY


# ============================================================================
# Tool Annotation Tests
# ============================================================================


class TestToolAnnotations:
    """Tests for Step 2 tool compliance annotations."""

    def test_tool_2_1_has_correct_annotations(self):
        """identify_e2e_deliverables has correct compliance annotations."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["identify_e2e_deliverables"]
        assert tool.read_only_hint is False
        assert tool.destructive_hint is False
        assert tool.open_world_hint is False

    def test_tool_2_2_has_correct_annotations(self):
        """select_focus_deliverable has correct compliance annotations."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["select_focus_deliverable"]
        assert tool.read_only_hint is False
        assert tool.destructive_hint is False
        assert tool.open_world_hint is False

    def test_step_2_tools_are_closed_world(self):
        """Step 2 tools are closed-world (no external API calls).

        Sharpen is a closed reasoning system. This invariant test
        encodes that architectural intent and catches regressions.
        """
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        step_2_tools = ["identify_e2e_deliverables", "select_focus_deliverable"]
        for name in step_2_tools:
            tool = TOOL_REGISTRY[name]
            assert tool.open_world_hint is False, f"{name} must be closed-world"


# ============================================================================
# Input Schema Tests
# ============================================================================


class TestInputSchemaRequirements:
    """Tests for Step 2 tool input schema required fields."""

    def test_tool_2_1_input_schema_requires_initiative_framing(self):
        """identify_e2e_deliverables schema requires initiative_framing."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["identify_e2e_deliverables"]
        required = tool.input_schema.get("required", [])
        assert "initiative_framing" in required

    def test_tool_2_1_input_schema_requires_confidence(self):
        """identify_e2e_deliverables schema requires confidence."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["identify_e2e_deliverables"]
        required = tool.input_schema.get("required", [])
        assert "confidence" in required

    def test_tool_2_1_input_schema_requires_candidate_deliverables(self):
        """identify_e2e_deliverables schema requires candidate_deliverables."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["identify_e2e_deliverables"]
        required = tool.input_schema.get("required", [])
        assert "candidate_deliverables" in required

    def test_tool_2_2_input_schema_requires_confirmed_deliverables(self):
        """select_focus_deliverable schema requires confirmed_deliverables."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["select_focus_deliverable"]
        required = tool.input_schema.get("required", [])
        assert "confirmed_deliverables" in required

    def test_tool_2_2_input_schema_has_selection_methods(self):
        """select_focus_deliverable schema has both selection methods (optional, mutually exclusive)."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["select_focus_deliverable"]
        properties = tool.input_schema.get("properties", {})
        # Both methods available but neither required (mutual exclusivity enforced at runtime)
        assert "selected_deliverable_name" in properties
        assert "sculpted_deliverable" in properties

    def test_tool_2_2_input_schema_requires_initiative_framing(self):
        """select_focus_deliverable schema requires initiative_framing."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["select_focus_deliverable"]
        required = tool.input_schema.get("required", [])
        assert "initiative_framing" in required

    def test_tool_2_2_input_schema_requires_confidence(self):
        """select_focus_deliverable schema requires confidence."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["select_focus_deliverable"]
        required = tool.input_schema.get("required", [])
        assert "confidence" in required


# ============================================================================
# Tool Description Tests
# ============================================================================


class TestToolDescriptions:
    """Tests for Step 2 tool descriptions enforcing facilitator role."""

    def test_tool_2_1_description_includes_critical_role(self):
        """identify_e2e_deliverables description includes CRITICAL role guidance."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["identify_e2e_deliverables"]
        assert "CRITICAL" in tool.description

    def test_tool_2_1_description_includes_confidence_examples(self):
        """identify_e2e_deliverables description includes CONFIDENCE EXAMPLES."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["identify_e2e_deliverables"]
        assert "CONFIDENCE EXAMPLES" in tool.description

    def test_tool_2_1_description_includes_sharpen_mode(self):
        """identify_e2e_deliverables description includes SHARPEN MODE rules."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["identify_e2e_deliverables"]
        assert "SHARPEN MODE" in tool.description

    def test_tool_2_2_description_includes_critical_role(self):
        """select_focus_deliverable description includes CRITICAL role guidance."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["select_focus_deliverable"]
        assert "CRITICAL" in tool.description

    def test_tool_2_2_description_includes_sharpen_mode(self):
        """select_focus_deliverable description includes SHARPEN MODE rules."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["select_focus_deliverable"]
        assert "SHARPEN MODE" in tool.description

    def test_tool_2_2_description_includes_example_conversation(self):
        """select_focus_deliverable description includes EXAMPLE CONVERSATION."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["select_focus_deliverable"]
        assert "EXAMPLE CONVERSATION" in tool.description
