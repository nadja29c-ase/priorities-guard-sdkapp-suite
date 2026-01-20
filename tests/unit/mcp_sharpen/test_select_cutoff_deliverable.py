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
            sculpted=None,
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
            sculpted=None,
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
            sculpted=None,
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
            sculpted=None,
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
            sculpted=None,
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
            sculpted=None,
            confidence="high",
        )

        assert result["valid"] is False
        assert result["error_type"] == "missing_deliverables"

    def test_no_selection_method_empty_string_rejects(self, valid_framing, valid_deliverables):
        """Empty selected_name with no sculpt is rejected as no_selection_method."""
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            selected_name="",
            sculpted=None,
            confidence="high",
        )

        assert result["valid"] is False
        assert result["error_type"] == "no_selection_method"

    def test_no_selection_method_none_rejects(self, valid_framing, valid_deliverables):
        """None selected_name with no sculpt is rejected as no_selection_method."""
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            selected_name=None,
            sculpted=None,
            confidence="high",
        )

        assert result["valid"] is False
        assert result["error_type"] == "no_selection_method"

    def test_selection_not_found_rejects(self, valid_framing, valid_deliverables):
        """Selection that doesn't match any deliverable is rejected."""
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            selected_name="Nonexistent Deliverable",
            sculpted=None,
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
            sculpted=None,
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
            sculpted=None,
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
            sculpted=None,
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
            sculpted=None,
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
            sculpted=None,
            confidence="high",
        )

        assert result["valid"] is True
        assert result["focus_deliverable"]["name"] == "Deployed REST API"

    def test_duplicate_deliverable_names_rejects(self, valid_framing):
        """Duplicate deliverable names are rejected to prevent data loss."""
        duplicate_deliverables = [
            {"name": "API", "description": "First API"},
            {"name": "Docs", "description": "Documentation"},
            {"name": "API", "description": "Second API"},  # Duplicate name
        ]

        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=duplicate_deliverables,
            selected_name="API",
            sculpted=None,
            confidence="high",
        )

        assert result["valid"] is False
        assert result["error_type"] == "duplicate_deliverable_names"


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
    async def test_duplicate_deliverable_names_returns_refuse_action(self, valid_framing):
        """Duplicate deliverable names returns action='REFUSE'."""
        arguments = {
            "initiative_framing": valid_framing,
            "confirmed_deliverables": [
                {"name": "API", "description": "First"},
                {"name": "API", "description": "Second"},
            ],
            "selected_deliverable_name": "API",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "duplicate_deliverable_names"
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
    async def test_guidance_uses_placeholder_and_provides_value(self, valid_framing, valid_deliverables):
        """Guidance uses [focus_name] placeholder; actual value in structuredContent."""
        arguments = {
            "initiative_framing": valid_framing,
            "confirmed_deliverables": valid_deliverables,
            "selected_deliverable_name": "Deployed REST API",
            "confidence": "high",
        }

        result = await handle(arguments)

        instruction = result.structuredContent["assistant_guidance"]["instruction"]
        # Static template uses placeholder
        assert "[focus_name]" in instruction
        # Actual value available in structuredContent for LLM to substitute
        assert result.structuredContent["focus_deliverable"]["name"] == "Deployed REST API"


# ============================================================================
# Sculpt Path - Logic Tests (tool_logic.py)
# ============================================================================


class TestValidateCutoffSelectionSculptPath:
    """Tests for validate_cutoff_selection sculpt path."""

    def test_sculpted_deliverable_returns_focus_and_deferred(self, valid_framing, valid_deliverables):
        """Valid sculpt returns focus_deliverable and deferred_deliverables."""
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            selected_name=None,
            sculpted={
                "name": "API with minimal docs",
                "description": "REST API and endpoint reference only",
                "replaces": ["Deployed REST API", "OpenAPI spec"],
            },
            confidence="high",
        )

        assert result["valid"] is True
        assert result["error_type"] is None
        assert result["focus_deliverable"]["name"] == "API with minimal docs"
        assert result["focus_deliverable"]["description"] == "REST API and endpoint reference only"
        # Integration tests should be deferred (not replaced)
        assert len(result["deferred_deliverables"]) == 1
        assert result["deferred_deliverables"][0]["name"] == "Integration tests"
        # Internal replaces for handler guidance
        assert result["_internal_replaces"] == ["Deployed REST API", "OpenAPI spec"]

    def test_both_methods_rejects(self, valid_framing, valid_deliverables):
        """Providing both selection and sculpt is rejected."""
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            selected_name="Deployed REST API",
            sculpted={
                "name": "Combined",
                "replaces": ["OpenAPI spec"],
            },
            confidence="high",
        )

        assert result["valid"] is False
        assert result["error_type"] == "both_selection_methods"

    def test_empty_sculpt_name_rejects(self, valid_framing, valid_deliverables):
        """Sculpt with empty name is rejected."""
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            selected_name=None,
            sculpted={
                "name": "",
                "replaces": ["Deployed REST API"],
            },
            confidence="high",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_sculpt_name"

    def test_empty_replaces_rejects(self, valid_framing, valid_deliverables):
        """Sculpt with empty replaces list is rejected."""
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            selected_name=None,
            sculpted={
                "name": "New Focus",
                "replaces": [],
            },
            confidence="high",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_replaces"

    def test_invalid_replaces_rejects(self, valid_framing, valid_deliverables):
        """Sculpt with non-existent names in replaces is rejected."""
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            selected_name=None,
            sculpted={
                "name": "New Focus",
                "replaces": ["Deployed REST API", "Nonexistent"],
            },
            confidence="high",
        )

        assert result["valid"] is False
        assert result["error_type"] == "invalid_replaces"
        assert "Nonexistent" in result["error_details"]

    def test_sculpt_replaces_all_returns_empty_deferred(self, valid_framing, valid_deliverables):
        """Sculpt that replaces all deliverables returns empty deferred list."""
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            selected_name=None,
            sculpted={
                "name": "Everything Bundle",
                "replaces": ["Deployed REST API", "OpenAPI spec", "Integration tests"],
            },
            confidence="high",
        )

        assert result["valid"] is True
        assert result["focus_deliverable"]["name"] == "Everything Bundle"
        assert result["deferred_deliverables"] == []

    def test_sculpt_description_optional(self, valid_framing, valid_deliverables):
        """Sculpt description is optional."""
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            selected_name=None,
            sculpted={
                "name": "API with docs",
                "replaces": ["Deployed REST API", "OpenAPI spec"],
            },
            confidence="high",
        )

        assert result["valid"] is True
        assert result["focus_deliverable"]["description"] == ""

    def test_sculpt_whitespace_name_trimmed(self, valid_framing, valid_deliverables):
        """Sculpt name with whitespace is trimmed."""
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            selected_name=None,
            sculpted={
                "name": "  Combined Focus  ",
                "replaces": ["Deployed REST API"],
            },
            confidence="high",
        )

        assert result["valid"] is True
        assert result["focus_deliverable"]["name"] == "Combined Focus"


# ============================================================================
# Sculpt Path - Handler Tests
# ============================================================================


class TestSelectCutoffHandlerSculptPath:
    """Tests for select_cutoff_deliverable handler with sculpting."""

    @pytest.mark.asyncio
    async def test_valid_sculpt_returns_proceed_to_step_3_action(self, valid_framing, valid_deliverables):
        """Valid sculpt returns action='PROCEED_TO_STEP_3'."""
        arguments = {
            "initiative_framing": valid_framing,
            "confirmed_deliverables": valid_deliverables,
            "sculpted_deliverable": {
                "name": "API with minimal docs",
                "description": "Combined scope",
                "replaces": ["Deployed REST API", "OpenAPI spec"],
            },
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert result.structuredContent["confirmed"] is True
        assert result.structuredContent["assistant_guidance"]["action"] == "PROCEED_TO_STEP_3"
        assert result.structuredContent["focus_deliverable"]["name"] == "API with minimal docs"

    @pytest.mark.asyncio
    async def test_sculpt_provides_replaces_in_structured_content(self, valid_framing, valid_deliverables):
        """Sculpt path includes replaces array in structuredContent for LLM."""
        arguments = {
            "initiative_framing": valid_framing,
            "confirmed_deliverables": valid_deliverables,
            "sculpted_deliverable": {
                "name": "API with minimal docs",
                "replaces": ["Deployed REST API", "OpenAPI spec"],
            },
            "confidence": "high",
        }

        result = await handle(arguments)

        # Replaces info available in structuredContent for LLM to mention
        assert "replaces" in result.structuredContent
        assert "Deployed REST API" in result.structuredContent["replaces"]
        assert "OpenAPI spec" in result.structuredContent["replaces"]

    @pytest.mark.asyncio
    async def test_both_methods_returns_clarifying_action(self, valid_framing, valid_deliverables):
        """Both selection and sculpt returns action='ASK_CLARIFYING'."""
        arguments = {
            "initiative_framing": valid_framing,
            "confirmed_deliverables": valid_deliverables,
            "selected_deliverable_name": "Deployed REST API",
            "sculpted_deliverable": {
                "name": "Combined",
                "replaces": ["OpenAPI spec"],
            },
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "both_selection_methods"
        assert result.structuredContent["assistant_guidance"]["action"] == "ASK_CLARIFYING"

    @pytest.mark.asyncio
    async def test_no_method_returns_clarifying_action(self, valid_framing, valid_deliverables):
        """Neither selection nor sculpt returns action='ASK_CLARIFYING'."""
        arguments = {
            "initiative_framing": valid_framing,
            "confirmed_deliverables": valid_deliverables,
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "no_selection_method"
        assert result.structuredContent["assistant_guidance"]["action"] == "ASK_CLARIFYING"

    @pytest.mark.asyncio
    async def test_invalid_replaces_returns_clarifying_action(self, valid_framing, valid_deliverables):
        """Invalid replaces names returns action='ASK_CLARIFYING'."""
        arguments = {
            "initiative_framing": valid_framing,
            "confirmed_deliverables": valid_deliverables,
            "sculpted_deliverable": {
                "name": "Combined",
                "replaces": ["Nonexistent Deliverable"],
            },
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "invalid_replaces"
        assert result.structuredContent["assistant_guidance"]["action"] == "ASK_CLARIFYING"
