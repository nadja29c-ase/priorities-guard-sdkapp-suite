"""
Tests for frame_initiative_constraints tool.

Tests both pure logic (tool_logic.py) and handler (tools/frame_initiative_constraints.py).
"""

import pytest

from mcp_server.sharpen.tool_logic import validate_initiative_constraints
from mcp_server.sharpen.tools.frame_initiative_constraints import handle


# ============================================================================
# Pure Logic Tests (tool_logic.py)
# ============================================================================


class TestValidateInitiativeConstraints:
    """Tests for validate_initiative_constraints function."""

    def test_valid_constraint_and_finished_returns_high_confidence(self):
        """Valid constraint and definition of finished returns high confidence."""
        result = validate_initiative_constraints(
            confirmed_intent={"who": "My team", "what": "A dashboard"},
            constraint_type="time",
            constraint_value="by end of Q1",
            definition_of_finished="Dashboard deployed and team trained",
        )

        assert result["confidence"] == "high"
        assert result["needs_clarification"] is False
        assert result["force_constraint"] is False

    def test_missing_confirmed_intent_returns_intent_missing(self):
        """Missing confirmed_intent returns intent_missing=True."""
        result = validate_initiative_constraints(
            confirmed_intent=None,
            constraint_type="time",
            constraint_value="by Friday",
            definition_of_finished="Done",
        )

        assert result["intent_missing"] is True
        assert result["initiative_framing"] is None

    def test_empty_confirmed_intent_who_returns_intent_missing(self):
        """Empty WHO in confirmed_intent returns intent_missing=True."""
        result = validate_initiative_constraints(
            confirmed_intent={"who": "", "what": "something"},
            constraint_type="time",
            constraint_value="by Friday",
            definition_of_finished="Done",
        )

        assert result["intent_missing"] is True

    def test_empty_confirmed_intent_what_returns_intent_missing(self):
        """Empty WHAT in confirmed_intent returns intent_missing=True."""
        result = validate_initiative_constraints(
            confirmed_intent={"who": "My team", "what": ""},
            constraint_type="time",
            constraint_value="by Friday",
            definition_of_finished="Done",
        )

        assert result["intent_missing"] is True

    def test_user_claims_no_constraints_returns_force_constraint(self):
        """user_claims_no_constraints=True returns force_constraint=True, framing=None."""
        result = validate_initiative_constraints(
            confirmed_intent={"who": "My team", "what": "A dashboard"},
            user_claims_no_constraints=True,
        )

        assert result["force_constraint"] is True
        assert result["confidence"] == "low"
        assert result["initiative_framing"] is None  # Framing NOT finalized

    def test_empty_constraint_value_returns_low_confidence(self):
        """Empty constraint_value returns low confidence, clarify CONSTRAINT."""
        result = validate_initiative_constraints(
            confirmed_intent={"who": "My team", "what": "A dashboard"},
            constraint_type="time",
            constraint_value="",
            definition_of_finished="Dashboard live",
        )

        assert result["confidence"] == "low"
        assert result["needs_clarification"] is True
        assert result["clarify_type"] == "CONSTRAINT"

    def test_vague_constraint_value_returns_medium_confidence(self):
        """Vague constraint_value like 'soon' returns medium confidence."""
        result = validate_initiative_constraints(
            confirmed_intent={"who": "My team", "what": "A dashboard"},
            constraint_type="time",
            constraint_value="soon",
            definition_of_finished="Dashboard live and team using it",
        )

        assert result["confidence"] == "medium"
        assert result["needs_clarification"] is True
        assert result["clarify_type"] == "CONSTRAINT"

    def test_empty_definition_of_finished_returns_low_confidence(self):
        """Empty definition_of_finished returns low confidence, clarify FINISHED."""
        result = validate_initiative_constraints(
            confirmed_intent={"who": "My team", "what": "A dashboard"},
            constraint_type="time",
            constraint_value="by Friday",
            definition_of_finished="",
        )

        assert result["confidence"] == "low"
        assert result["needs_clarification"] is True
        assert result["clarify_type"] == "FINISHED"

    def test_vague_definition_of_finished_returns_medium_confidence(self):
        """Vague definition_of_finished like 'done' returns medium confidence."""
        result = validate_initiative_constraints(
            confirmed_intent={"who": "My team", "what": "A dashboard"},
            constraint_type="time",
            constraint_value="by end of month",
            definition_of_finished="when it's done",
        )

        assert result["confidence"] == "medium"
        assert result["needs_clarification"] is True
        assert result["clarify_type"] == "FINISHED"

    def test_initiative_framing_merges_intent_and_constraints(self):
        """initiative_framing contains all fields from intent plus constraints."""
        result = validate_initiative_constraints(
            confirmed_intent={"who": "Marketing", "what": "Campaign tracker", "why": "to measure ROI"},
            constraint_type="budget",
            constraint_value="$5000 max",
            definition_of_finished="Tracker shows live campaign metrics",
        )

        framing = result["initiative_framing"]
        assert framing["who"] == "Marketing"
        assert framing["what"] == "Campaign tracker"
        assert framing["why"] == "to measure ROI"
        assert framing["constraint_type"] == "budget"
        assert framing["constraint_value"] == "$5000 max"
        assert framing["definition_of_finished"] == "Tracker shows live campaign metrics"

    def test_missing_constraint_type_returns_low_confidence(self):
        """Missing constraint_type returns low confidence."""
        result = validate_initiative_constraints(
            confirmed_intent={"who": "My team", "what": "A dashboard"},
            constraint_type=None,
            constraint_value="by Friday",
            definition_of_finished="Dashboard deployed",
        )

        assert result["confidence"] == "low"
        assert result["clarify_type"] == "CONSTRAINT"

    def test_forced_mvp_constraint_type_accepted(self):
        """forced_mvp is a valid constraint_type."""
        result = validate_initiative_constraints(
            confirmed_intent={"who": "My team", "what": "A dashboard"},
            constraint_type="forced_mvp",
            constraint_value="A single chart showing key metric",
            definition_of_finished="Chart visible on homepage",
        )

        assert result["confidence"] == "high"
        assert result["initiative_framing"]["constraint_type"] == "forced_mvp"


# ============================================================================
# Handler Tests (tools/frame_initiative_constraints.py)
# ============================================================================


class TestFrameInitiativeConstraintsHandler:
    """Tests for the MCP tool handler."""

    @pytest.mark.asyncio
    async def test_valid_input_returns_confirm_framing_complete(self):
        """Valid input returns CONFIRM_FRAMING_COMPLETE action."""
        arguments = {
            "confirmed_intent": {"who": "My team", "what": "A dashboard"},
            "constraint_type": "time",
            "constraint_value": "by end of Q1",
            "definition_of_finished": "Dashboard deployed and team trained",
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert result.structuredContent["assistant_guidance"]["action"] == "CONFIRM_FRAMING_COMPLETE"

    @pytest.mark.asyncio
    async def test_force_constraint_returns_force_constraint_action(self):
        """user_claims_no_constraints returns FORCE_CONSTRAINT action, framing=None."""
        arguments = {
            "confirmed_intent": {"who": "My team", "what": "A dashboard"},
            "user_claims_no_constraints": True,
        }

        result = await handle(arguments)

        assert result.structuredContent["assistant_guidance"]["action"] == "FORCE_CONSTRAINT"
        assert result.structuredContent["force_constraint"] is True
        assert result.structuredContent["initiative_framing"] is None  # Framing NOT finalized

    @pytest.mark.asyncio
    async def test_missing_confirmed_intent_returns_error(self):
        """Missing confirmed_intent returns isError=True."""
        arguments = {
            "constraint_type": "time",
            "constraint_value": "by Friday",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert "intent_missing" in str(result.structuredContent.get("error", ""))

    @pytest.mark.asyncio
    async def test_clarify_object_present_when_needed(self):
        """clarify object is present when needs_clarification is true."""
        arguments = {
            "confirmed_intent": {"who": "My team", "what": "A dashboard"},
            "constraint_type": "time",
            "constraint_value": "",
            "definition_of_finished": "Done",
        }

        result = await handle(arguments)

        assert "clarify" in result.structuredContent
        assert result.structuredContent["clarify"]["type"] == "CONSTRAINT"

    @pytest.mark.asyncio
    async def test_guidance_instruction_enforces_facilitator_role(self):
        """Guidance instructions enforce facilitator role."""
        arguments = {
            "confirmed_intent": {"who": "My team", "what": "A dashboard"},
            "user_claims_no_constraints": True,
        }

        result = await handle(arguments)

        instruction = result.structuredContent["assistant_guidance"]["instruction"]
        assert "do not suggest" in instruction.lower()

    @pytest.mark.asyncio
    async def test_empty_confirmed_intent_returns_error(self):
        """Empty confirmed_intent (empty who) returns isError=True."""
        arguments = {
            "confirmed_intent": {"who": "", "what": "A dashboard"},
            "constraint_type": "time",
            "constraint_value": "by Friday",
            "definition_of_finished": "Done",
        }

        result = await handle(arguments)

        assert result.isError is True


# ============================================================================
# Integration Tests (Tool Registration)
# ============================================================================


class TestToolRegistration:
    """Tests for tool registration and discovery."""

    def test_frame_initiative_intent_in_registry(self):
        """frame_initiative_intent is registered in tool registry."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        assert "frame_initiative_intent" in TOOL_REGISTRY

    def test_frame_initiative_constraints_in_registry(self):
        """frame_initiative_constraints is registered in tool registry."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        assert "frame_initiative_constraints" in TOOL_REGISTRY

    def test_tools_have_correct_annotations(self):
        """Both tools have correct compliance annotations."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        for tool_name in ["frame_initiative_intent", "frame_initiative_constraints"]:
            tool = TOOL_REGISTRY[tool_name]
            assert tool.read_only_hint is False
            assert tool.destructive_hint is False
            assert tool.open_world_hint is False

    def test_constraints_tool_requires_confirmed_intent(self):
        """frame_initiative_constraints input schema requires confirmed_intent."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["frame_initiative_constraints"]
        required = tool.input_schema.get("required", [])
        assert "confirmed_intent" in required
