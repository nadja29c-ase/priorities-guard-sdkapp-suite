"""
Tests for frame_initiative_hypothesis tool.

Tests both pure logic (tool_logic.py) and handler.
"""

import pytest

from mcp_server.sharpen.tool_logic import validate_initiative_hypothesis
from mcp_server.sharpen.tools.frame_initiative_hypothesis import handle


class TestValidateInitiativeHypothesis:
    """Tests for validate_initiative_hypothesis function."""

    def test_valid_hypothesis_returns_framing(self):
        """Valid hypothesis returns complete framing."""
        result = validate_initiative_hypothesis(
            who="New engineering hires",
            why="So they can contribute without interruptions",
            what="A first-week onboarding checklist",
        )

        assert result["valid"] is True
        assert result["framing"]["who"] == "New engineering hires"
        assert result["framing"]["why"] == "So they can contribute without interruptions"
        assert result["framing"]["what"] == "A first-week onboarding checklist"

    def test_missing_who_rejects(self):
        """Missing WHO from prior step is rejected."""
        result = validate_initiative_hypothesis(
            who="",
            why="So they can contribute",
            what="A checklist",
        )

        assert result["valid"] is False
        assert result["error_type"] == "missing_prior_step"
        assert "who" in result["error_details"]

    def test_missing_why_rejects(self):
        """Missing WHY from prior step is rejected."""
        result = validate_initiative_hypothesis(
            who="New hires",
            why="",
            what="A checklist",
        )

        assert result["valid"] is False
        assert result["error_type"] == "missing_prior_step"
        assert "why" in result["error_details"]

    def test_missing_both_who_and_why_rejects(self):
        """Missing both WHO and WHY from prior step is rejected."""
        result = validate_initiative_hypothesis(
            who="",
            why="",
            what="A checklist",
        )

        assert result["valid"] is False
        assert result["error_type"] == "missing_prior_step"
        assert "who" in result["error_details"]
        assert "why" in result["error_details"]

    def test_missing_what_rejects(self):
        """Missing WHAT hypothesis is rejected."""
        result = validate_initiative_hypothesis(
            who="New hires",
            why="So they can contribute",
            what="",
        )

        assert result["valid"] is False
        assert result["error_type"] == "missing_what"

    def test_whitespace_trimmed(self):
        """Whitespace in inputs is trimmed."""
        result = validate_initiative_hypothesis(
            who="  New hires  ",
            why="  So they contribute  ",
            what="  A checklist  ",
        )

        assert result["valid"] is True
        assert result["framing"]["who"] == "New hires"
        assert result["framing"]["why"] == "So they contribute"
        assert result["framing"]["what"] == "A checklist"

    def test_none_inputs_handled(self):
        """None inputs are handled gracefully."""
        result = validate_initiative_hypothesis(
            who=None,
            why=None,
            what=None,
        )

        assert result["valid"] is False
        assert result["error_type"] == "missing_prior_step"


class TestFrameHypothesisHandler:
    """Tests for frame_initiative_hypothesis handler."""

    @pytest.mark.asyncio
    async def test_valid_input_returns_proceed_action(self):
        """Valid input returns action='PROCEED_TO_CONSTRAINTS'."""
        arguments = {
            "who": "New engineering hires",
            "why": "So they can contribute without interruptions",
            "what": "A first-week checklist",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert result.structuredContent["confirmed"] is True
        assert result.structuredContent["assistant_guidance"]["action"] == "PROCEED_TO_CONSTRAINTS"

    @pytest.mark.asyncio
    async def test_low_confidence_returns_clarifying_action(self):
        """Low confidence returns action='ASK_CLARIFYING'."""
        arguments = {
            "who": "New hires",
            "why": "So they contribute",
            "what": "something",
            "confidence": "low",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "confidence_too_low"
        assert result.structuredContent["assistant_guidance"]["action"] == "ASK_CLARIFYING"

    @pytest.mark.asyncio
    async def test_medium_confidence_returns_clarifying_action(self):
        """Medium confidence returns action='ASK_CLARIFYING'."""
        arguments = {
            "who": "New hires",
            "why": "So they contribute",
            "what": "something helpful",
            "confidence": "medium",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "confidence_too_low"
        assert result.structuredContent["assistant_guidance"]["action"] == "ASK_CLARIFYING"

    @pytest.mark.asyncio
    async def test_missing_prior_step_returns_refuse_action(self):
        """Missing prior step returns action='REFUSE'."""
        arguments = {
            "who": "",
            "why": "",
            "what": "A checklist",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "missing_prior_step"
        assert result.structuredContent["assistant_guidance"]["action"] == "REFUSE"

    @pytest.mark.asyncio
    async def test_missing_what_returns_clarifying_action(self):
        """Missing WHAT returns action='ASK_CLARIFYING'."""
        arguments = {
            "who": "New hires",
            "why": "So they contribute",
            "what": "",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "missing_what"
        assert result.structuredContent["assistant_guidance"]["action"] == "ASK_CLARIFYING"

    @pytest.mark.asyncio
    async def test_valid_input_includes_framing_intent(self):
        """Valid input includes framing_intent with who, why, what."""
        arguments = {
            "who": "New engineering hires",
            "why": "So they can find answers without interrupting",
            "what": "A first-week checklist",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert "framing_intent" in result.structuredContent
        assert result.structuredContent["framing_intent"]["who"] == "New engineering hires"
        assert result.structuredContent["framing_intent"]["why"] == "So they can find answers without interrupting"
        assert result.structuredContent["framing_intent"]["what"] == "A first-week checklist"

    @pytest.mark.asyncio
    async def test_text_content_for_valid_input(self):
        """Valid input returns human-readable text content."""
        arguments = {
            "who": "New engineering hires",
            "why": "So they can contribute",
            "what": "A checklist",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert len(result.content) == 1
        assert "Hypothesis confirmed" in result.content[0].text
        assert "New engineering hires" in result.content[0].text
        assert "A checklist" in result.content[0].text

    @pytest.mark.asyncio
    async def test_guidance_instruction_for_missing_what(self):
        """Guidance instruction for missing WHAT enforces facilitator role."""
        arguments = {
            "who": "New hires",
            "why": "So they contribute",
            "what": "",
            "confidence": "high",
        }

        result = await handle(arguments)

        instruction = result.structuredContent["assistant_guidance"]["instruction"]
        assert "SHARPEN MODE STILL BINDING" in instruction
        assert "Do not suggest solutions" in instruction


class TestFrameHypothesisToolRegistration:
    """Tests for tool registration and discovery."""

    def test_frame_initiative_hypothesis_in_registry(self):
        """frame_initiative_hypothesis is registered in tool registry."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        assert "frame_initiative_hypothesis" in TOOL_REGISTRY

    def test_tool_has_correct_annotations(self):
        """Tool has correct compliance annotations."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["frame_initiative_hypothesis"]
        assert tool.read_only_hint is False
        assert tool.destructive_hint is False
        assert tool.open_world_hint is False

    def test_tool_description_frames_what_as_hypothesis(self):
        """Tool description frames WHAT as hypothesis."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["frame_initiative_hypothesis"]
        assert "hypothesis" in tool.description.lower()

    def test_tool_description_mentions_prior_step(self):
        """Tool description mentions requiring prior step."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["frame_initiative_hypothesis"]
        assert "frame_initiative_intent" in tool.description
