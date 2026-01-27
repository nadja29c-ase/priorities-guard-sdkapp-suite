"""
Tests for frame_initiative_outcome tool (registered as frame_initiative_outcome).

Tests both pure logic (tool_logic.py) and handler (tools/frame_initiative_intent.py).
Structural validation only — semantic quality is the LLM's job.

Note: WHO is now captured separately in frame_initiative_audience.
This tool captures PAIN + OBSERVABLE + WHY with provenance evidence.
WHO is validated as a prior step dependency (must be non-empty).

NOTE: Tool implementation file is frame_initiative_intent.py (for rollback safety),
but tool is registered as frame_initiative_outcome.
"""

import pytest

from mcp_server.sharpen.tool_logic import validate_initiative_outcome, validate_outcome_provenance
from mcp_server.sharpen.tools.frame_initiative_intent import handle


# ============================================================================
# Pure Logic Tests (tool_logic.py) — Structural Validation
# ============================================================================


class TestValidateInitiativeOutcome:
    """Tests for validate_initiative_outcome function — structural validation only."""

    def test_valid_who_why_returns_valid_true(self):
        """Valid WHO and WHY returns valid=True."""
        result = validate_initiative_outcome(
            who="My team",
            why="So they can track progress",
        )

        assert result["valid"] is True
        assert result["error_type"] is None

    def test_empty_who_returns_missing_prior_step(self):
        """Empty WHO returns missing_prior_step error (WHO comes from audience step)."""
        result = validate_initiative_outcome(
            who="",
            why="To track progress",
        )

        assert result["valid"] is False
        assert result["error_type"] == "missing_prior_step"

    def test_none_who_returns_missing_prior_step(self):
        """None WHO returns missing_prior_step error."""
        result = validate_initiative_outcome(
            who=None,
            why="To track progress",
        )

        assert result["valid"] is False
        assert result["error_type"] == "missing_prior_step"

    def test_whitespace_only_who_returns_missing_prior_step(self):
        """Whitespace-only WHO is treated as empty → missing_prior_step."""
        result = validate_initiative_outcome(
            who="   ",
            why="To track progress",
        )

        assert result["valid"] is False
        assert result["error_type"] == "missing_prior_step"

    def test_empty_why_returns_missing_why(self):
        """Empty WHY returns missing_why error."""
        result = validate_initiative_outcome(
            who="My team",
            why="",
        )

        assert result["valid"] is False
        assert result["error_type"] == "missing_why"

    def test_none_why_returns_missing_why(self):
        """None WHY returns missing_why error."""
        result = validate_initiative_outcome(
            who="My team",
            why=None,
        )

        assert result["valid"] is False
        assert result["error_type"] == "missing_why"

    def test_framing_outcome_contains_who_and_why(self):
        """framing_outcome contains who and why."""
        result = validate_initiative_outcome(
            who="The marketing team",
            why="to measure ROI",
        )

        assert result["framing_outcome"]["who"] == "The marketing team"
        assert result["framing_outcome"]["why"] == "to measure ROI"

    def test_whitespace_is_stripped(self):
        """Leading/trailing whitespace is stripped from inputs."""
        result = validate_initiative_outcome(
            who="  My team  ",
            why="  To track progress  ",
        )

        assert result["framing_outcome"]["who"] == "My team"
        assert result["framing_outcome"]["why"] == "To track progress"
        assert result["valid"] is True


# ============================================================================
# Provenance Validation Tests (tool_logic.py)
# ============================================================================


class TestValidateOutcomeProvenance:
    """Tests for validate_outcome_provenance function."""

    def test_all_true_with_both_verbatims_valid(self):
        """All provenance flags True with both verbatims is valid."""
        result = validate_outcome_provenance(
            why_reframed_from_observable=True,
            user_pain_verbatim="They feel disoriented and blocked",
            user_observable_verbatim="They'd find docs and submit first PR within 2 weeks",
        )

        assert result["valid"] is True
        assert result["failed_checks"] == []

    def test_empty_pain_verbatim_rejects(self):
        """Empty pain verbatim is rejected."""
        result = validate_outcome_provenance(
            why_reframed_from_observable=True,
            user_pain_verbatim="",
            user_observable_verbatim="They'd find docs",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_pain_verbatim"

    def test_empty_observable_verbatim_rejects(self):
        """Empty observable verbatim is rejected — observable is mandatory."""
        result = validate_outcome_provenance(
            why_reframed_from_observable=True,
            user_pain_verbatim="They feel blocked",
            user_observable_verbatim="",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_observable_verbatim"

    def test_why_not_reframed_from_observable_rejects(self):
        """why_reframed_from_observable=False is rejected."""
        result = validate_outcome_provenance(
            why_reframed_from_observable=False,
            user_pain_verbatim="Some pain",
            user_observable_verbatim="Some observable",
        )

        assert result["valid"] is False
        assert "why_reframed_from_observable" in result["failed_checks"]

    def test_whitespace_only_pain_verbatim_rejects(self):
        """Whitespace-only pain verbatim is treated as empty."""
        result = validate_outcome_provenance(
            why_reframed_from_observable=True,
            user_pain_verbatim="   ",
            user_observable_verbatim="Some observable",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_pain_verbatim"

    def test_whitespace_only_observable_verbatim_rejects(self):
        """Whitespace-only observable verbatim is treated as empty."""
        result = validate_outcome_provenance(
            why_reframed_from_observable=True,
            user_pain_verbatim="Some pain",
            user_observable_verbatim="   ",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_observable_verbatim"

    def test_pain_checked_before_observable(self):
        """Pain verbatim is checked before observable verbatim."""
        result = validate_outcome_provenance(
            why_reframed_from_observable=True,
            user_pain_verbatim="",
            user_observable_verbatim="",
        )

        # Should fail on pain first, not observable
        assert result["error_type"] == "empty_pain_verbatim"


# ============================================================================
# Handler Tests (tools/frame_initiative_intent.py → frame_initiative_outcome)
# ============================================================================


class TestFrameInitiativeOutcomeHandler:
    """Tests for the MCP tool handler with provenance."""

    @pytest.mark.asyncio
    async def test_valid_input_returns_captured_true(self):
        """Valid input with provenance returns captured=True."""
        arguments = {
            "who": "My team",
            "user_pain_verbatim": "They waste time searching for info",
            "user_observable_verbatim": "They'd find information in under 5 minutes",
            "why": "So they can find information quickly",
            "why_reframed_from_observable": True,
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert result.structuredContent is not None
        assert result.structuredContent["captured"] is True

    @pytest.mark.asyncio
    async def test_valid_input_includes_framing_outcome(self):
        """Valid input includes framing_outcome in structuredContent with who and why."""
        arguments = {
            "who": "My team",
            "user_pain_verbatim": "They can't find docs",
            "user_observable_verbatim": "They'd find docs in under 5 minutes",
            "why": "To find docs easily",
            "why_reframed_from_observable": True,
        }

        result = await handle(arguments)

        assert "framing_outcome" in result.structuredContent
        assert result.structuredContent["framing_outcome"]["who"] == "My team"
        assert result.structuredContent["framing_outcome"]["why"] == "To find docs easily"

    @pytest.mark.asyncio
    async def test_valid_input_includes_provenance(self):
        """Valid input includes provenance object in response."""
        arguments = {
            "who": "New hires",
            "user_pain_verbatim": "They feel lost",
            "user_observable_verbatim": "They'd navigate independently",
            "why": "So they can navigate independently",
            "why_reframed_from_observable": True,
        }

        result = await handle(arguments)

        assert "provenance" in result.structuredContent
        provenance = result.structuredContent["provenance"]
        assert provenance["user_pain_verbatim"] == "They feel lost"
        assert provenance["user_observable_verbatim"] == "They'd navigate independently"
        assert provenance["why_reframed_from_observable"] is True

    @pytest.mark.asyncio
    async def test_missing_who_returns_error_with_guidance(self):
        """Missing WHO returns error with BACKTRACK guidance."""
        arguments = {
            "who": "",
            "user_pain_verbatim": "Things are slow",
            "user_observable_verbatim": "Things would be fast",
            "why": "To be faster",
            "why_reframed_from_observable": True,
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "missing_prior_step"
        assert result.structuredContent["assistant_guidance"]["action"] == "BACKTRACK"

    @pytest.mark.asyncio
    async def test_empty_pain_verbatim_returns_error_with_guidance(self):
        """Empty pain verbatim returns error with ASK_CLARIFYING guidance."""
        arguments = {
            "who": "New engineering hires",
            "user_pain_verbatim": "",
            "user_observable_verbatim": "Some observable",
            "why": "So they can do something",
            "why_reframed_from_observable": True,
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_pain_verbatim"
        assert result.structuredContent["assistant_guidance"]["action"] == "ASK_CLARIFYING"

    @pytest.mark.asyncio
    async def test_empty_observable_verbatim_returns_error_with_guidance(self):
        """Empty observable verbatim returns error with ASK_CLARIFYING guidance."""
        arguments = {
            "who": "New engineering hires",
            "user_pain_verbatim": "They feel blocked",
            "user_observable_verbatim": "",
            "why": "So they can work independently",
            "why_reframed_from_observable": True,
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_observable_verbatim"
        assert result.structuredContent["assistant_guidance"]["action"] == "ASK_CLARIFYING"

    @pytest.mark.asyncio
    async def test_why_reframed_from_observable_false_returns_error(self):
        """why_reframed_from_observable=False returns error with guidance."""
        arguments = {
            "who": "New hires",
            "user_pain_verbatim": "They feel blocked",
            "user_observable_verbatim": "They'd find docs",
            "why": "So they feel unblocked",  # This is from pain, not observable
            "why_reframed_from_observable": False,
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "provenance_failed"
        assert result.structuredContent["assistant_guidance"]["action"] == "ASK_CLARIFYING"

    @pytest.mark.asyncio
    async def test_success_has_guidance(self):
        """Success response includes assistant_guidance."""
        arguments = {
            "who": "My team",
            "user_pain_verbatim": "They struggle",
            "user_observable_verbatim": "They'd succeed",
            "why": "To succeed",
            "why_reframed_from_observable": True,
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert "assistant_guidance" in result.structuredContent
        assert "instruction" in result.structuredContent["assistant_guidance"]

    @pytest.mark.asyncio
    async def test_text_content_for_valid_input(self):
        """Valid input returns human-readable text content."""
        arguments = {
            "who": "My team",
            "user_pain_verbatim": "They waste time",
            "user_observable_verbatim": "They'd save time",
            "why": "To save time",
            "why_reframed_from_observable": True,
        }

        result = await handle(arguments)

        assert len(result.content) == 1
        assert "Problem outcome captured" in result.content[0].text
        assert "My team" in result.content[0].text

    @pytest.mark.asyncio
    async def test_valid_input_returns_proceed_to_hypothesis(self):
        """Valid input returns action='PROCEED_TO_HYPOTHESIS'."""
        arguments = {
            "who": "New engineering hires",
            "user_pain_verbatim": "They keep asking the same questions",
            "user_observable_verbatim": "They'd find answers without asking",
            "why": "So they can find answers without interrupting others",
            "why_reframed_from_observable": True,
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert result.structuredContent["assistant_guidance"]["action"] == "PROCEED_TO_HYPOTHESIS"


class TestFrameOutcomeHandlerProvenance:
    """Tests for handler provenance validation."""

    @pytest.mark.asyncio
    async def test_all_provenance_true_succeeds(self):
        """All provenance flags True with both verbatims succeeds."""
        arguments = {
            "who": "New engineering hires",
            "user_pain_verbatim": "They feel disoriented and blocked in the first 4 weeks",
            "user_observable_verbatim": "They'd find documentation themselves and submit their first PR within 2 weeks",
            "why": "So they can find documentation independently and ship their first PR within 2 weeks",
            "why_reframed_from_observable": True,
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert result.structuredContent["captured"] is True
        assert "provenance" in result.structuredContent

    @pytest.mark.asyncio
    async def test_valid_input_includes_both_verbatims_in_provenance(self):
        """Valid input includes both verbatims in provenance object."""
        arguments = {
            "who": "New hires",
            "user_pain_verbatim": "They feel lost",
            "user_observable_verbatim": "They'd navigate independently",
            "why": "So they can navigate independently",
            "why_reframed_from_observable": True,
        }

        result = await handle(arguments)

        assert "provenance" in result.structuredContent
        provenance = result.structuredContent["provenance"]
        assert provenance["user_pain_verbatim"] == "They feel lost"
        assert provenance["user_observable_verbatim"] == "They'd navigate independently"
        assert provenance["why_reframed_from_observable"] is True


# ============================================================================
# Integration Tests (Tool Registration)
# ============================================================================


class TestToolRegistration:
    """Tests for tool registration and discovery."""

    def test_frame_initiative_outcome_in_registry(self):
        """frame_initiative_outcome is registered in tool registry."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        assert "frame_initiative_outcome" in TOOL_REGISTRY

    def test_frame_initiative_intent_not_in_registry(self):
        """frame_initiative_intent is no longer in registry (renamed)."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        assert "frame_initiative_intent" not in TOOL_REGISTRY

    def test_tool_has_correct_annotations(self):
        """Tool has correct compliance annotations."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["frame_initiative_outcome"]
        assert tool.read_only_hint is False
        assert tool.destructive_hint is False
        assert tool.open_world_hint is False

    def test_tool_description_includes_preconditions(self):
        """Tool description includes CALL PRECONDITIONS."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["frame_initiative_outcome"]
        assert "CALL PRECONDITIONS" in tool.description

    def test_legacy_guidance_dict_exists(self):
        """_LEGACY_GUIDANCE dict exists for rollback."""
        from mcp_server.sharpen.tools.frame_initiative_intent import _LEGACY_GUIDANCE

        assert isinstance(_LEGACY_GUIDANCE, dict)
        assert "provenance_failed" in _LEGACY_GUIDANCE
        assert "empty_pain_verbatim" in _LEGACY_GUIDANCE
        assert "empty_observable_verbatim" in _LEGACY_GUIDANCE

    def test_tool_schema_has_provenance_fields(self):
        """Tool schema includes provenance fields (minus who_stated_by_user)."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["frame_initiative_outcome"]
        schema = tool.input_schema

        assert "user_pain_verbatim" in schema["properties"]
        assert "user_observable_verbatim" in schema["properties"]
        assert "why_reframed_from_observable" in schema["properties"]
        # Removed fields
        assert "who_stated_by_user" not in schema["properties"]  # Moved to audience step

    def test_tool_schema_has_who_as_required(self):
        """Tool schema has WHO as required (from prior step)."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["frame_initiative_outcome"]
        schema = tool.input_schema

        assert "who" in schema["properties"]
        assert "who" in schema["required"]
