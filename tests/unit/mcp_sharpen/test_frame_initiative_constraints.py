"""
Tests for frame_initiative_constraints tool.

Tests both pure logic (tool_logic.py) and handler (tools/frame_initiative_constraints.py).
Structural validation only — semantic quality is the LLM's job.
"""

import pytest

from mcp_server.sharpen.tool_logic import validate_initiative_constraints
from mcp_server.sharpen.tools.frame_initiative_constraints import handle


# ============================================================================
# Pure Logic Tests (tool_logic.py)
# ============================================================================


class TestValidateInitiativeConstraints:
    """Tests for validate_initiative_constraints function — structural validation only."""

    def test_valid_constraint_and_finished_returns_valid_true(self):
        """Valid constraint and definition of finished returns valid=True."""
        result = validate_initiative_constraints(
            confirmed_intent={"who": "My team", "what": "A dashboard"},
            constraint_type="time",
            constraint_value="by end of Q1",
            definition_of_finished="Dashboard deployed and team trained",
        )

        assert result["valid"] is True
        assert result["missing"] == []
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
        assert result["valid"] is False
        assert result["initiative_framing"] is None  # Framing NOT finalized

    def test_missing_constraint_type_returns_valid_false(self):
        """Missing constraint_type returns valid=False."""
        result = validate_initiative_constraints(
            confirmed_intent={"who": "My team", "what": "A dashboard"},
            constraint_type=None,
            constraint_value="by Friday",
            definition_of_finished="Dashboard deployed",
        )

        assert result["valid"] is False
        assert "constraint_type" in result["missing"]

    def test_missing_constraint_value_returns_valid_false(self):
        """Missing constraint_value returns valid=False."""
        result = validate_initiative_constraints(
            confirmed_intent={"who": "My team", "what": "A dashboard"},
            constraint_type="time",
            constraint_value="",
            definition_of_finished="Dashboard live",
        )

        assert result["valid"] is False
        assert "constraint_value" in result["missing"]

    def test_missing_definition_of_finished_returns_valid_false(self):
        """Missing definition_of_finished returns valid=False."""
        result = validate_initiative_constraints(
            confirmed_intent={"who": "My team", "what": "A dashboard"},
            constraint_type="time",
            constraint_value="by Friday",
            definition_of_finished="",
        )

        assert result["valid"] is False
        assert "definition_of_finished" in result["missing"]

    def test_all_fields_missing_returns_all_missing(self):
        """All constraint fields missing returns all in missing list."""
        result = validate_initiative_constraints(
            confirmed_intent={"who": "My team", "what": "A dashboard"},
            constraint_type=None,
            constraint_value=None,
            definition_of_finished=None,
        )

        assert result["valid"] is False
        assert "constraint_type" in result["missing"]
        assert "constraint_value" in result["missing"]
        assert "definition_of_finished" in result["missing"]

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

    def test_forced_mvp_constraint_type_accepted(self):
        """forced_mvp is a valid constraint_type."""
        result = validate_initiative_constraints(
            confirmed_intent={"who": "My team", "what": "A dashboard"},
            constraint_type="forced_mvp",
            constraint_value="A single chart showing key metric",
            definition_of_finished="Chart visible on homepage",
        )

        assert result["valid"] is True
        assert result["initiative_framing"]["constraint_type"] == "forced_mvp"

    def test_whitespace_is_stripped(self):
        """Whitespace is stripped from constraint inputs."""
        result = validate_initiative_constraints(
            confirmed_intent={"who": "My team", "what": "A dashboard"},
            constraint_type="  time  ",
            constraint_value="  by Friday  ",
            definition_of_finished="  Dashboard live  ",
        )

        assert result["valid"] is True
        assert result["initiative_framing"]["constraint_type"] == "time"
        assert result["initiative_framing"]["constraint_value"] == "by Friday"
        assert result["initiative_framing"]["definition_of_finished"] == "Dashboard live"

    def test_whitespace_only_is_empty(self):
        """Whitespace-only inputs are treated as empty."""
        result = validate_initiative_constraints(
            confirmed_intent={"who": "My team", "what": "A dashboard"},
            constraint_type="time",
            constraint_value="   ",
            definition_of_finished="Dashboard live",
        )

        assert result["valid"] is False
        assert "constraint_value" in result["missing"]


# ============================================================================
# Handler Tests (tools/frame_initiative_constraints.py)
# ============================================================================


class TestFrameInitiativeConstraintsHandler:
    """Tests for the MCP tool handler."""

    @pytest.mark.asyncio
    async def test_valid_input_returns_confirmed_true(self):
        """Valid input returns confirmed=True."""
        arguments = {
            "confirmed_intent": {"who": "My team", "what": "A dashboard"},
            "constraint_type": "time",
            "constraint_value": "by end of Q1",
            "definition_of_finished": "Dashboard deployed and team trained",
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert result.structuredContent["confirmed"] is True

    @pytest.mark.asyncio
    async def test_valid_input_includes_initiative_framing(self):
        """Valid input includes initiative_framing in structuredContent."""
        arguments = {
            "confirmed_intent": {"who": "My team", "what": "A dashboard"},
            "constraint_type": "capacity",
            "constraint_value": "4 hours per week",
            "definition_of_finished": "Dashboard shows key metrics",
        }

        result = await handle(arguments)

        assert "initiative_framing" in result.structuredContent
        framing = result.structuredContent["initiative_framing"]
        assert framing["who"] == "My team"
        assert framing["constraint_type"] == "capacity"

    @pytest.mark.asyncio
    async def test_force_constraint_returns_force_constraint_true(self):
        """user_claims_no_constraints returns force_constraint=True, no error."""
        arguments = {
            "confirmed_intent": {"who": "My team", "what": "A dashboard"},
            "user_claims_no_constraints": True,
        }

        result = await handle(arguments)

        assert result.isError is not True  # Not an error, just needs clarification
        assert result.structuredContent["force_constraint"] is True

    @pytest.mark.asyncio
    async def test_missing_confirmed_intent_returns_error(self):
        """Missing confirmed_intent returns isError=True."""
        arguments = {
            "constraint_type": "time",
            "constraint_value": "by Friday",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "intent_missing"

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
        assert result.structuredContent["error"] == "intent_missing"

    @pytest.mark.asyncio
    async def test_missing_constraint_fields_returns_error(self):
        """Missing constraint fields returns isError=True with missing list."""
        arguments = {
            "confirmed_intent": {"who": "My team", "what": "A dashboard"},
            "constraint_type": "time",
            "constraint_value": "",
            "definition_of_finished": "Done",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "missing_fields"
        assert "constraint_value" in result.structuredContent["missing"]

    @pytest.mark.asyncio
    async def test_missing_fields_includes_partial_framing(self):
        """Missing fields response includes partial initiative_framing."""
        arguments = {
            "confirmed_intent": {"who": "My team", "what": "A dashboard"},
            "constraint_type": "time",
            "constraint_value": "by Friday",
            "definition_of_finished": "",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert "initiative_framing" in result.structuredContent
        assert result.structuredContent["initiative_framing"]["constraint_type"] == "time"

    @pytest.mark.asyncio
    async def test_guidance_instruction_present(self):
        """assistant_guidance with instruction is always present."""
        arguments = {
            "confirmed_intent": {"who": "My team", "what": "A dashboard"},
            "constraint_type": "time",
            "constraint_value": "by end of Q1",
            "definition_of_finished": "Dashboard deployed",
        }

        result = await handle(arguments)

        assert "assistant_guidance" in result.structuredContent
        assert "instruction" in result.structuredContent["assistant_guidance"]

    @pytest.mark.asyncio
    async def test_guidance_instruction_for_force_constraint(self):
        """Guidance instruction for force_constraint enforces facilitator role."""
        arguments = {
            "confirmed_intent": {"who": "My team", "what": "A dashboard"},
            "user_claims_no_constraints": True,
        }

        result = await handle(arguments)

        instruction = result.structuredContent["assistant_guidance"]["instruction"]
        assert "do not suggest" in instruction.lower()
        assert "forced_mvp" in instruction

    @pytest.mark.asyncio
    async def test_guidance_instruction_for_missing_fields(self):
        """Guidance instruction for missing fields enforces facilitator role."""
        arguments = {
            "confirmed_intent": {"who": "My team", "what": "A dashboard"},
            "constraint_type": "time",
            "constraint_value": "",
            "definition_of_finished": "",
        }

        result = await handle(arguments)

        instruction = result.structuredContent["assistant_guidance"]["instruction"]
        assert "Do not suggest" in instruction

    @pytest.mark.asyncio
    async def test_text_content_for_valid_input(self):
        """Valid input returns human-readable text content."""
        arguments = {
            "confirmed_intent": {"who": "My team", "what": "A dashboard"},
            "constraint_type": "time",
            "constraint_value": "by Friday",
            "definition_of_finished": "Dashboard live",
        }

        result = await handle(arguments)

        assert len(result.content) == 1
        assert "Framing complete" in result.content[0].text
        assert "My team" in result.content[0].text


# ============================================================================
# Integration Tests (Tool Registration)
# ============================================================================


class TestToolRegistration:
    """Tests for tool registration and discovery."""

    def test_frame_initiative_constraints_in_registry(self):
        """frame_initiative_constraints is registered in tool registry."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        assert "frame_initiative_constraints" in TOOL_REGISTRY

    def test_tool_has_correct_annotations(self):
        """Tool has correct compliance annotations."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["frame_initiative_constraints"]
        assert tool.read_only_hint is False
        assert tool.destructive_hint is False
        assert tool.open_world_hint is False

    def test_tool_description_includes_facilitator_role(self):
        """Tool description includes FACILITATOR ROLE guidance."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["frame_initiative_constraints"]
        assert "FACILITATOR ROLE" in tool.description

    def test_tool_description_includes_call_criteria(self):
        """Tool description includes CALL ONLY WHEN criteria."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["frame_initiative_constraints"]
        assert "CALL ONLY WHEN" in tool.description

    def test_tool_description_includes_no_constraints_case(self):
        """Tool description includes NO CONSTRAINTS CLAIMED special case."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["frame_initiative_constraints"]
        assert "NO CONSTRAINTS CLAIMED" in tool.description

    def test_constraints_tool_requires_confirmed_intent(self):
        """frame_initiative_constraints input schema requires confirmed_intent."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["frame_initiative_constraints"]
        required = tool.input_schema.get("required", [])
        assert "confirmed_intent" in required
