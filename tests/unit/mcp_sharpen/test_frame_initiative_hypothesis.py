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


# ============================================================================
# Provenance Validation Tests (tool_logic.py)
# ============================================================================


class TestValidateHypothesisProvenance:
    """Tests for validate_hypothesis_provenance function."""

    def test_all_true_with_verbatim_valid(self):
        """All provenance flags True with verbatim is valid."""
        from mcp_server.sharpen.tool_logic import validate_hypothesis_provenance

        result = validate_hypothesis_provenance(
            what_stated_by_user=True,
            user_what_verbatim="A checklist they can follow",
        )

        assert result["valid"] is True
        assert result["failed_checks"] == []

    def test_empty_verbatim_rejects(self):
        """Empty verbatim is rejected — WHAT must exist."""
        from mcp_server.sharpen.tool_logic import validate_hypothesis_provenance

        result = validate_hypothesis_provenance(
            what_stated_by_user=True,
            user_what_verbatim="",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_verbatim"

    def test_what_not_stated_rejects(self):
        """what_stated_by_user=False is rejected."""
        from mcp_server.sharpen.tool_logic import validate_hypothesis_provenance

        result = validate_hypothesis_provenance(
            what_stated_by_user=False,
            user_what_verbatim="Some what",
        )

        assert result["valid"] is False
        assert "what_stated_by_user" in result["failed_checks"]

    def test_what_not_stated_rejected(self):
        """what_stated_by_user=False is rejected."""
        from mcp_server.sharpen.tool_logic import validate_hypothesis_provenance

        result = validate_hypothesis_provenance(
            what_stated_by_user=False,
            user_what_verbatim="Some what",
        )

        assert result["valid"] is False
        assert "what_stated_by_user" in result["failed_checks"]

    def test_whitespace_only_verbatim_rejects(self):
        """Whitespace-only verbatim is treated as empty."""
        from mcp_server.sharpen.tool_logic import validate_hypothesis_provenance

        result = validate_hypothesis_provenance(
            what_stated_by_user=True,
            user_what_verbatim="   ",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_verbatim"


class TestFrameHypothesisHandlerProvenance:
    """Tests for handler provenance validation."""

    @pytest.mark.asyncio
    async def test_all_provenance_true_succeeds(self):
        """All provenance flags True with verbatim succeeds."""
        arguments = {
            "who": "New engineering hires",
            "why": "So they can find answers without interrupting others",
            "user_what_verbatim": "A checklist they can follow in their first week",
            "what_derived_from_verbatim": "A first-week checklist",
            "what_stated_by_user": True,
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert result.structuredContent["captured"] is True
        assert "provenance" in result.structuredContent

    @pytest.mark.asyncio
    async def test_provenance_false_rejects(self):
        """what_stated_by_user=False is rejected."""
        arguments = {
            "who": "New engineering hires",
            "why": "So they can contribute",
            "user_what_verbatim": "Some solution",
            "what_derived_from_verbatim": "A solution",
            "what_stated_by_user": False,
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "provenance_failed"

    @pytest.mark.asyncio
    async def test_empty_verbatim_rejects(self):
        """Empty verbatim is rejected."""
        arguments = {
            "who": "New engineering hires",
            "why": "So they can contribute",
            "user_what_verbatim": "",
            "what_derived_from_verbatim": "A solution",
            "what_stated_by_user": True,
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_verbatim"

    @pytest.mark.asyncio
    async def test_provenance_failure_returns_guidance(self):
        """Provenance failure returns actionable guidance."""
        arguments = {
            "who": "Someone",
            "why": "For reasons",
            "user_what_verbatim": "Something",
            "what_derived_from_verbatim": "A thing",
            "what_stated_by_user": False,
        }

        result = await handle(arguments)

        assert "assistant_guidance" in result.structuredContent
        instruction = result.structuredContent["assistant_guidance"]["instruction"]
        assert "SHARPEN MODE STILL BINDING" in instruction

    @pytest.mark.asyncio
    async def test_empty_verbatim_returns_specific_guidance(self):
        """Empty verbatim returns specific guidance about getting WHAT."""
        arguments = {
            "who": "Team",
            "why": "Some reason",
            "user_what_verbatim": "",
            "what_derived_from_verbatim": "Something",
            "what_stated_by_user": True,
        }

        result = await handle(arguments)

        instruction = result.structuredContent["assistant_guidance"]["instruction"]
        assert "user_what_verbatim is empty" in instruction

    @pytest.mark.asyncio
    async def test_failed_checks_listed_in_response(self):
        """Failed provenance checks are listed in response."""
        arguments = {
            "who": "Team",
            "why": "Reason",
            "user_what_verbatim": "What",
            "what_derived_from_verbatim": "Thing",
            "what_stated_by_user": False,
        }

        result = await handle(arguments)

        assert "failed_checks" in result.structuredContent
        assert "what_stated_by_user" in result.structuredContent["failed_checks"]

    @pytest.mark.asyncio
    async def test_valid_input_includes_provenance(self):
        """Valid input includes provenance object in response."""
        arguments = {
            "who": "New hires",
            "why": "So they can navigate independently",
            "user_what_verbatim": "An onboarding guide",
            "what_derived_from_verbatim": "An onboarding guide",
            "what_stated_by_user": True,
        }

        result = await handle(arguments)

        assert "provenance" in result.structuredContent
        provenance = result.structuredContent["provenance"]
        assert provenance["user_what_verbatim"] == "An onboarding guide"
        assert provenance["what_stated_by_user"] is True


class TestFrameHypothesisHandler:
    """Tests for frame_initiative_hypothesis handler."""

    @pytest.mark.asyncio
    async def test_valid_input_returns_proceed_action(self):
        """Valid input returns action='PROCEED_TO_CONSTRAINTS'."""
        arguments = {
            "who": "New engineering hires",
            "why": "So they can contribute without interruptions",
            "user_what_verbatim": "A first-week checklist",
            "what_derived_from_verbatim": "A first-week checklist",
            "what_stated_by_user": True,
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert result.structuredContent["captured"] is True
        assert result.structuredContent["assistant_guidance"]["action"] == "PROCEED_TO_CONSTRAINTS"

    @pytest.mark.asyncio
    async def test_missing_prior_step_returns_refuse_action(self):
        """Missing prior step returns action='REFUSE'."""
        arguments = {
            "who": "",
            "why": "",
            "user_what_verbatim": "A checklist",
            "what_derived_from_verbatim": "A checklist",
            "what_stated_by_user": True,
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
            "user_what_verbatim": "Something",
            "what_derived_from_verbatim": "",
            "what_stated_by_user": True,
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
            "user_what_verbatim": "A first-week checklist",
            "what_derived_from_verbatim": "A first-week checklist",
            "what_stated_by_user": True,
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
            "user_what_verbatim": "A checklist",
            "what_derived_from_verbatim": "A checklist",
            "what_stated_by_user": True,
        }

        result = await handle(arguments)

        assert len(result.content) == 1
        assert "Hypothesis captured" in result.content[0].text
        assert "New engineering hires" in result.content[0].text
        assert "A checklist" in result.content[0].text


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
        assert "frame_initiative_outcome" in tool.description
