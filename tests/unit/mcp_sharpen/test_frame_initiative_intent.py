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

    def test_all_true_with_both_verbatims_valid(self):
        """All provenance flags True with both verbatims is valid."""
        result = validate_intent_provenance(
            who_stated_by_user=True,
            why_reframed_from_observable=True,
            user_pain_verbatim="They feel disoriented and blocked",
            user_observable_verbatim="They'd find docs and submit first PR within 2 weeks",
        )

        assert result["valid"] is True
        assert result["failed_checks"] == []

    def test_empty_pain_verbatim_rejects(self):
        """Empty pain verbatim is rejected."""
        result = validate_intent_provenance(
            who_stated_by_user=True,
            why_reframed_from_observable=True,
            user_pain_verbatim="",
            user_observable_verbatim="They'd find docs",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_pain_verbatim"

    def test_empty_observable_verbatim_rejects(self):
        """Empty observable verbatim is rejected — observable is mandatory."""
        result = validate_intent_provenance(
            who_stated_by_user=True,
            why_reframed_from_observable=True,
            user_pain_verbatim="They feel blocked",
            user_observable_verbatim="",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_observable_verbatim"

    def test_who_not_stated_rejects(self):
        """who_stated_by_user=False is rejected."""
        result = validate_intent_provenance(
            who_stated_by_user=False,
            why_reframed_from_observable=True,
            user_pain_verbatim="Some pain",
            user_observable_verbatim="Some observable",
        )

        assert result["valid"] is False
        assert "who_stated_by_user" in result["failed_checks"]

    def test_why_not_reframed_from_observable_rejects(self):
        """why_reframed_from_observable=False is rejected."""
        result = validate_intent_provenance(
            who_stated_by_user=True,
            why_reframed_from_observable=False,
            user_pain_verbatim="Some pain",
            user_observable_verbatim="Some observable",
        )

        assert result["valid"] is False
        assert "why_reframed_from_observable" in result["failed_checks"]

    def test_multiple_failures_lists_all(self):
        """Multiple failed checks are all listed."""
        result = validate_intent_provenance(
            who_stated_by_user=False,
            why_reframed_from_observable=False,
            user_pain_verbatim="Some pain",
            user_observable_verbatim="Some observable",
        )

        assert result["valid"] is False
        assert len(result["failed_checks"]) == 2

    def test_whitespace_only_pain_verbatim_rejects(self):
        """Whitespace-only pain verbatim is treated as empty."""
        result = validate_intent_provenance(
            who_stated_by_user=True,
            why_reframed_from_observable=True,
            user_pain_verbatim="   ",
            user_observable_verbatim="Some observable",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_pain_verbatim"

    def test_whitespace_only_observable_verbatim_rejects(self):
        """Whitespace-only observable verbatim is treated as empty."""
        result = validate_intent_provenance(
            who_stated_by_user=True,
            why_reframed_from_observable=True,
            user_pain_verbatim="Some pain",
            user_observable_verbatim="   ",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_observable_verbatim"

    def test_pain_checked_before_observable(self):
        """Pain verbatim is checked before observable verbatim."""
        result = validate_intent_provenance(
            who_stated_by_user=True,
            why_reframed_from_observable=True,
            user_pain_verbatim="",
            user_observable_verbatim="",
        )

        # Should fail on pain first, not observable
        assert result["error_type"] == "empty_pain_verbatim"


# ============================================================================
# Handler Tests (tools/frame_initiative_intent.py)
# ============================================================================


class TestFrameInitiativeIntentHandler:
    """Tests for the MCP tool handler with provenance."""

    @pytest.mark.asyncio
    async def test_valid_input_returns_captured_true(self):
        """Valid input with provenance returns captured=True."""
        arguments = {
            "who": "My team",
            "user_pain_verbatim": "They waste time searching for info",
            "user_observable_verbatim": "They'd find information in under 5 minutes",
            "why": "So they can find information quickly",
            "who_stated_by_user": True,
            "why_reframed_from_observable": True,
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert result.structuredContent is not None
        assert result.structuredContent["captured"] is True

    @pytest.mark.asyncio
    async def test_valid_input_includes_framing_intent(self):
        """Valid input includes framing_intent in structuredContent with who and why."""
        arguments = {
            "who": "My team",
            "user_pain_verbatim": "They can't find docs",
            "user_observable_verbatim": "They'd find docs in under 5 minutes",
            "why": "To find docs easily",
            "who_stated_by_user": True,
            "why_reframed_from_observable": True,
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
            "user_observable_verbatim": "They'd navigate independently",
            "why": "So they can navigate independently",
            "who_stated_by_user": True,
            "why_reframed_from_observable": True,
        }

        result = await handle(arguments)

        assert "provenance" in result.structuredContent
        provenance = result.structuredContent["provenance"]
        assert provenance["user_pain_verbatim"] == "They feel lost"
        assert provenance["user_observable_verbatim"] == "They'd navigate independently"
        assert provenance["who_stated_by_user"] is True
        assert provenance["why_reframed_from_observable"] is True

    @pytest.mark.asyncio
    async def test_multiple_stakeholders_returns_incomplete(self):
        """Multiple stakeholders WHO returns zero-info error."""
        arguments = {
            "who": "The team and the client",
            "user_pain_verbatim": "Communication is broken",
            "user_observable_verbatim": "Messages would be answered same day",
            "why": "To communicate better",
            "who_stated_by_user": True,
            "why_reframed_from_observable": True,
        }
        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent == {"status": "incomplete"}

    @pytest.mark.asyncio
    async def test_missing_who_returns_incomplete(self):
        """Missing WHO returns zero-info error."""
        arguments = {
            "who": "",
            "user_pain_verbatim": "Things are slow",
            "user_observable_verbatim": "Things would be fast",
            "why": "To be faster",
            "who_stated_by_user": True,
            "why_reframed_from_observable": True,
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent == {"status": "incomplete"}

    @pytest.mark.asyncio
    async def test_missing_why_returns_incomplete(self):
        """Missing WHY returns zero-info error."""
        arguments = {
            "who": "My team",
            "user_pain_verbatim": "Things are frustrating",
            "user_observable_verbatim": "Things would work smoothly",
            "why": "",
            "who_stated_by_user": True,
            "why_reframed_from_observable": True,
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent == {"status": "incomplete"}

    @pytest.mark.asyncio
    async def test_success_has_guidance(self):
        """Success response still includes assistant_guidance."""
        arguments = {
            "who": "My team",
            "user_pain_verbatim": "They struggle",
            "user_observable_verbatim": "They'd succeed",
            "why": "To succeed",
            "who_stated_by_user": True,
            "why_reframed_from_observable": True,
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert "assistant_guidance" in result.structuredContent
        assert "instruction" in result.structuredContent["assistant_guidance"]

    @pytest.mark.asyncio
    async def test_error_has_no_guidance(self):
        """Error responses have no guidance (zero-info pattern)."""
        arguments = {
            "who": "",
            "user_pain_verbatim": "Pain exists",
            "user_observable_verbatim": "Pain would not exist",
            "why": "To fix it",
            "who_stated_by_user": True,
            "why_reframed_from_observable": True,
        }

        result = await handle(arguments)

        assert result.isError is True
        assert "assistant_guidance" not in result.structuredContent
        assert "error" not in result.structuredContent
        assert result.structuredContent == {"status": "incomplete"}

    @pytest.mark.asyncio
    async def test_text_content_for_valid_input(self):
        """Valid input returns human-readable text content."""
        arguments = {
            "who": "My team",
            "user_pain_verbatim": "They waste time",
            "user_observable_verbatim": "They'd save time",
            "why": "To save time",
            "who_stated_by_user": True,
            "why_reframed_from_observable": True,
        }

        result = await handle(arguments)

        assert len(result.content) == 1
        assert "Problem framing captured" in result.content[0].text
        assert "My team" in result.content[0].text

    @pytest.mark.asyncio
    async def test_valid_input_returns_proceed_to_hypothesis(self):
        """Valid input returns action='PROCEED_TO_HYPOTHESIS'."""
        arguments = {
            "who": "New engineering hires",
            "user_pain_verbatim": "They keep asking the same questions",
            "user_observable_verbatim": "They'd find answers without asking",
            "why": "So they can find answers without interrupting others",
            "who_stated_by_user": True,
            "why_reframed_from_observable": True,
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert result.structuredContent["assistant_guidance"]["action"] == "PROCEED_TO_HYPOTHESIS"


class TestFrameIntentHandlerProvenance:
    """Tests for handler provenance validation."""

    @pytest.mark.asyncio
    async def test_all_provenance_true_succeeds(self):
        """All provenance flags True with both verbatims succeeds."""
        arguments = {
            "who": "New engineering hires",
            "user_pain_verbatim": "They feel disoriented and blocked in the first 4 weeks",
            "user_observable_verbatim": "They'd find documentation themselves and submit their first PR within 2 weeks",
            "why": "So they can find documentation independently and ship their first PR within 2 weeks",
            "who_stated_by_user": True,
            "why_reframed_from_observable": True,
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert result.structuredContent["captured"] is True
        assert "provenance" in result.structuredContent

    @pytest.mark.asyncio
    async def test_empty_observable_verbatim_returns_incomplete(self):
        """Empty observable verbatim returns zero-info error."""
        arguments = {
            "who": "New engineering hires",
            "user_pain_verbatim": "They feel blocked",
            "user_observable_verbatim": "",
            "why": "So they can work independently",
            "who_stated_by_user": True,
            "why_reframed_from_observable": True,
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent == {"status": "incomplete"}

    @pytest.mark.asyncio
    async def test_valid_input_includes_both_verbatims_in_provenance(self):
        """Valid input includes both verbatims in provenance object."""
        arguments = {
            "who": "New hires",
            "user_pain_verbatim": "They feel lost",
            "user_observable_verbatim": "They'd navigate independently",
            "why": "So they can navigate independently",
            "who_stated_by_user": True,
            "why_reframed_from_observable": True,
        }

        result = await handle(arguments)

        assert "provenance" in result.structuredContent
        provenance = result.structuredContent["provenance"]
        assert provenance["user_pain_verbatim"] == "They feel lost"
        assert provenance["user_observable_verbatim"] == "They'd navigate independently"
        assert provenance["why_reframed_from_observable"] is True

    @pytest.mark.asyncio
    async def test_why_reframed_from_observable_false_returns_incomplete(self):
        """why_reframed_from_observable=False returns zero-info error."""
        arguments = {
            "who": "New hires",
            "user_pain_verbatim": "They feel blocked",
            "user_observable_verbatim": "They'd find docs",
            "why": "So they feel unblocked",  # This is from pain, not observable
            "who_stated_by_user": True,
            "why_reframed_from_observable": False,
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent == {"status": "incomplete"}

    @pytest.mark.asyncio
    async def test_empty_pain_verbatim_returns_incomplete(self):
        """Empty pain verbatim returns zero-info error."""
        arguments = {
            "who": "New engineering hires",
            "user_pain_verbatim": "",  # Empty!
            "user_observable_verbatim": "Some observable",
            "why": "So they can do something",
            "who_stated_by_user": True,
            "why_reframed_from_observable": True,
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent == {"status": "incomplete"}

    @pytest.mark.asyncio
    async def test_all_errors_return_zero_info(self):
        """All error paths return only status:incomplete (no guidance)."""
        arguments = {
            "who": "Someone",
            "user_pain_verbatim": "Some pain",
            "user_observable_verbatim": "Some observable",
            "why": "For reasons",
            "who_stated_by_user": False,
            "why_reframed_from_observable": False,
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent == {"status": "incomplete"}
        assert "assistant_guidance" not in result.structuredContent
        assert "error" not in result.structuredContent
        assert "failed_checks" not in result.structuredContent


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

    def test_tool_description_includes_preconditions(self):
        """Tool description includes CALL PRECONDITIONS."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["frame_initiative_intent"]
        assert "CALL PRECONDITIONS" in tool.description

    def test_legacy_guidance_dict_exists(self):
        """_LEGACY_GUIDANCE dict exists for rollback."""
        from mcp_server.sharpen.tools.frame_initiative_intent import _LEGACY_GUIDANCE

        assert isinstance(_LEGACY_GUIDANCE, dict)
        assert "provenance_failed" in _LEGACY_GUIDANCE
        assert "empty_pain_verbatim" in _LEGACY_GUIDANCE
        assert "empty_observable_verbatim" in _LEGACY_GUIDANCE
        assert "missing_fields" in _LEGACY_GUIDANCE
        assert "multiple_stakeholders" in _LEGACY_GUIDANCE

    def test_tool_schema_has_provenance_fields(self):
        """Tool schema includes all provenance fields."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["frame_initiative_intent"]
        schema = tool.input_schema

        assert "user_pain_verbatim" in schema["properties"]
        assert "user_observable_verbatim" in schema["properties"]
        assert "who_stated_by_user" in schema["properties"]
        assert "why_reframed_from_observable" in schema["properties"]
        assert "user_confirmed_framing" not in schema["properties"]  # Removed in confirmation consolidation!
        assert "confidence" not in schema["properties"]  # Removed!
        assert "why_reframed_from_pain" not in schema["properties"]  # Renamed!
