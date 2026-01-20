"""
Tests for frame_initiative_intent tool.

Tests both pure logic (tool_logic.py) and handler (tools/frame_initiative_intent.py).
Structural validation only — semantic quality is the LLM's job.
"""

import pytest

from mcp_server.sharpen.tool_logic import validate_initiative_intent
from mcp_server.sharpen.tools.frame_initiative_intent import handle


# ============================================================================
# Pure Logic Tests (tool_logic.py)
# ============================================================================


class TestValidateInitiativeIntent:
    """Tests for validate_initiative_intent function — structural validation only."""

    def test_valid_who_what_why_returns_valid_true(self):
        """Valid WHO, WHAT, and WHY returns valid=True."""
        result = validate_initiative_intent(
            who="My team",
            what="A project dashboard",
            why="So they can track progress",
        )

        assert result["valid"] is True
        assert result["missing"] == []

    def test_empty_who_returns_valid_false(self):
        """Empty WHO returns valid=False, missing=['who']."""
        result = validate_initiative_intent(
            who="",
            what="A dashboard",
            why="To track progress",
        )

        assert result["valid"] is False
        assert "who" in result["missing"]

    def test_none_who_returns_valid_false(self):
        """None WHO returns valid=False, missing=['who']."""
        result = validate_initiative_intent(
            who=None,
            what="A dashboard",
            why="To track progress",
        )

        assert result["valid"] is False
        assert "who" in result["missing"]

    def test_empty_what_returns_valid_false(self):
        """Empty WHAT returns valid=False, missing=['what']."""
        result = validate_initiative_intent(
            who="My team",
            what="",
            why="To track progress",
        )

        assert result["valid"] is False
        assert "what" in result["missing"]

    def test_none_what_returns_valid_false(self):
        """None WHAT returns valid=False, missing=['what']."""
        result = validate_initiative_intent(
            who="My team",
            what=None,
            why="To track progress",
        )

        assert result["valid"] is False
        assert "what" in result["missing"]

    def test_all_empty_returns_all_missing(self):
        """All empty returns valid=False, missing=['who', 'what', 'why']."""
        result = validate_initiative_intent(
            who="",
            what="",
            why="",
        )

        assert result["valid"] is False
        assert "who" in result["missing"]
        assert "what" in result["missing"]
        assert "why" in result["missing"]

    def test_empty_why_returns_valid_false(self):
        """Empty WHY returns valid=False, missing=['why'] (WHY is mandatory)."""
        result = validate_initiative_intent(
            who="My team",
            what="A project dashboard",
            why="",
        )

        assert result["valid"] is False
        assert "why" in result["missing"]

    def test_why_is_included_when_provided(self):
        """WHY is included in framing_intent when provided."""
        result = validate_initiative_intent(
            who="My team",
            what="A dashboard",
            why="so we can track progress",
        )

        assert result["framing_intent"]["why"] == "so we can track progress"
        assert result["valid"] is True

    def test_framing_intent_contains_all_fields(self):
        """framing_intent contains who, what, why."""
        result = validate_initiative_intent(
            who="The marketing team",
            what="A campaign tracker",
            why="to measure ROI",
        )

        assert result["framing_intent"]["who"] == "The marketing team"
        assert result["framing_intent"]["what"] == "A campaign tracker"
        assert result["framing_intent"]["why"] == "to measure ROI"

    def test_whitespace_is_stripped(self):
        """Leading/trailing whitespace is stripped from inputs."""
        result = validate_initiative_intent(
            who="  My team  ",
            what="  A dashboard  ",
            why="  To track progress  ",
        )

        assert result["framing_intent"]["who"] == "My team"
        assert result["framing_intent"]["what"] == "A dashboard"
        assert result["framing_intent"]["why"] == "To track progress"
        assert result["valid"] is True

    def test_whitespace_only_is_empty(self):
        """Whitespace-only inputs are treated as empty."""
        result = validate_initiative_intent(
            who="   ",
            what="A dashboard",
            why="To track progress",
        )

        assert result["valid"] is False
        assert "who" in result["missing"]


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
            "what": "A project dashboard",
            "why": "So they can track progress",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert result.structuredContent is not None
        assert result.structuredContent["confirmed"] is True

    @pytest.mark.asyncio
    async def test_valid_input_includes_framing_intent(self):
        """Valid input includes framing_intent in structuredContent."""
        arguments = {
            "who": "My team",
            "what": "A dashboard",
            "why": "To track progress",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert "framing_intent" in result.structuredContent
        assert result.structuredContent["framing_intent"]["who"] == "My team"
        assert result.structuredContent["framing_intent"]["what"] == "A dashboard"
        assert result.structuredContent["framing_intent"]["why"] == "To track progress"

    @pytest.mark.asyncio
    async def test_low_confidence_rejected(self):
        """Low confidence is rejected with error."""
        arguments = {
            "who": "My team",
            "what": "A dashboard",
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
            "what": "A dashboard",
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
            "what": "A dashboard",
            "why": "To track progress",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "confidence_too_low"

    @pytest.mark.asyncio
    async def test_missing_who_returns_error(self):
        """Missing WHO returns isError=True with missing fields."""
        arguments = {
            "who": "",
            "what": "A dashboard",
            "why": "To track progress",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "missing_fields"
        assert "who" in result.structuredContent["missing"]

    @pytest.mark.asyncio
    async def test_missing_what_returns_error(self):
        """Missing WHAT returns isError=True with missing fields."""
        arguments = {
            "who": "My team",
            "what": "",
            "why": "To track progress",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "missing_fields"
        assert "what" in result.structuredContent["missing"]

    @pytest.mark.asyncio
    async def test_missing_why_returns_error(self):
        """Missing WHY returns isError=True with missing fields."""
        arguments = {
            "who": "My team",
            "what": "A dashboard",
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
            "what": "A dashboard",
            "why": "To track progress",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert "assistant_guidance" in result.structuredContent
        assert "instruction" in result.structuredContent["assistant_guidance"]

    @pytest.mark.asyncio
    async def test_guidance_instruction_for_missing_fields(self):
        """Guidance instruction for missing fields enforces facilitator role."""
        arguments = {"who": "", "what": "A dashboard", "why": "To track progress", "confidence": "high"}

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
            "what": "A dashboard",
            "why": "To track progress",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert len(result.content) == 1
        assert "Intent confirmed" in result.content[0].text
        assert "My team" in result.content[0].text
        assert "A dashboard" in result.content[0].text

    @pytest.mark.asyncio
    async def test_high_confidence_in_response(self):
        """High confidence is included in response structuredContent."""
        arguments = {
            "who": "My team",
            "what": "A dashboard",
            "why": "To track progress",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.structuredContent["confidence"] == "high"


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

    def test_tool_description_includes_critical_role(self):
        """Tool description includes CRITICAL role guidance."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["frame_initiative_intent"]
        assert "CRITICAL" in tool.description

    def test_tool_description_includes_confidence_examples(self):
        """Tool description includes CONFIDENCE EXAMPLES."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["frame_initiative_intent"]
        assert "CONFIDENCE EXAMPLES" in tool.description
