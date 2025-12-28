"""
Unit tests for formulate_problem tool.

Tests both the pure tool_logic function and the tool handler.
"""

import pytest
from mcp_server.unpack.tool_logic import formulate_problem
from mcp_server.unpack.tools.formulate_problem import handle


class TestFormulateProblemLogic:
    """Tests for the pure formulate_problem function."""

    def test_all_components_present_high_confidence(self):
        """All 4 components present and detailed -> high confidence."""
        result = formulate_problem(
            actor="I",
            goal="grow my freelance business",
            obstacle="I keep taking low-paying projects because I'm scared to say no",
            cost="time and energy that could go to better clients",
        )

        assert result["confidence"] == "high"
        assert result["formulated_problem"]["actor"] == "I"
        assert result["formulated_problem"]["goal"] == "grow my freelance business"
        assert "keep taking low-paying projects" in result["formulated_problem"]["obstacle"]
        assert "time and energy" in result["formulated_problem"]["cost"]
        assert result["needs_clarification"] is False
        assert "clarify" not in result

    def test_one_weak_component_medium_confidence(self):
        """One component weak (< 5 chars) -> medium confidence."""
        result = formulate_problem(
            actor="I",
            goal="get promoted",
            obstacle="my manager doesn't notice my work",
            cost="sad",  # Too short
        )

        assert result["confidence"] == "medium"
        assert result["needs_clarification"] is True
        assert result["clarify"]["type"] == "COST"

    def test_missing_goal_low_confidence(self):
        """Missing goal -> low confidence with clarify type."""
        result = formulate_problem(
            actor="I",
            goal="",  # Missing
            obstacle="things keep getting in the way",
            cost="stress",
        )

        assert result["confidence"] == "low"
        assert result["needs_clarification"] is True
        assert result["clarify"]["type"] == "GOAL"
        # Full statement should have placeholder
        assert "[goal unclear]" in result["formulated_problem"]["full_statement"]

    def test_missing_obstacle_low_confidence(self):
        """Missing obstacle -> low confidence with clarify type."""
        result = formulate_problem(
            actor="I",
            goal="be more productive",
            obstacle="",  # Missing
            cost="wasted time",
        )

        assert result["confidence"] == "low"
        assert result["needs_clarification"] is True
        assert result["clarify"]["type"] == "OBSTACLE"

    def test_missing_cost_medium_confidence(self):
        """Missing cost but other 3 present -> medium confidence."""
        result = formulate_problem(
            actor="I",
            goal="launch my product this quarter",
            obstacle="I keep getting pulled into meetings",
            cost="",  # Missing
        )

        assert result["confidence"] == "medium"
        assert result["needs_clarification"] is True
        assert result["clarify"]["type"] == "COST"

    def test_multiple_missing_low_confidence(self):
        """Multiple components missing -> low confidence."""
        result = formulate_problem(
            actor="I",
            goal="",
            obstacle="",
            cost="",
        )

        assert result["confidence"] == "low"
        assert result["needs_clarification"] is True
        assert "clarify" in result

    def test_full_statement_format(self):
        """Full statement follows expected format."""
        result = formulate_problem(
            actor="my team",
            goal="ship on time",
            obstacle="scope keeps expanding",
            cost="missed deadlines and burnout",
        )

        full = result["formulated_problem"]["full_statement"]
        assert full.startswith("my team is trying to")
        assert "ship on time" in full
        assert "scope keeps expanding" in full
        assert "missed deadlines and burnout" in full

    def test_default_actor_when_unclear(self):
        """Empty actor defaults to 'I'."""
        result = formulate_problem(
            actor="",
            goal="make progress",
            obstacle="distractions",
            cost="frustration",
        )

        assert result["formulated_problem"]["actor"] == "I"
        assert result["formulated_problem"]["full_statement"].startswith("I am trying to")

    def test_whitespace_only_treated_as_empty(self):
        """Whitespace-only input treated as empty."""
        result = formulate_problem(
            actor="   ",
            goal="   ",
            obstacle="things",
            cost="stuff",
        )

        assert result["confidence"] == "low"
        assert result["formulated_problem"]["actor"] == "I"


class TestFormulateProblemHandler:
    """Tests for the tool handler."""

    @pytest.mark.asyncio
    async def test_valid_input_returns_structured_content(self):
        """Valid input returns proper structured content."""
        result = await handle(
            user_id="",
            correlation_id="test-123",
            arguments={
                "actor": "I",
                "goal": "improve my productivity",
                "obstacle": "constant context switching",
                "cost": "mental exhaustion",
            },
        )

        assert result.isError is not True
        assert len(result.content) == 1
        assert "Formulated problem" in result.content[0].text

        sc = result.structuredContent
        assert "formulated_problem" in sc
        assert "confidence" in sc
        assert "assistant_guidance" in sc

    @pytest.mark.asyncio
    async def test_partial_input_returns_low_confidence(self):
        """Partial input (missing fields) returns low confidence with clarify."""
        result = await handle(
            user_id="",
            correlation_id="test-123",
            arguments={
                "actor": "I",
                "goal": "do something",
                # Missing obstacle and cost - but schema allows this now
            },
        )

        # Should NOT error - fields are optional
        assert result.isError is not True
        sc = result.structuredContent
        assert sc["confidence"] in ("low", "medium")
        assert sc["needs_clarification"] is True

    @pytest.mark.asyncio
    async def test_high_confidence_guidance_returns_confirm_action(self):
        """High confidence response returns CONFIRM_PROBLEM action."""
        result = await handle(
            user_id="",
            correlation_id="test-123",
            arguments={
                "actor": "I",
                "goal": "get promoted to senior engineer",
                "obstacle": "my manager doesn't see my impact",
                "cost": "career stagnation and frustration",
            },
        )

        sc = result.structuredContent
        assert sc["confidence"] == "high"
        assert sc["assistant_guidance"]["action"] == "CONFIRM_PROBLEM"
        assert "problem_statement" in sc["assistant_guidance"]

    @pytest.mark.asyncio
    async def test_low_confidence_guidance_returns_clarify_action(self):
        """Low confidence response returns ASK_CLARIFYING action with type."""
        result = await handle(
            user_id="",
            correlation_id="test-123",
            arguments={
                "actor": "I",
                "goal": "",  # Missing
                "obstacle": "stuff",
                "cost": "things",
            },
        )

        sc = result.structuredContent
        assert sc["confidence"] == "low"
        assert sc["needs_clarification"] is True
        assert sc["clarify"]["type"] == "GOAL"
        # Guidance returns intent codes, not prose
        assert sc["assistant_guidance"]["action"] == "ASK_CLARIFYING"
        assert sc["assistant_guidance"]["clarify_type"] == "GOAL"

    @pytest.mark.asyncio
    async def test_guidance_returns_intent_not_prose(self):
        """Guidance returns structured intent codes, not prose strings."""
        result = await handle(
            user_id="",
            correlation_id="test-123",
            arguments={
                "actor": "I",
                "goal": "decide whether to change jobs",
                "obstacle": "fear of the unknown",
                "cost": "stuck in a rut",
            },
        )

        guidance = result.structuredContent["assistant_guidance"]

        # Guidance should be a dict with action, not a string
        assert isinstance(guidance, dict), "Guidance should be intent codes, not prose"
        assert "action" in guidance
        assert guidance["action"] in ("CONFIRM_PROBLEM", "ASK_CLARIFYING")
        assert "problem_statement" in guidance
