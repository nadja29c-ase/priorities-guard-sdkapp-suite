"""
Tests for frame_initiative_audience tool.

Tests both pure logic (tool_logic.py) and handler (tools/frame_initiative_audience.py).
Structural validation only — semantic quality is the LLM's job.
"""

import pytest

from mcp_server.sharpen.tool_logic import validate_initiative_audience
from mcp_server.sharpen.tools.frame_initiative_audience import handle


# ============================================================================
# Pure Logic Tests (tool_logic.py) — Structural Validation
# ============================================================================


class TestValidateInitiativeAudience:
    """Tests for validate_initiative_audience function — structural validation only."""

    def test_empty_verbatim_rejected_first(self):
        """Empty verbatim is checked first, returns empty_verbatim error."""
        result = validate_initiative_audience(
            who="My team",
            user_who_verbatim="",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_verbatim"

    def test_whitespace_only_verbatim_rejected(self):
        """Whitespace-only verbatim is treated as empty."""
        result = validate_initiative_audience(
            who="My team",
            user_who_verbatim="   ",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_verbatim"

    def test_empty_who_rejected(self):
        """Empty WHO returns valid=False, error_type=empty_who."""
        result = validate_initiative_audience(
            who="",
            user_who_verbatim="my team",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_who"

    def test_whitespace_only_who_rejected(self):
        """Whitespace-only WHO is treated as empty."""
        result = validate_initiative_audience(
            who="   ",
            user_who_verbatim="my team",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_who"

    def test_none_who_rejected(self):
        """None WHO returns valid=False, error_type=empty_who."""
        result = validate_initiative_audience(
            who=None,
            user_who_verbatim="my team",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_who"

    def test_single_stakeholder_valid(self):
        """Single stakeholder with verbatim is valid."""
        result = validate_initiative_audience(
            who="New engineering hires",
            user_who_verbatim="new engineering hires",
        )

        assert result["valid"] is True
        assert result["who"] == "New engineering hires"
        assert result["user_who_verbatim"] == "new engineering hires"
        assert result["error_type"] is None

    def test_multiple_stakeholders_and_pattern_rejected(self):
        """WHO with 'and' pattern returns multiple_stakeholders error."""
        result = validate_initiative_audience(
            who="Engineers and their managers",
            user_who_verbatim="engineers and their managers",
        )

        assert result["valid"] is False
        assert result["error_type"] == "multiple_stakeholders"

    def test_multiple_stakeholders_comma_pattern_rejected(self):
        """WHO with comma pattern returns multiple_stakeholders error."""
        result = validate_initiative_audience(
            who="Engineers, designers, PMs",
            user_who_verbatim="engineers, designers, PMs",
        )

        assert result["valid"] is False
        assert result["error_type"] == "multiple_stakeholders"

    def test_multiple_stakeholders_or_pattern_rejected(self):
        """WHO with 'or' pattern returns multiple_stakeholders error."""
        result = validate_initiative_audience(
            who="The client or leadership",
            user_who_verbatim="the client or leadership",
        )

        assert result["valid"] is False
        assert result["error_type"] == "multiple_stakeholders"

    def test_composite_sales_and_marketing_valid(self):
        """Known composite 'Sales and Marketing' is valid."""
        result = validate_initiative_audience(
            who="Sales and Marketing team",
            user_who_verbatim="sales and marketing team",
        )

        assert result["valid"] is True
        assert result["error_type"] is None

    def test_composite_product_and_engineering_valid(self):
        """Known composite 'Product and Engineering' is valid."""
        result = validate_initiative_audience(
            who="Product and Engineering",
            user_who_verbatim="product and engineering",
        )

        assert result["valid"] is True
        assert result["error_type"] is None

    def test_ampersand_product_engineering_valid(self):
        """Ampersand 'Product & Engineering' is valid (compound role)."""
        result = validate_initiative_audience(
            who="Product & Engineering",
            user_who_verbatim="product & engineering",
        )

        assert result["valid"] is True
        assert result["error_type"] is None

    def test_ampersand_unlisted_valid(self):
        """Ampersand pattern not in composite list is still valid (compound role)."""
        result = validate_initiative_audience(
            who="Ops & Legal",
            user_who_verbatim="ops & legal",
        )

        assert result["valid"] is True
        assert result["error_type"] is None

    def test_slash_designers_developers_valid(self):
        """Slash pattern 'Designers/Developers' is valid (same group)."""
        result = validate_initiative_audience(
            who="Designers/Developers",
            user_who_verbatim="designers/developers",
        )

        assert result["valid"] is True
        assert result["error_type"] is None

    def test_slash_pattern_valid(self):
        """Slash pattern is valid — treated as compound role."""
        result = validate_initiative_audience(
            who="Frontend/Backend engineers",
            user_who_verbatim="frontend/backend engineers",
        )

        assert result["valid"] is True
        assert result["error_type"] is None

    def test_qualified_group_valid(self):
        """Single group with qualifier is valid."""
        result = validate_initiative_audience(
            who="senior engineers",
            user_who_verbatim="senior engineers",
        )

        assert result["valid"] is True
        assert result["error_type"] is None

    def test_qualified_group_with_attribute_valid(self):
        """Single group with attribute qualifier is valid."""
        result = validate_initiative_audience(
            who="freelancers with ADHD",
            user_who_verbatim="freelancers with ADHD",
        )

        assert result["valid"] is True
        assert result["error_type"] is None

    def test_distinct_groups_rejected(self):
        """Distinct beneficiary groups are rejected."""
        result = validate_initiative_audience(
            who="founders and customers",
            user_who_verbatim="founders and customers",
        )

        assert result["valid"] is False
        assert result["error_type"] == "multiple_stakeholders"

    def test_distinct_groups_team_and_client_rejected(self):
        """'The team and the client' is rejected as distinct groups."""
        result = validate_initiative_audience(
            who="The team and the client",
            user_who_verbatim="the team and the client",
        )

        assert result["valid"] is False
        assert result["error_type"] == "multiple_stakeholders"

    def test_whitespace_is_stripped(self):
        """Leading/trailing whitespace is stripped."""
        result = validate_initiative_audience(
            who="  New hires  ",
            user_who_verbatim="  new hires  ",
        )

        assert result["valid"] is True
        assert result["who"] == "New hires"
        assert result["user_who_verbatim"] == "new hires"


# ============================================================================
# Handler Tests (tools/frame_initiative_audience.py)
# ============================================================================


class TestFrameInitiativeAudienceHandler:
    """Tests for the MCP tool handler."""

    @pytest.mark.asyncio
    async def test_valid_input_returns_captured(self):
        """Valid input returns captured=True."""
        arguments = {
            "user_who_verbatim": "new engineering hires",
            "who": "New engineering hires",
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert result.structuredContent is not None
        assert result.structuredContent["captured"] is True

    @pytest.mark.asyncio
    async def test_valid_input_includes_provenance(self):
        """Valid input includes provenance with user_who_verbatim."""
        arguments = {
            "user_who_verbatim": "my team",
            "who": "My team",
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert "provenance" in result.structuredContent
        assert result.structuredContent["provenance"]["user_who_verbatim"] == "my team"

    @pytest.mark.asyncio
    async def test_valid_with_deferred_stakeholders(self):
        """Valid input with deferred stakeholders is captured."""
        arguments = {
            "user_who_verbatim": "engineers",
            "who": "Engineers",
            "deferred_stakeholders": ["managers", "executives"],
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert result.structuredContent["captured"] is True
        assert result.structuredContent["audience"]["who"] == "Engineers"
        assert result.structuredContent["audience"]["deferred_stakeholders"] == ["managers", "executives"]

    @pytest.mark.asyncio
    async def test_empty_verbatim_returns_educational_error(self):
        """Empty verbatim returns educational error with guidance."""
        arguments = {
            "user_who_verbatim": "",
            "who": "My team",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_verbatim"
        assert "assistant_guidance" in result.structuredContent
        assert result.structuredContent["assistant_guidance"]["action"] == "ASK_CLARIFYING"

    @pytest.mark.asyncio
    async def test_empty_who_returns_educational_error(self):
        """Empty WHO returns educational error with guidance."""
        arguments = {
            "user_who_verbatim": "my team",
            "who": "",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_who"
        assert "assistant_guidance" in result.structuredContent
        assert result.structuredContent["assistant_guidance"]["action"] == "ASK_CLARIFYING"

    @pytest.mark.asyncio
    async def test_multiple_stakeholders_returns_educational_error(self):
        """Multiple stakeholders returns educational error with guidance."""
        arguments = {
            "user_who_verbatim": "engineers and their managers",
            "who": "Engineers and their managers",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "multiple_stakeholders"
        assert "assistant_guidance" in result.structuredContent
        assert result.structuredContent["assistant_guidance"]["action"] == "ASK_CLARIFYING"

    @pytest.mark.asyncio
    async def test_error_response_has_standard_shape(self):
        """Error responses have standard shape with error and assistant_guidance."""
        arguments = {
            "user_who_verbatim": "",
            "who": "",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert "error" in result.structuredContent
        assert "assistant_guidance" in result.structuredContent
        assert "action" in result.structuredContent["assistant_guidance"]
        assert "instruction" in result.structuredContent["assistant_guidance"]

    @pytest.mark.asyncio
    async def test_success_has_proceed_to_outcome_action(self):
        """Success response has PROCEED_TO_OUTCOME action."""
        arguments = {
            "user_who_verbatim": "freelancers",
            "who": "Freelancers",
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert result.structuredContent["assistant_guidance"]["action"] == "PROCEED_TO_OUTCOME"

    @pytest.mark.asyncio
    async def test_success_has_text_content(self):
        """Success response has human-readable text content."""
        arguments = {
            "user_who_verbatim": "my team",
            "who": "My team",
        }

        result = await handle(arguments)

        assert len(result.content) == 1
        assert "Primary beneficiary captured" in result.content[0].text
        assert "My team" in result.content[0].text

    @pytest.mark.asyncio
    async def test_deferred_stakeholders_default_empty(self):
        """deferred_stakeholders defaults to empty array when not provided."""
        arguments = {
            "user_who_verbatim": "developers",
            "who": "Developers",
        }

        result = await handle(arguments)

        assert result.structuredContent["audience"]["deferred_stakeholders"] == []


# ============================================================================
# Integration Tests (Tool Registration)
# ============================================================================


class TestToolRegistration:
    """Tests for tool registration and discovery."""

    def test_frame_initiative_audience_in_registry(self):
        """frame_initiative_audience is registered in tool registry."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        assert "frame_initiative_audience" in TOOL_REGISTRY

    def test_tool_has_correct_annotations(self):
        """Tool has correct compliance annotations."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["frame_initiative_audience"]
        assert tool.read_only_hint is False
        assert tool.destructive_hint is False
        assert tool.open_world_hint is False

    def test_tool_description_includes_preconditions(self):
        """Tool description includes CALL PRECONDITIONS."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["frame_initiative_audience"]
        assert "CALL PRECONDITIONS" in tool.description

    def test_tool_description_includes_sharpen_mode_rules(self):
        """Tool description includes SHARPEN MODE BINDING RULES."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["frame_initiative_audience"]
        assert "SHARPEN MODE BINDING RULES" in tool.description

    def test_tool_schema_has_verbatim_field(self):
        """Tool schema has user_who_verbatim field as required."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["frame_initiative_audience"]
        schema = tool.input_schema

        assert "user_who_verbatim" in schema["properties"]
        assert "user_who_verbatim" in schema["required"]

    def test_tool_schema_has_who_field(self):
        """Tool schema has who field as required."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["frame_initiative_audience"]
        schema = tool.input_schema

        assert "who" in schema["properties"]
        assert "who" in schema["required"]

    def test_tool_schema_has_deferred_stakeholders_field(self):
        """Tool schema has deferred_stakeholders field as optional."""
        from mcp_server.sharpen.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["frame_initiative_audience"]
        schema = tool.input_schema

        assert "deferred_stakeholders" in schema["properties"]
        assert "deferred_stakeholders" not in schema["required"]
