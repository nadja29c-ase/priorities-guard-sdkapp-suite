"""
Tests for select_cutoff_deliverable tool.

Tests both pure logic (tool_logic.py) and handler (tools/select_cutoff_deliverable.py).
Structural validation only — semantic quality is the LLM's job.
"""

import pytest

from mcp_server.sharpen.tool_logic import validate_cutoff_selection
from mcp_server.sharpen.tools.select_cutoff_deliverable import handle


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def valid_framing():
    """Valid initiative framing from Step 1."""
    return {
        "who": "Engineering team",
        "what": "A new API",
        "why": "To serve mobile clients",
        "constraint_type": "time",
        "constraint_value": "by March 15",
        "definition_of_finished": "API deployed and accessible",
    }


@pytest.fixture
def valid_deliverables():
    """Valid confirmed deliverables from Step 2.1."""
    return [
        {"name": "Deployed REST API", "description": "With authentication"},
        {"name": "OpenAPI spec", "description": "For public endpoints"},
        {"name": "Integration tests", "description": "For all endpoints"},
    ]


# ============================================================================
# Pure Logic Tests (tool_logic.py - validate_cutoff_selection)
# ============================================================================


class TestValidateCutoffSelection:
    """Tests for validate_cutoff_selection function — structural validation only."""

    def test_valid_selection_returns_focus_and_deferred(self, valid_framing, valid_deliverables):
        """Valid selection returns focus_deliverable and deferred_deliverables."""
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            selected_name="Deployed REST API",
            confidence="high",
        )

        assert result["valid"] is True
        assert result["error_type"] is None
        assert result["focus_deliverable"]["name"] == "Deployed REST API"
        assert result["focus_deliverable"]["description"] == "With authentication"
        assert len(result["deferred_deliverables"]) == 2

    def test_confidence_low_rejects(self, valid_framing, valid_deliverables):
        """Confidence='low' is rejected."""
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            selected_name="Deployed REST API",
            confidence="low",
        )

        assert result["valid"] is False
        assert result["error_type"] == "confidence_too_low"

    def test_confidence_medium_rejects(self, valid_framing, valid_deliverables):
        """Confidence='medium' is rejected."""
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            selected_name="Deployed REST API",
            confidence="medium",
        )

        assert result["valid"] is False
        assert result["error_type"] == "confidence_too_low"

    def test_missing_framing_rejects(self, valid_deliverables):
        """Framing=None is rejected."""
        result = validate_cutoff_selection(
            framing=None,
            deliverables=valid_deliverables,
            selected_name="Deployed REST API",
            confidence="high",
        )

        assert result["valid"] is False
        assert result["error_type"] == "missing_framing"

    def test_missing_deliverables_rejects(self, valid_framing):
        """Deliverables=None is rejected."""
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=None,
            selected_name="Deployed REST API",
            confidence="high",
        )

        assert result["valid"] is False
        assert result["error_type"] == "missing_deliverables"

    def test_empty_deliverables_rejects(self, valid_framing):
        """Empty deliverables list is rejected."""
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=[],
            selected_name="Deployed REST API",
            confidence="high",
        )

        assert result["valid"] is False
        assert result["error_type"] == "missing_deliverables"

    def test_empty_selection_rejects(self, valid_framing, valid_deliverables):
        """Empty selected_name is rejected."""
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            selected_name="",
            confidence="high",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_selection"

    def test_none_selection_rejects(self, valid_framing, valid_deliverables):
        """None selected_name is rejected."""
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            selected_name=None,
            confidence="high",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_selection"

    def test_selection_not_found_rejects(self, valid_framing, valid_deliverables):
        """Selection that doesn't match any deliverable is rejected."""
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            selected_name="Nonexistent Deliverable",
            confidence="high",
        )

        assert result["valid"] is False
        assert result["error_type"] == "selection_not_found"

    def test_selection_is_case_sensitive(self, valid_framing, valid_deliverables):
        """Selection is case-sensitive."""
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            selected_name="deployed rest api",  # lowercase
            confidence="high",
        )

        assert result["valid"] is False
        assert result["error_type"] == "selection_not_found"

    def test_single_deliverable_selection_returns_empty_deferred(self, valid_framing):
        """Single deliverable selected returns empty deferred list."""
        single_deliverable = [{"name": "Only Deliverable", "description": "The only one"}]

        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=single_deliverable,
            selected_name="Only Deliverable",
            confidence="high",
        )

        assert result["valid"] is True
        assert result["focus_deliverable"]["name"] == "Only Deliverable"
        assert result["deferred_deliverables"] == []

    def test_focus_deliverable_preserves_description(self, valid_framing, valid_deliverables):
        """Focus deliverable preserves description from input."""
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            selected_name="OpenAPI spec",
            confidence="high",
        )

        assert result["valid"] is True
        assert result["focus_deliverable"]["description"] == "For public endpoints"

    def test_deferred_deliverables_preserve_descriptions(self, valid_framing, valid_deliverables):
        """Deferred deliverables preserve descriptions from input."""
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            selected_name="Deployed REST API",
            confidence="high",
        )

        assert result["valid"] is True
        deferred_names = [d["name"] for d in result["deferred_deliverables"]]
        assert "OpenAPI spec" in deferred_names
        assert "Integration tests" in deferred_names

    def test_whitespace_selection_is_trimmed(self, valid_framing, valid_deliverables):
        """Selection with leading/trailing whitespace is trimmed."""
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            selected_name="  Deployed REST API  ",
            confidence="high",
        )

        assert result["valid"] is True
        assert result["focus_deliverable"]["name"] == "Deployed REST API"


# ============================================================================
# Handler Tests (tools/select_cutoff_deliverable.py)
# ============================================================================


class TestSelectCutoffHandler:
    """Tests for select_cutoff_deliverable handler."""

    @pytest.mark.asyncio
    async def test_valid_input_returns_proceed_to_step_3_action(self, valid_framing, valid_deliverables):
        """Valid input returns action='PROCEED_TO_STEP_3'."""
        arguments = {
            "initiative_framing": valid_framing,
            "confirmed_deliverables": valid_deliverables,
            "selected_deliverable_name": "Deployed REST API",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert result.structuredContent["confirmed"] is True
        assert result.structuredContent["assistant_guidance"]["action"] == "PROCEED_TO_STEP_3"

    @pytest.mark.asyncio
    async def test_low_confidence_returns_clarifying_action(self, valid_framing, valid_deliverables):
        """Low confidence returns action='ASK_CLARIFYING'."""
        arguments = {
            "initiative_framing": valid_framing,
            "confirmed_deliverables": valid_deliverables,
            "selected_deliverable_name": "Deployed REST API",
            "confidence": "low",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "confidence_too_low"
        assert result.structuredContent["assistant_guidance"]["action"] == "ASK_CLARIFYING"

    @pytest.mark.asyncio
    async def test_selection_not_found_returns_clarifying_action(self, valid_framing, valid_deliverables):
        """Selection not found returns action='ASK_CLARIFYING'."""
        arguments = {
            "initiative_framing": valid_framing,
            "confirmed_deliverables": valid_deliverables,
            "selected_deliverable_name": "Nonexistent",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "selection_not_found"
        assert result.structuredContent["assistant_guidance"]["action"] == "ASK_CLARIFYING"

    @pytest.mark.asyncio
    async def test_missing_framing_returns_refuse_action(self, valid_deliverables):
        """Missing framing returns action='REFUSE'."""
        arguments = {
            "initiative_framing": None,
            "confirmed_deliverables": valid_deliverables,
            "selected_deliverable_name": "Deployed REST API",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "missing_framing"
        assert result.structuredContent["assistant_guidance"]["action"] == "REFUSE"

    @pytest.mark.asyncio
    async def test_missing_deliverables_returns_refuse_action(self, valid_framing):
        """Missing deliverables returns action='REFUSE'."""
        arguments = {
            "initiative_framing": valid_framing,
            "confirmed_deliverables": None,
            "selected_deliverable_name": "Deployed REST API",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "missing_deliverables"
        assert result.structuredContent["assistant_guidance"]["action"] == "REFUSE"

    @pytest.mark.asyncio
    async def test_confirmed_output_structure(self, valid_framing, valid_deliverables):
        """Confirmed output has correct structure."""
        arguments = {
            "initiative_framing": valid_framing,
            "confirmed_deliverables": valid_deliverables,
            "selected_deliverable_name": "Deployed REST API",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is not True
        sc = result.structuredContent
        assert "focus_deliverable" in sc
        assert "scope_boundary" in sc
        assert sc["scope_boundary"] == "explicit"
        assert "deferred_deliverables" in sc
        assert "confidence" in sc
        assert sc["confidence"] == "high"

    @pytest.mark.asyncio
    async def test_guidance_includes_focus_deliverable_name(self, valid_framing, valid_deliverables):
        """Guidance instruction includes the focus deliverable name."""
        arguments = {
            "initiative_framing": valid_framing,
            "confirmed_deliverables": valid_deliverables,
            "selected_deliverable_name": "Deployed REST API",
            "confidence": "high",
        }

        result = await handle(arguments)

        instruction = result.structuredContent["assistant_guidance"]["instruction"]
        assert "Deployed REST API" in instruction
