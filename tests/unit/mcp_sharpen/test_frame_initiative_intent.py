"""
Tests for frame_initiative_intent tool.

Tests both pure logic (tool_logic.py) and handler (tools/frame_initiative_intent.py).
Structural validation only — semantic quality is the LLM's job.

Note: WHAT is now captured separately in frame_initiative_hypothesis.
This tool only captures WHO and WHY with provenance evidence.
"""

import pytest

from mcp_server.sharpen.tool_logic import validate_initiative_intent, validate_intent_provenance
from mcp_server.sharpen.tools.frame_initiative_intent import handle


# ============================================================================
# Pure Logic Tests (tool_logic.py) — Structural Validation
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
# Provenance Validation Tests (tool_logic.py)
# ============================================================================


class TestValidateIntentProvenance:
    """Tests for validate_intent_provenance function."""

    def test_all_true_with_verbatim_valid(self):
        """All provenance flags True with verbatim is valid."""
        result = validate_intent_provenance(
            who_stated_by_user=True,
            why_reframed_from_pain=True,
            user_confirmed_framing=True,
            user_pain_verbatim="They keep asking the same questions",
        )

        assert result["valid"] is True
        assert result["failed_checks"] == []

    def test_empty_verbatim_rejects(self):
        """Empty verbatim is rejected — pain must exist."""
        result = validate_intent_provenance(
            who_stated_by_user=True,
            why_reframed_from_pain=True,
            user_confirmed_framing=True,
            user_pain_verbatim="",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_verbatim"

    def test_who_not_stated_rejects(self):
        """who_stated_by_user=False is rejected."""
        result = validate_intent_provenance(
            who_stated_by_user=False,
            why_reframed_from_pain=True,
            user_confirmed_framing=True,
            user_pain_verbatim="Some pain",
        )

        assert result["valid"] is False
        assert "who_stated_by_user" in result["failed_checks"]

    def test_why_not_reframed_rejects(self):
        """why_reframed_from_pain=False is rejected."""
        result = validate_intent_provenance(
            who_stated_by_user=True,
            why_reframed_from_pain=False,
            user_confirmed_framing=True,
            user_pain_verbatim="Some pain",
        )

        assert result["valid"] is False
        assert "why_reframed_from_pain" in result["failed_checks"]

    def test_not_confirmed_rejects(self):
        """user_confirmed_framing=False is rejected."""
        result = validate_intent_provenance(
            who_stated_by_user=True,
            why_reframed_from_pain=True,
            user_confirmed_framing=False,
            user_pain_verbatim="Some pain",
        )

        assert result["valid"] is False
        assert "user_confirmed_framing" in result["failed_checks"]

    def test_multiple_failures_lists_all(self):
        """Multiple failed checks are all listed."""
        result = validate_intent_provenance(
            who_stated_by_user=False,
            why_reframed_from_pain=False,
            user_confirmed_framing=False,
            user_pain_verbatim="Some pain",  # verbatim present, so we get boolean failures
        )

        assert result["valid"] is False
        assert len(result["failed_checks"]) == 3

    def test_whitespace_only_verbatim_rejects(self):
        """Whitespace-only verbatim is treated as empty."""
        result = validate_intent_provenance(
            who_stated_by_user=True,
            why_reframed_from_pain=True,
            user_confirmed_framing=True,
            user_pain_verbatim="   ",  # Whitespace only
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_verbatim"


# ============================================================================
# Handler Tests (tools/frame_initiative_intent.py)
# ============================================================================


class TestFrameInitiativeIntentHandler:
    """Tests for the MCP tool handler with provenance."""

    @pytest.mark.asyncio
    async def test_valid_input_returns_confirmed_true(self):
        """Valid input with provenance returns confirmed=True."""
        arguments = {
            "who": "My team",
            "user_pain_verbatim": "They waste time searching for info",
            "why": "So they can find information quickly",
            "who_stated_by_user": True,
            "why_reframed_from_pain": True,
            "user_confirmed_framing": True,
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
            "user_pain_verbatim": "They can't find docs",
            "why": "To find docs easily",
            "who_stated_by_user": True,
            "why_reframed_from_pain": True,
            "user_confirmed_framing": True,
        }

        result = await handle(arguments)

        assert "framing_intent" in result.structuredContent
        assert result.structuredContent["framing_intent"]["who"] == "My team"
        assert result.structuredContent["framing_intent"]["why"] == "To find docs easily"
        assert "what" not in result.structuredContent["framing_intent"]

    @pytest.mark.asyncio
    async def test_valid_input_includes_provenance(self):
        """Valid input includes provenance object in response."""
        arguments = {
            "who": "New hires",
            "user_pain_verbatim": "They feel lost",
            "why": "So they can navigate independently",
            "who_stated_by_user": True,
            "why_reframed_from_pain": True,
            "user_confirmed_framing": True,
        }

        result = await handle(arguments)

        assert "provenance" in result.structuredContent
        provenance = result.structuredContent["provenance"]
        assert provenance["user_pain_verbatim"] == "They feel lost"
        assert provenance["who_stated_by_user"] is True
        assert provenance["why_reframed_from_pain"] is True
        assert provenance["user_confirmed_framing"] is True

    @pytest.mark.asyncio
    async def test_multiple_stakeholders_returns_error(self):
        """Multiple stakeholders WHO returns error with recovery hint."""
        arguments = {
            "who": "The team and the client",
            "user_pain_verbatim": "Communication is broken",
            "why": "To communicate better",
            "who_stated_by_user": True,
            "why_reframed_from_pain": True,
            "user_confirmed_framing": True,
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
            "user_pain_verbatim": "Things are slow",
            "why": "To be faster",
            "who_stated_by_user": True,
            "why_reframed_from_pain": True,
            "user_confirmed_framing": True,
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
            "user_pain_verbatim": "Things are frustrating",
            "why": "",
            "who_stated_by_user": True,
            "why_reframed_from_pain": True,
            "user_confirmed_framing": True,
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
            "user_pain_verbatim": "They struggle",
            "why": "To succeed",
            "who_stated_by_user": True,
            "why_reframed_from_pain": True,
            "user_confirmed_framing": True,
        }

        result = await handle(arguments)

        assert "assistant_guidance" in result.structuredContent
        assert "instruction" in result.structuredContent["assistant_guidance"]

    @pytest.mark.asyncio
    async def test_guidance_instruction_for_missing_fields(self):
        """Guidance instruction for missing fields enforces facilitator role."""
        arguments = {
            "who": "",
            "user_pain_verbatim": "Pain exists",
            "why": "To fix it",
            "who_stated_by_user": True,
            "why_reframed_from_pain": True,
            "user_confirmed_framing": True,
        }

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
            "user_pain_verbatim": "They waste time",
            "why": "To save time",
            "who_stated_by_user": True,
            "why_reframed_from_pain": True,
            "user_confirmed_framing": True,
        }

        result = await handle(arguments)

        assert len(result.content) == 1
        assert "Problem framing confirmed" in result.content[0].text
        assert "My team" in result.content[0].text

    @pytest.mark.asyncio
    async def test_valid_input_returns_proceed_to_hypothesis(self):
        """Valid input returns action='PROCEED_TO_HYPOTHESIS'."""
        arguments = {
            "who": "New engineering hires",
            "user_pain_verbatim": "They keep asking the same questions",
            "why": "So they can find answers without interrupting others",
            "who_stated_by_user": True,
            "why_reframed_from_pain": True,
            "user_confirmed_framing": True,
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert result.structuredContent["assistant_guidance"]["action"] == "PROCEED_TO_HYPOTHESIS"


class TestFrameIntentHandlerProvenance:
    """Tests for handler provenance validation."""

    @pytest.mark.asyncio
    async def test_all_provenance_true_succeeds(self):
        """All provenance flags True with verbatim succeeds."""
        arguments = {
            "who": "New engineering hires",
            "user_pain_verbatim": "They keep asking the same questions",
            "why": "So they can find answers without interrupting others",
            "who_stated_by_user": True,
            "why_reframed_from_pain": True,
            "user_confirmed_framing": True,
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert result.structuredContent["confirmed"] is True
        assert "provenance" in result.structuredContent

    @pytest.mark.asyncio
    async def test_provenance_false_rejects(self):
        """Any provenance flag False is rejected."""
        arguments = {
            "who": "New engineering hires",
            "user_pain_verbatim": "Some pain",
            "why": "So they can do something",
            "who_stated_by_user": True,
            "why_reframed_from_pain": True,
            "user_confirmed_framing": False,  # Not confirmed!
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "provenance_failed"

    @pytest.mark.asyncio
    async def test_empty_verbatim_rejects(self):
        """Empty verbatim is rejected."""
        arguments = {
            "who": "New engineering hires",
            "user_pain_verbatim": "",  # Empty!
            "why": "So they can do something",
            "who_stated_by_user": True,
            "why_reframed_from_pain": True,
            "user_confirmed_framing": True,
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_verbatim"

    @pytest.mark.asyncio
    async def test_provenance_failure_returns_guidance(self):
        """Provenance failure returns actionable guidance."""
        arguments = {
            "who": "Someone",
            "user_pain_verbatim": "Some pain",
            "why": "For reasons",
            "who_stated_by_user": False,
            "why_reframed_from_pain": False,
            "user_confirmed_framing": False,
        }

        result = await handle(arguments)

        assert "assistant_guidance" in result.structuredContent
        instruction = result.structuredContent["assistant_guidance"]["instruction"]
        assert "SHARPEN MODE STILL BINDING" in instruction

    @pytest.mark.asyncio
    async def test_empty_verbatim_returns_specific_guidance(self):
        """Empty verbatim returns specific guidance about getting pain."""
        arguments = {
            "who": "Team",
            "user_pain_verbatim": "",
            "why": "Some reason",
            "who_stated_by_user": True,
            "why_reframed_from_pain": True,
            "user_confirmed_framing": True,
        }

        result = await handle(arguments)

        instruction = result.structuredContent["assistant_guidance"]["instruction"]
        assert "user_pain_verbatim is empty" in instruction

    @pytest.mark.asyncio
    async def test_failed_checks_listed_in_response(self):
        """Failed provenance checks are listed in response."""
        arguments = {
            "who": "Team",
            "user_pain_verbatim": "Pain",
            "why": "Reason",
            "who_stated_by_user": False,
            "why_reframed_from_pain": True,
            "user_confirmed_framing": False,
        }

        result = await handle(arguments)

        assert "failed_checks" in result.structuredContent
        assert "who_stated_by_user" in result.structuredContent["failed_checks"]
        assert "user_confirmed_framing" in result.structuredContent["failed_checks"]


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

    def test_tool_description_includes_provenance(self):
        """Tool description includes PROVENANCE guidance."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["frame_initiative_intent"]
        assert "PROVENANCE" in tool.description

    def test_tool_description_mentions_hypothesis_tool(self):
        """Tool description mentions frame_initiative_hypothesis."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["frame_initiative_intent"]
        assert "frame_initiative_hypothesis" in tool.description

    def test_tool_schema_has_provenance_fields(self):
        """Tool schema includes all provenance fields."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["frame_initiative_intent"]
        schema = tool.input_schema

        assert "user_pain_verbatim" in schema["properties"]
        assert "who_stated_by_user" in schema["properties"]
        assert "why_reframed_from_pain" in schema["properties"]
        assert "user_confirmed_framing" in schema["properties"]
        assert "confidence" not in schema["properties"]  # Removed!
