"""
Tests for frame_initiative_intent tool.

Tests both pure logic (tool_logic.py) and handler (tools/frame_initiative_intent.py).
"""

import pytest

from mcp_server.sharpen.tool_logic import validate_initiative_intent
from mcp_server.sharpen.tools.frame_initiative_intent import handle


# ============================================================================
# Pure Logic Tests (tool_logic.py)
# ============================================================================


class TestValidateInitiativeIntent:
    """Tests for validate_initiative_intent function."""

    def test_valid_who_and_what_returns_high_confidence(self):
        """Valid WHO and WHAT returns high confidence."""
        result = validate_initiative_intent(
            who="My team",
            what="A project dashboard",
        )

        assert result["confidence"] == "high"
        assert result["needs_clarification"] is False
        assert result["clarify_type"] is None

    def test_empty_who_returns_low_confidence(self):
        """Empty WHO returns low confidence, clarify WHO."""
        result = validate_initiative_intent(
            who="",
            what="A dashboard",
        )

        assert result["confidence"] == "low"
        assert result["needs_clarification"] is True
        assert result["clarify_type"] == "WHO"

    def test_short_who_returns_low_confidence(self):
        """WHO less than 3 chars returns low confidence."""
        result = validate_initiative_intent(
            who="Me",
            what="A dashboard",
        )

        assert result["confidence"] == "low"
        assert result["clarify_type"] == "WHO"

    def test_empty_what_returns_low_confidence(self):
        """Empty WHAT returns low confidence, clarify WHAT."""
        result = validate_initiative_intent(
            who="My team",
            what="",
        )

        assert result["confidence"] == "low"
        assert result["needs_clarification"] is True
        assert result["clarify_type"] == "WHAT"

    def test_short_what_returns_low_confidence(self):
        """WHAT less than 5 chars returns low confidence."""
        result = validate_initiative_intent(
            who="My team",
            what="App",
        )

        assert result["confidence"] == "low"
        assert result["clarify_type"] == "WHAT"

    def test_vague_what_returns_medium_confidence(self):
        """Vague WHAT with words like 'improve' returns medium confidence."""
        result = validate_initiative_intent(
            who="My team",
            what="Improve the process",
        )

        assert result["confidence"] == "medium"
        assert result["needs_clarification"] is True
        assert result["clarify_type"] == "WHAT"

    def test_vague_what_case_insensitive(self):
        """Vague word detection is case-insensitive."""
        result = validate_initiative_intent(
            who="My team",
            what="IMPROVE the workflow",
        )

        assert result["confidence"] == "medium"
        assert result["clarify_type"] == "WHAT"

    def test_activity_based_what_returns_medium_confidence(self):
        """Activity-based WHAT starting with verb returns medium confidence."""
        result = validate_initiative_intent(
            who="My team",
            what="Work on the backend",
        )

        assert result["confidence"] == "medium"
        assert result["needs_clarification"] is True
        assert result["clarify_type"] == "WHAT"

    def test_empty_why_does_not_affect_confidence(self):
        """Empty WHY does not affect confidence (WHY is optional)."""
        result = validate_initiative_intent(
            who="My team",
            what="A project dashboard",
            why="",
        )

        assert result["confidence"] == "high"
        assert result["framing_intent"]["why"] is None

    def test_why_is_included_when_provided(self):
        """WHY is included in framing_intent when provided."""
        result = validate_initiative_intent(
            who="My team",
            what="A dashboard",
            why="so we can track progress",
        )

        assert result["framing_intent"]["why"] == "so we can track progress"
        assert result["confidence"] == "high"

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
        )

        assert result["framing_intent"]["who"] == "My team"
        assert result["framing_intent"]["what"] == "A dashboard"
        assert result["confidence"] == "high"


# ============================================================================
# Handler Tests (tools/frame_initiative_intent.py)
# ============================================================================


class TestFrameInitiativeIntentHandler:
    """Tests for the MCP tool handler."""

    @pytest.mark.asyncio
    async def test_valid_input_returns_confirm_action(self):
        """Valid input returns CONFIRM_AND_PROCEED action."""
        arguments = {
            "who": "My team",
            "what": "A project dashboard",
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert result.structuredContent is not None
        assert result.structuredContent["assistant_guidance"]["action"] == "CONFIRM_AND_PROCEED"

    @pytest.mark.asyncio
    async def test_invalid_input_returns_clarifying_action(self):
        """Invalid input returns ASK_CLARIFYING action."""
        arguments = {
            "who": "",
            "what": "A dashboard",
        }

        result = await handle(arguments)

        assert result.structuredContent["assistant_guidance"]["action"] == "ASK_CLARIFYING"

    @pytest.mark.asyncio
    async def test_clarify_object_present_when_needed(self):
        """clarify object is present when needs_clarification is true."""
        arguments = {
            "who": "",
            "what": "A dashboard",
        }

        result = await handle(arguments)

        assert "clarify" in result.structuredContent
        assert result.structuredContent["clarify"]["type"] == "WHO"

    @pytest.mark.asyncio
    async def test_clarify_object_absent_when_not_needed(self):
        """clarify object is absent when needs_clarification is false."""
        arguments = {
            "who": "My team",
            "what": "A project dashboard",
        }

        result = await handle(arguments)

        assert "clarify" not in result.structuredContent

    @pytest.mark.asyncio
    async def test_empty_arguments_handled(self):
        """Empty arguments are handled gracefully."""
        arguments = {}

        result = await handle(arguments)

        # Should return low confidence, clarify WHO
        assert result.structuredContent["confidence"] == "low"
        assert result.structuredContent["clarify"]["type"] == "WHO"

    @pytest.mark.asyncio
    async def test_guidance_instruction_for_who_clarification(self):
        """Guidance instruction for WHO clarification enforces facilitator role."""
        arguments = {"who": "", "what": "A dashboard"}

        result = await handle(arguments)

        instruction = result.structuredContent["assistant_guidance"]["instruction"]
        assert "Ask ONE question" in instruction
        assert "Do not suggest" in instruction

    @pytest.mark.asyncio
    async def test_guidance_instruction_for_what_clarification(self):
        """Guidance instruction for WHAT clarification enforces facilitator role."""
        arguments = {"who": "My team", "what": ""}

        result = await handle(arguments)

        instruction = result.structuredContent["assistant_guidance"]["instruction"]
        assert "Ask ONE question" in instruction
        assert "Do not suggest" in instruction

    @pytest.mark.asyncio
    async def test_handler_ignores_missing_why(self):
        """WHY is optional — handler returns high confidence without it."""
        arguments = {
            "who": "My team",
            "what": "A dashboard",
        }

        result = await handle(arguments)

        assert result.structuredContent["confidence"] == "high"
        assert result.structuredContent["framing_intent"]["why"] is None

    @pytest.mark.asyncio
    async def test_semantic_failures_do_not_return_error(self):
        """Semantic failures (low confidence) are not errors — just clarification needed."""
        arguments = {"who": "", "what": ""}

        result = await handle(arguments)

        assert result.isError is not True
        assert result.structuredContent["confidence"] == "low"
        assert result.structuredContent["needs_clarification"] is True
