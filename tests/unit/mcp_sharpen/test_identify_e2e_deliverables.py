"""
Tests for identify_e2e_deliverables tool.

Tests both pure logic (tool_logic.py) and handler (tools/identify_e2e_deliverables.py).
Structural validation only — semantic quality is the LLM's job.
"""

import pytest

from mcp_server.sharpen.tool_logic import validate_e2e_deliverables
from mcp_server.sharpen.tools.identify_e2e_deliverables import handle


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
    """Valid list of deliverables."""
    return [
        {"name": "Deployed REST API", "description": "With authentication"},
        {"name": "OpenAPI spec", "description": "For public endpoints"},
    ]


# ============================================================================
# Pure Logic Tests (tool_logic.py - validate_e2e_deliverables)
# ============================================================================


class TestValidateE2EDeliverables:
    """Tests for validate_e2e_deliverables function — structural validation only."""

    def test_valid_deliverables_returns_confirmed(self, valid_framing, valid_deliverables):
        """Valid framing + deliverables + confidence=high returns valid=True."""
        result = validate_e2e_deliverables(
            framing=valid_framing,
            deliverables=valid_deliverables,
            confidence="high",
        )

        assert result["valid"] is True
        assert result["error_type"] is None
        assert result["confirmed_deliverables"] is not None
        assert len(result["confirmed_deliverables"]) == 2
        assert result["count"] == 2

    def test_confidence_low_rejects(self, valid_framing, valid_deliverables):
        """Confidence='low' is rejected."""
        result = validate_e2e_deliverables(
            framing=valid_framing,
            deliverables=valid_deliverables,
            confidence="low",
        )

        assert result["valid"] is False
        assert result["error_type"] == "confidence_too_low"

    def test_confidence_medium_rejects(self, valid_framing, valid_deliverables):
        """Confidence='medium' is rejected."""
        result = validate_e2e_deliverables(
            framing=valid_framing,
            deliverables=valid_deliverables,
            confidence="medium",
        )

        assert result["valid"] is False
        assert result["error_type"] == "confidence_too_low"

    def test_missing_framing_rejects(self, valid_deliverables):
        """Framing=None is rejected."""
        result = validate_e2e_deliverables(
            framing=None,
            deliverables=valid_deliverables,
            confidence="high",
        )

        assert result["valid"] is False
        assert result["error_type"] == "missing_framing"

    def test_incomplete_framing_rejects(self, valid_deliverables):
        """Framing missing required field is rejected."""
        incomplete_framing = {
            "who": "Team",
            "what": "API",
            # Missing: constraint_type, constraint_value, definition_of_finished
        }

        result = validate_e2e_deliverables(
            framing=incomplete_framing,
            deliverables=valid_deliverables,
            confidence="high",
        )

        assert result["valid"] is False
        assert result["error_type"] == "missing_framing"

    def test_empty_deliverables_rejects(self, valid_framing):
        """Empty deliverables list is rejected."""
        result = validate_e2e_deliverables(
            framing=valid_framing,
            deliverables=[],
            confidence="high",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_deliverables"

    def test_none_deliverables_rejects(self, valid_framing):
        """Deliverables=None is rejected."""
        result = validate_e2e_deliverables(
            framing=valid_framing,
            deliverables=None,
            confidence="high",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_deliverables"

    def test_too_many_deliverables_rejects(self, valid_framing):
        """More than 10 deliverables is rejected."""
        many_deliverables = [{"name": f"Deliverable {i}"} for i in range(11)]

        result = validate_e2e_deliverables(
            framing=valid_framing,
            deliverables=many_deliverables,
            confidence="high",
        )

        assert result["valid"] is False
        assert result["error_type"] == "too_many_deliverables"
        assert result["count"] == 11

    def test_deliverable_missing_name_rejects(self, valid_framing):
        """Deliverable with empty name is rejected."""
        deliverables = [{"name": "", "description": "Some description"}]

        result = validate_e2e_deliverables(
            framing=valid_framing,
            deliverables=deliverables,
            confidence="high",
        )

        assert result["valid"] is False
        assert result["error_type"] == "invalid_deliverable"

    def test_deliverable_without_description_normalizes(self, valid_framing):
        """Deliverable without description is normalized to empty string."""
        deliverables = [{"name": "API"}]

        result = validate_e2e_deliverables(
            framing=valid_framing,
            deliverables=deliverables,
            confidence="high",
        )

        assert result["valid"] is True
        assert result["confirmed_deliverables"][0]["description"] == ""

    def test_max_10_deliverables_allowed(self, valid_framing):
        """Exactly 10 deliverables is allowed."""
        deliverables = [{"name": f"Deliverable {i}"} for i in range(10)]

        result = validate_e2e_deliverables(
            framing=valid_framing,
            deliverables=deliverables,
            confidence="high",
        )

        assert result["valid"] is True
        assert result["count"] == 10

    def test_whitespace_name_is_trimmed_and_rejected(self, valid_framing):
        """Whitespace-only name is trimmed and then rejected as empty."""
        deliverables = [{"name": "   "}]

        result = validate_e2e_deliverables(
            framing=valid_framing,
            deliverables=deliverables,
            confidence="high",
        )

        assert result["valid"] is False
        assert result["error_type"] == "invalid_deliverable"

    def test_description_whitespace_is_trimmed(self, valid_framing):
        """Description whitespace is trimmed."""
        deliverables = [{"name": "API", "description": "  With auth  "}]

        result = validate_e2e_deliverables(
            framing=valid_framing,
            deliverables=deliverables,
            confidence="high",
        )

        assert result["valid"] is True
        assert result["confirmed_deliverables"][0]["description"] == "With auth"


# ============================================================================
# Handler Tests (tools/identify_e2e_deliverables.py)
# ============================================================================


class TestIdentifyDeliverablesHandler:
    """Tests for identify_e2e_deliverables handler."""

    @pytest.mark.asyncio
    async def test_valid_input_returns_proceed_action(self, valid_framing, valid_deliverables):
        """Valid input returns action='PROCEED_TO_CUTOFF'."""
        arguments = {
            "initiative_framing": valid_framing,
            "candidate_deliverables": valid_deliverables,
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert result.structuredContent["confirmed"] is True
        assert result.structuredContent["assistant_guidance"]["action"] == "PROCEED_TO_CUTOFF"

    @pytest.mark.asyncio
    async def test_low_confidence_returns_clarifying_action(self, valid_framing, valid_deliverables):
        """Low confidence returns action='ASK_CLARIFYING'."""
        arguments = {
            "initiative_framing": valid_framing,
            "candidate_deliverables": valid_deliverables,
            "confidence": "low",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "confidence_too_low"
        assert result.structuredContent["assistant_guidance"]["action"] == "ASK_CLARIFYING"

    @pytest.mark.asyncio
    async def test_missing_framing_returns_refuse_action(self, valid_deliverables):
        """Missing framing returns action='REFUSE'."""
        arguments = {
            "initiative_framing": None,
            "candidate_deliverables": valid_deliverables,
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "missing_framing"
        assert result.structuredContent["assistant_guidance"]["action"] == "REFUSE"

    @pytest.mark.asyncio
    async def test_too_many_deliverables_returns_refuse_action(self, valid_framing):
        """Too many deliverables returns action='REFUSE'."""
        many_deliverables = [{"name": f"Deliverable {i}"} for i in range(11)]
        arguments = {
            "initiative_framing": valid_framing,
            "candidate_deliverables": many_deliverables,
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "too_many_deliverables"
        assert result.structuredContent["assistant_guidance"]["action"] == "REFUSE"

    @pytest.mark.asyncio
    async def test_empty_deliverables_returns_clarifying_action(self, valid_framing):
        """Empty deliverables returns action='ASK_CLARIFYING'."""
        arguments = {
            "initiative_framing": valid_framing,
            "candidate_deliverables": [],
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_deliverables"
        assert result.structuredContent["assistant_guidance"]["action"] == "ASK_CLARIFYING"

    @pytest.mark.asyncio
    async def test_confirmed_deliverables_structure(self, valid_framing, valid_deliverables):
        """Confirmed output has correct structure."""
        arguments = {
            "initiative_framing": valid_framing,
            "candidate_deliverables": valid_deliverables,
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is not True
        sc = result.structuredContent
        assert "confirmed_deliverables" in sc
        assert "count" in sc
        assert "confidence" in sc
        assert sc["confidence"] == "high"
        assert sc["count"] == 2
