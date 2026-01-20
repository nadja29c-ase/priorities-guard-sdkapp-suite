"""
Tests for commit_week_deliverable tool.

Tests both pure logic (tool_logic.py) and handler (tools/commit_week_deliverable.py).
Structural validation only — semantic quality is the LLM's job.
"""

import pytest

from mcp_server.sharpen.tool_logic import validate_good_enough
from mcp_server.sharpen.tools.commit_week_deliverable import handle


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def valid_framing():
    """Valid initiative framing from Step 1."""
    return {
        "who": "New engineering hires",
        "what": "A first-week onboarding checklist",
        "why": "So they can start contributing without constant interruptions",
        "constraint_type": "capacity",
        "constraint_value": "3 hours per week",
    }


@pytest.fixture
def valid_focus():
    """Valid focus deliverable from Step 2."""
    return {
        "name": "First-week checklist",
        "description": "Onboarding checklist for new hires",
    }


@pytest.fixture
def valid_good_enough():
    """Valid good enough definition."""
    return "Draft checklist with all 5 days and at least one task per day"


# ============================================================================
# Pure Logic Tests (tool_logic.py - validate_good_enough)
# ============================================================================


class TestValidateGoodEnough:
    """Tests for validate_good_enough function — structural validation only."""

    def test_valid_input_returns_sharpened_scope(self, valid_framing, valid_focus, valid_good_enough):
        """Valid input returns sharpened_scope."""
        result = validate_good_enough(
            framing=valid_framing,
            focus=valid_focus,
            good_enough=valid_good_enough,
            confidence="high",
        )

        assert result["valid"] is True
        assert result["error_type"] is None
        assert result["sharpened_scope"]["initiative_framing"] == valid_framing
        assert result["sharpened_scope"]["focus_deliverable"] == valid_focus
        assert result["sharpened_scope"]["good_enough_definition"] == valid_good_enough

    def test_confidence_low_rejects(self, valid_framing, valid_focus, valid_good_enough):
        """Confidence='low' is rejected."""
        result = validate_good_enough(
            framing=valid_framing,
            focus=valid_focus,
            good_enough=valid_good_enough,
            confidence="low",
        )

        assert result["valid"] is False
        assert result["error_type"] == "confidence_too_low"

    def test_confidence_medium_rejects(self, valid_framing, valid_focus, valid_good_enough):
        """Confidence='medium' is rejected."""
        result = validate_good_enough(
            framing=valid_framing,
            focus=valid_focus,
            good_enough=valid_good_enough,
            confidence="medium",
        )

        assert result["valid"] is False
        assert result["error_type"] == "confidence_too_low"

    def test_missing_framing_rejects(self, valid_focus, valid_good_enough):
        """Framing=None is rejected."""
        result = validate_good_enough(
            framing=None,
            focus=valid_focus,
            good_enough=valid_good_enough,
            confidence="high",
        )

        assert result["valid"] is False
        assert result["error_type"] == "missing_framing"

    def test_incomplete_framing_rejects(self, valid_focus, valid_good_enough):
        """Incomplete framing is rejected."""
        incomplete_framing = {
            "who": "Someone",
            "what": "Something",
            # Missing why, constraint_type, constraint_value
        }
        result = validate_good_enough(
            framing=incomplete_framing,
            focus=valid_focus,
            good_enough=valid_good_enough,
            confidence="high",
        )

        assert result["valid"] is False
        assert result["error_type"] == "missing_framing"
        assert "constraint_type" in result["error_details"]

    def test_missing_focus_rejects(self, valid_framing, valid_good_enough):
        """Focus=None is rejected."""
        result = validate_good_enough(
            framing=valid_framing,
            focus=None,
            good_enough=valid_good_enough,
            confidence="high",
        )

        assert result["valid"] is False
        assert result["error_type"] == "missing_focus"

    def test_focus_without_name_rejects(self, valid_framing, valid_good_enough):
        """Focus without name is rejected."""
        result = validate_good_enough(
            framing=valid_framing,
            focus={"description": "Some desc"},
            good_enough=valid_good_enough,
            confidence="high",
        )

        assert result["valid"] is False
        assert result["error_type"] == "missing_focus"

    def test_empty_good_enough_rejects(self, valid_framing, valid_focus):
        """Empty good enough is rejected."""
        result = validate_good_enough(
            framing=valid_framing,
            focus=valid_focus,
            good_enough="",
            confidence="high",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_definition"

    def test_whitespace_good_enough_rejects(self, valid_framing, valid_focus):
        """Whitespace-only good enough is rejected."""
        result = validate_good_enough(
            framing=valid_framing,
            focus=valid_focus,
            good_enough="   ",
            confidence="high",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_definition"

    def test_none_good_enough_rejects(self, valid_framing, valid_focus):
        """None good enough is rejected."""
        result = validate_good_enough(
            framing=valid_framing,
            focus=valid_focus,
            good_enough=None,
            confidence="high",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_definition"

    def test_good_enough_trimmed(self, valid_framing, valid_focus):
        """Good enough with whitespace is trimmed."""
        result = validate_good_enough(
            framing=valid_framing,
            focus=valid_focus,
            good_enough="  Just the contacts  ",
            confidence="high",
        )

        assert result["valid"] is True
        assert result["sharpened_scope"]["good_enough_definition"] == "Just the contacts"


# ============================================================================
# Handler Tests (tools/commit_good_enough.py)
# ============================================================================


class TestCommitGoodEnoughHandler:
    """Tests for commit_good_enough handler."""

    @pytest.mark.asyncio
    async def test_valid_input_returns_sharpen_complete_action(
        self, valid_framing, valid_focus, valid_good_enough
    ):
        """Valid input returns action='SHARPEN_COMPLETE'."""
        arguments = {
            "initiative_framing": valid_framing,
            "focus_deliverable": valid_focus,
            "good_enough_definition": valid_good_enough,
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert result.structuredContent["confirmed"] is True
        assert result.structuredContent["assistant_guidance"]["action"] == "SHARPEN_COMPLETE"

    @pytest.mark.asyncio
    async def test_low_confidence_returns_clarifying_action(
        self, valid_framing, valid_focus, valid_good_enough
    ):
        """Low confidence returns action='ASK_CLARIFYING'."""
        arguments = {
            "initiative_framing": valid_framing,
            "focus_deliverable": valid_focus,
            "good_enough_definition": valid_good_enough,
            "confidence": "low",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "confidence_too_low"
        assert result.structuredContent["assistant_guidance"]["action"] == "ASK_CLARIFYING"

    @pytest.mark.asyncio
    async def test_missing_framing_returns_refuse_action(self, valid_focus, valid_good_enough):
        """Missing framing returns action='REFUSE'."""
        arguments = {
            "initiative_framing": None,
            "focus_deliverable": valid_focus,
            "good_enough_definition": valid_good_enough,
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "missing_framing"
        assert result.structuredContent["assistant_guidance"]["action"] == "REFUSE"

    @pytest.mark.asyncio
    async def test_missing_focus_returns_refuse_action(self, valid_framing, valid_good_enough):
        """Missing focus returns action='REFUSE'."""
        arguments = {
            "initiative_framing": valid_framing,
            "focus_deliverable": None,
            "good_enough_definition": valid_good_enough,
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "missing_focus"
        assert result.structuredContent["assistant_guidance"]["action"] == "REFUSE"

    @pytest.mark.asyncio
    async def test_empty_definition_returns_clarifying_action(self, valid_framing, valid_focus):
        """Empty definition returns action='ASK_CLARIFYING'."""
        arguments = {
            "initiative_framing": valid_framing,
            "focus_deliverable": valid_focus,
            "good_enough_definition": "",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_definition"
        assert result.structuredContent["assistant_guidance"]["action"] == "ASK_CLARIFYING"

    @pytest.mark.asyncio
    async def test_confirmed_output_structure(
        self, valid_framing, valid_focus, valid_good_enough
    ):
        """Confirmed output has correct structure."""
        arguments = {
            "initiative_framing": valid_framing,
            "focus_deliverable": valid_focus,
            "good_enough_definition": valid_good_enough,
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is not True
        sc = result.structuredContent
        assert "sharpened_scope" in sc
        assert "confidence" in sc
        assert sc["confidence"] == "high"
        assert "confirmed" in sc
        assert sc["confirmed"] is True

    @pytest.mark.asyncio
    async def test_sharpened_scope_includes_all_data(
        self, valid_framing, valid_focus, valid_good_enough
    ):
        """Sharpened scope includes framing, focus, and good enough."""
        arguments = {
            "initiative_framing": valid_framing,
            "focus_deliverable": valid_focus,
            "good_enough_definition": valid_good_enough,
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is not True
        sharpened = result.structuredContent["sharpened_scope"]
        assert "initiative_framing" in sharpened
        assert "focus_deliverable" in sharpened
        assert "good_enough_definition" in sharpened
        assert sharpened["focus_deliverable"]["name"] == "First-week checklist"

    @pytest.mark.asyncio
    async def test_guidance_instruction_says_sharpen_complete(
        self, valid_framing, valid_focus, valid_good_enough
    ):
        """Guidance instruction includes SHARPEN COMPLETE."""
        arguments = {
            "initiative_framing": valid_framing,
            "focus_deliverable": valid_focus,
            "good_enough_definition": valid_good_enough,
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is not True
        instruction = result.structuredContent["assistant_guidance"]["instruction"]
        assert "SHARPEN COMPLETE" in instruction

    @pytest.mark.asyncio
    async def test_text_content_includes_focus_and_good_enough(
        self, valid_framing, valid_focus, valid_good_enough
    ):
        """Text content includes focus deliverable and good enough."""
        arguments = {
            "initiative_framing": valid_framing,
            "focus_deliverable": valid_focus,
            "good_enough_definition": valid_good_enough,
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is not True
        text = result.content[0].text
        assert "First-week checklist" in text
        assert "5 days" in text

    @pytest.mark.asyncio
    async def test_pydantic_validation_error_handled(self, valid_framing):
        """Invalid pydantic input returns validation error."""
        arguments = {
            "initiative_framing": valid_framing,
            "focus_deliverable": "not an object",  # Should be dict
            "good_enough_definition": "valid definition",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "validation_error"
