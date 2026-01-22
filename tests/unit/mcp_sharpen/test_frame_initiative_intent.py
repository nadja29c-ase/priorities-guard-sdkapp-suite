"""
Tests for frame_initiative_intent tool.

Tests both pure logic (tool_logic.py) and handler (tools/frame_initiative_intent.py).
Structural validation only — semantic quality is the LLM's job.

Note: WHAT is now captured separately in frame_initiative_hypothesis.
This tool only captures WHO and WHY.
"""

import pytest

from mcp_server.sharpen.tool_logic import validate_initiative_intent
from mcp_server.sharpen.tools.frame_initiative_intent import handle


# ============================================================================
# Pure Logic Tests (tool_logic.py)
# ============================================================================


class TestValidateInitiativeIntent:
    """Tests for validate_initiative_intent function — structural validation only."""

    def test_valid_who_why_returns_valid_true(self):
        """Valid WHO and WHY returns valid=True."""
        result = validate_initiative_intent(
            who="My team",
            why="So they can track progress",
        )

        assert result["valid"] is True
        assert result["missing"] == []

    def test_empty_who_returns_valid_false(self):
        """Empty WHO returns valid=False, missing=['who']."""
        result = validate_initiative_intent(
            who="",
            why="To track progress",
        )

        assert result["valid"] is False
        assert "who" in result["missing"]

    def test_none_who_returns_valid_false(self):
        """None WHO returns valid=False, missing=['who']."""
        result = validate_initiative_intent(
            who=None,
            why="To track progress",
        )

        assert result["valid"] is False
        assert "who" in result["missing"]

    def test_all_empty_returns_all_missing(self):
        """All empty returns valid=False, missing=['who', 'why']."""
        result = validate_initiative_intent(
            who="",
            why="",
        )

        assert result["valid"] is False
        assert "who" in result["missing"]
        assert "why" in result["missing"]

    def test_empty_why_returns_valid_false(self):
        """Empty WHY returns valid=False, missing=['why'] (WHY is mandatory)."""
        result = validate_initiative_intent(
            who="My team",
            why="",
        )

        assert result["valid"] is False
        assert "why" in result["missing"]

    def test_why_is_included_when_provided(self):
        """WHY is included in framing_intent when provided."""
        result = validate_initiative_intent(
            who="My team",
            why="so we can track progress",
        )

        assert result["framing_intent"]["why"] == "so we can track progress"
        assert result["valid"] is True

    def test_framing_intent_contains_who_and_why(self):
        """framing_intent contains who and why (no what)."""
        result = validate_initiative_intent(
            who="The marketing team",
            why="to measure ROI",
        )

        assert result["framing_intent"]["who"] == "The marketing team"
        assert result["framing_intent"]["why"] == "to measure ROI"
        assert "what" not in result["framing_intent"]

    def test_whitespace_is_stripped(self):
        """Leading/trailing whitespace is stripped from inputs."""
        result = validate_initiative_intent(
            who="  My team  ",
            why="  To track progress  ",
        )

        assert result["framing_intent"]["who"] == "My team"
        assert result["framing_intent"]["why"] == "To track progress"
        assert result["valid"] is True

    def test_whitespace_only_is_empty(self):
        """Whitespace-only inputs are treated as empty."""
        result = validate_initiative_intent(
            who="   ",
            why="To track progress",
        )

        assert result["valid"] is False
        assert "who" in result["missing"]

    def test_multiple_stakeholders_and_pattern(self):
        """WHO with 'and' returns multiple_stakeholders=True."""
        result = validate_initiative_intent(
            who="The team and the client",
            why="To track progress",
        )
        assert result["valid"] is False
        assert result["multiple_stakeholders"] is True

    def test_multiple_stakeholders_comma_pattern(self):
        """WHO with comma list returns multiple_stakeholders=True."""
        result = validate_initiative_intent(
            who="Engineers, designers, PMs",
            why="To track progress",
        )
        assert result["valid"] is False
        assert result["multiple_stakeholders"] is True

    def test_multiple_stakeholders_or_pattern(self):
        """WHO with 'or' returns multiple_stakeholders=True."""
        result = validate_initiative_intent(
            who="The client or leadership",
            why="To show progress",
        )
        assert result["valid"] is False
        assert result["multiple_stakeholders"] is True

    def test_composite_audience_sales_and_marketing(self):
        """Known composite 'Sales and Marketing' is valid."""
        result = validate_initiative_intent(
            who="Sales and Marketing team",
            why="To track leads",
        )
        assert result["valid"] is True
        assert result.get("multiple_stakeholders") is False

    def test_composite_audience_r_and_d(self):
        """Known composite 'Research and Development' is valid."""
        result = validate_initiative_intent(
            who="Research and Development",
            why="To speed up experiments",
        )
        assert result["valid"] is True
        assert result.get("multiple_stakeholders") is False

    def test_single_stakeholder_valid(self):
        """WHO with single stakeholder is valid."""
        result = validate_initiative_intent(
            who="New engineering hires",
            why="To onboard faster",
        )
        assert result["valid"] is True
        assert result.get("multiple_stakeholders") is False


# ============================================================================
# Handler Tests (tools/frame_initiative_intent.py)
# ============================================================================


class TestFrameInitiativeIntentHandler:
    """Tests for the MCP tool handler."""

    @pytest.mark.asyncio
    async def test_valid_input_returns_confirmed_true(self):
        """Valid input with high confidence returns confirmed=True."""
        arguments = {
            "who": "My team",
            "why": "So they can track progress",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert result.structuredContent is not None
        assert result.structuredContent["confirmed"] is True

    @pytest.mark.asyncio
    async def test_valid_input_includes_framing_intent(self):
        """Valid input includes framing_intent in structuredContent with who and why."""
        arguments = {
            "who": "My team",
            "why": "To track progress",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert "framing_intent" in result.structuredContent
        assert result.structuredContent["framing_intent"]["who"] == "My team"
        assert result.structuredContent["framing_intent"]["why"] == "To track progress"
        assert "what" not in result.structuredContent["framing_intent"]

    @pytest.mark.asyncio
    async def test_low_confidence_rejected(self):
        """Low confidence is rejected with error."""
        arguments = {
            "who": "My team",
            "why": "To track progress",
            "confidence": "low",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "confidence_too_low"
        assert result.structuredContent["confidence_provided"] == "low"

    @pytest.mark.asyncio
    async def test_medium_confidence_rejected(self):
        """Medium confidence is rejected with error."""
        arguments = {
            "who": "My team",
            "why": "To track progress",
            "confidence": "medium",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "confidence_too_low"
        assert result.structuredContent["confidence_provided"] == "medium"

    @pytest.mark.asyncio
    async def test_missing_confidence_rejected(self):
        """Missing confidence is rejected with error."""
        arguments = {
            "who": "My team",
            "why": "To track progress",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "confidence_too_low"

    @pytest.mark.asyncio
    async def test_multiple_stakeholders_returns_error(self):
        """Multiple stakeholders WHO returns error with recovery hint."""
        arguments = {
            "who": "The team and the client",
            "why": "To track progress",
            "confidence": "high",
        }
        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "multiple_stakeholders"
        assert "recovery_hint" in result.structuredContent

    @pytest.mark.asyncio
    async def test_missing_who_returns_error(self):
        """Missing WHO returns isError=True with missing fields."""
        arguments = {
            "who": "",
            "why": "To track progress",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "missing_fields"
        assert "who" in result.structuredContent["missing"]

    @pytest.mark.asyncio
    async def test_missing_why_returns_error(self):
        """Missing WHY returns isError=True with missing fields."""
        arguments = {
            "who": "My team",
            "why": "",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "missing_fields"
        assert "why" in result.structuredContent["missing"]

    @pytest.mark.asyncio
    async def test_guidance_instruction_present(self):
        """assistant_guidance with instruction is always present."""
        arguments = {
            "who": "My team",
            "why": "To track progress",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert "assistant_guidance" in result.structuredContent
        assert "instruction" in result.structuredContent["assistant_guidance"]

    @pytest.mark.asyncio
    async def test_guidance_instruction_for_missing_fields(self):
        """Guidance instruction for missing fields enforces facilitator role."""
        arguments = {"who": "", "why": "To track progress", "confidence": "high"}

        result = await handle(arguments)

        instruction = result.structuredContent["assistant_guidance"]["instruction"]
        assert "SHARPEN MODE STILL BINDING" in instruction
        assert "ONE question" in instruction
        assert "stop and wait" in instruction

    @pytest.mark.asyncio
    async def test_text_content_for_valid_input(self):
        """Valid input returns human-readable text content."""
        arguments = {
            "who": "My team",
            "why": "To track progress",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert len(result.content) == 1
        assert "Problem framing confirmed" in result.content[0].text
        assert "My team" in result.content[0].text

    @pytest.mark.asyncio
    async def test_high_confidence_in_response(self):
        """High confidence is included in response structuredContent."""
        arguments = {
            "who": "My team",
            "why": "To track progress",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.structuredContent["confidence"] == "high"

    @pytest.mark.asyncio
    async def test_valid_input_returns_proceed_to_hypothesis(self):
        """Valid input returns action='PROCEED_TO_HYPOTHESIS'."""
        arguments = {
            "who": "New engineering hires",
            "why": "So they can find answers without interrupting others",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert result.structuredContent["assistant_guidance"]["action"] == "PROCEED_TO_HYPOTHESIS"


# ============================================================================
# Integration Tests (Tool Registration)
# ============================================================================


class TestToolRegistration:
    """Tests for tool registration and discovery."""

    def test_frame_initiative_intent_in_registry(self):
        """frame_initiative_intent is registered in tool registry."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        assert "frame_initiative_intent" in TOOL_REGISTRY

    def test_tool_has_correct_annotations(self):
        """Tool has correct compliance annotations."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["frame_initiative_intent"]
        assert tool.read_only_hint is False
        assert tool.destructive_hint is False
        assert tool.open_world_hint is False

    def test_tool_description_includes_critical(self):
        """Tool description includes CRITICAL guidance."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["frame_initiative_intent"]
        assert "CRITICAL" in tool.description

    def test_tool_description_mentions_hypothesis_tool(self):
        """Tool description mentions frame_initiative_hypothesis."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["frame_initiative_intent"]
        assert "frame_initiative_hypothesis" in tool.description
