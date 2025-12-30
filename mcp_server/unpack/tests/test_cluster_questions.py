"""
Unit tests for cluster_questions tool.

Tests both the pure tool_logic function and the tool handler.
"""

import pytest
from mcp_server.unpack.tool_logic import (
    cluster_questions,
    generate_summary_markdown,
    MissingProblemStatementError,
    InsufficientQuestionsError,
    InvalidClustersError,
)
from mcp_server.unpack.tools.cluster_questions import handle


class TestClusterQuestionsLogic:
    """Tests for the pure cluster_questions function."""

    def test_valid_input_returns_clusters(self):
        """Valid input returns clusters with expected structure."""
        result = cluster_questions(
            problem_statement="I am trying to get respect at work, but the team keeps interrupting me, which costs my confidence.",
            clusters=[
                {"theme": "Understanding the behavior", "questions": ["Why does the team interrupt me?", "Is this intentional?"]},
                {"theme": "How to respond", "questions": ["Should I talk to my manager?", "Should I address it directly?"]},
                {"theme": "Potential consequences", "questions": ["What if it gets worse?", "Will it affect my career?"]},
            ],
            unclustered=[],
        )

        assert "error" not in result
        assert len(result["clusters"]) == 3

        # Check themes are preserved
        assert result["clusters"][0]["theme"] == "Understanding the behavior"

        # Check unclustered is present (empty)
        assert result["unclustered"] == []

        # Check summary markdown exists
        assert "summary_markdown" in result
        assert result["summary_markdown"].startswith("# Unpack Summary")

    def test_fewer_than_5_questions_raises_error(self):
        """Fewer than 5 total questions raises InsufficientQuestionsError."""
        with pytest.raises(InsufficientQuestionsError) as exc_info:
            cluster_questions(
                problem_statement="Test problem",
                clusters=[{"theme": "Test theme", "questions": ["Why?", "What?", "How?", "When?"]}],
            )

        assert exc_info.value.error_type == "insufficient_questions"
        assert exc_info.value.extra["count"] == 4
        assert exc_info.value.extra["required_minimum"] == 5

    def test_empty_problem_statement_raises_error(self):
        """Empty problem statement raises MissingProblemStatementError."""
        with pytest.raises(MissingProblemStatementError) as exc_info:
            cluster_questions(
                problem_statement="",
                clusters=[{"theme": "Test theme", "questions": ["Q1", "Q2", "Q3"]}],
            )

        assert exc_info.value.error_type == "missing_problem_statement"

    def test_whitespace_problem_statement_raises_error(self):
        """Whitespace-only problem statement raises MissingProblemStatementError."""
        with pytest.raises(MissingProblemStatementError) as exc_info:
            cluster_questions(
                problem_statement="   ",
                clusters=[{"theme": "Test theme", "questions": ["Q1", "Q2", "Q3"]}],
            )

        assert exc_info.value.error_type == "missing_problem_statement"

    def test_with_unclustered_questions(self):
        """Unclustered questions are preserved in output."""
        result = cluster_questions(
            problem_statement="Test problem statement here",
            clusters=[
                {"theme": "Root causes", "questions": ["Why?", "What caused this?"]},
                {"theme": "Options to consider", "questions": ["Should I?", "Could I try?"]},
            ],
            unclustered=["What's for lunch?"],
        )

        assert "error" not in result
        assert result["unclustered"] == ["What's for lunch?"]
        # Summary should include unclustered section
        assert "Other Questions" in result["summary_markdown"]
        assert "What's for lunch?" in result["summary_markdown"]

    def test_empty_clusters_raises_error(self):
        """Empty clusters list raises InvalidClustersError."""
        with pytest.raises(InvalidClustersError) as exc_info:
            cluster_questions(
                problem_statement="Test problem",
                clusters=[],
            )

        assert exc_info.value.error_type == "invalid_clusters"

    def test_cluster_with_no_questions_skipped(self):
        """Clusters with no questions are skipped."""
        result = cluster_questions(
            problem_statement="Test problem statement here",
            clusters=[
                {"theme": "Empty theme", "questions": []},  # Empty - should be skipped
                {"theme": "Valid theme", "questions": ["Q1", "Q2", "Q3", "Q4", "Q5"]},
            ],
        )

        assert "error" not in result
        assert len(result["clusters"]) == 1
        assert result["clusters"][0]["theme"] == "Valid theme"

    def test_cluster_ids_assigned(self):
        """Clusters get unique IDs."""
        result = cluster_questions(
            problem_statement="Test problem statement here",
            clusters=[
                {"theme": "First theme", "questions": ["Q1", "Q2"]},
                {"theme": "Second theme", "questions": ["Q3", "Q4", "Q5"]},
            ],
        )

        assert "error" not in result
        assert result["clusters"][0]["id"] == "cluster_1"
        assert result["clusters"][1]["id"] == "cluster_2"

    def test_empty_theme_gets_default(self):
        """Empty theme gets default 'Theme N' name."""
        result = cluster_questions(
            problem_statement="Test problem statement here",
            clusters=[
                {"theme": "", "questions": ["Q1", "Q2", "Q3", "Q4", "Q5"]},
            ],
        )

        assert "error" not in result
        assert result["clusters"][0]["theme"] == "Theme 1"

    def test_total_questions_returned(self):
        """Result includes total_questions count."""
        result = cluster_questions(
            problem_statement="Test problem",
            clusters=[
                {"theme": "Theme A", "questions": ["Q1", "Q2", "Q3"]},
                {"theme": "Theme B", "questions": ["Q4", "Q5"]},
            ],
            unclustered=[],
        )

        assert result["total_questions"] == 5

    def test_single_question_clusters_moved_to_unclustered(self):
        """Single-question clusters should be moved to unclustered."""
        result = cluster_questions(
            problem_statement="Test problem",
            clusters=[
                {"theme": "Valid cluster", "questions": ["Q1", "Q2", "Q3"]},
                {"theme": "Single question", "questions": ["Lonely Q"]},  # Should move
                {"theme": "Another valid", "questions": ["Q4", "Q5"]},
            ],
            unclustered=[],
        )

        # Only 2 valid clusters
        assert len(result["clusters"]) == 2

        # Single question moved to unclustered
        assert "Lonely Q" in result["unclustered"]

        # Total still counts all questions
        assert result["total_questions"] == 6


class TestDataShapeForWidget:
    """Tests verifying data shape expected by widget.

    These tests ensure the backend outputs match what the widget expects.
    Critical for widget rendering.
    """

    def test_cluster_output_uses_theme_field(self):
        """Widget depends on 'theme' not 'label'."""
        result = cluster_questions(
            problem_statement="Test problem",
            clusters=[
                {"theme": "Test theme", "questions": ["Q1", "Q2", "Q3", "Q4", "Q5"]}
            ],
        )

        assert "theme" in result["clusters"][0]
        assert "label" not in result["clusters"][0]
        assert result["clusters"][0]["theme"] == "Test theme"

    @pytest.mark.asyncio
    async def test_handler_includes_problem_statement_in_response(self):
        """Widget header depends on problem_statement in structuredContent."""
        result = await handle(
            user_id="",
            correlation_id="test-data-shape",
            arguments={
                "problem_statement": "My specific problem statement for header",
                "clusters": [
                    {"theme": "Test theme", "questions": ["Q1", "Q2", "Q3", "Q4", "Q5"]}
                ],
                "unclustered": [],
            },
        )

        assert result.isError is not True
        sc = result.structuredContent
        assert "problem_statement" in sc
        assert sc["problem_statement"] == "My specific problem statement for header"

    def test_minimum_five_questions_enforced(self):
        """Changed from 3 to 5 for better clustering quality."""
        # Should raise for 4 questions
        with pytest.raises(InsufficientQuestionsError) as exc_info:
            cluster_questions(
                problem_statement="Test problem",
                clusters=[{"theme": "Test", "questions": ["Q1", "Q2", "Q3", "Q4"]}],
            )

        assert exc_info.value.extra["required_minimum"] == 5

        # Should succeed for 5 questions
        result = cluster_questions(
            problem_statement="Test problem",
            clusters=[{"theme": "Test", "questions": ["Q1", "Q2", "Q3", "Q4", "Q5"]}],
        )
        assert result["total_questions"] == 5


class TestGenerateSummaryMarkdown:
    """Tests for summary markdown generation."""

    def test_summary_starts_with_header(self):
        """Summary starts with '# Unpack Summary'."""
        md = generate_summary_markdown(
            problem_statement="Test problem",
            clusters=[{"theme": "Test theme", "questions": ["Q1"]}],
            unclustered=[],
        )
        assert md.startswith("# Unpack Summary")

    def test_summary_contains_problem(self):
        """Summary contains problem statement."""
        md = generate_summary_markdown(
            problem_statement="My specific problem statement",
            clusters=[{"theme": "Test theme", "questions": ["Q1"]}],
            unclustered=[],
        )
        assert "## Problem" in md
        assert "My specific problem statement" in md

    def test_summary_contains_clusters_by_theme(self):
        """Summary contains cluster headings with theme."""
        md = generate_summary_markdown(
            problem_statement="Test",
            clusters=[
                {"theme": "Understanding the root cause", "questions": ["Why?"]},
            ],
            unclustered=[],
        )
        assert "### Understanding the root cause" in md
        assert "- Why?" in md

    def test_summary_uses_questions_by_theme_header(self):
        """Summary uses 'Questions by Theme' section header."""
        md = generate_summary_markdown(
            problem_statement="Test",
            clusters=[{"theme": "Test", "questions": ["Q1"]}],
            unclustered=[],
        )
        assert "## Questions by Theme" in md

    def test_summary_contains_other_questions(self):
        """Summary contains 'Other Questions' section when unclustered present."""
        md = generate_summary_markdown(
            problem_statement="Test",
            clusters=[{"theme": "Test theme", "questions": ["Q1"]}],
            unclustered=["Random question"],
        )
        assert "### Other Questions" in md
        assert "- Random question" in md
        assert "_These questions didn't fit a clear theme._" in md

    def test_summary_ends_with_attribution(self):
        """Summary ends with attribution."""
        md = generate_summary_markdown(
            problem_statement="Test",
            clusters=[{"theme": "Test theme", "questions": ["Q1"]}],
            unclustered=[],
        )
        assert "Generated with Unpack" in md
        assert "fulfilling-productivity.com" in md


class TestClusterQuestionsHandler:
    """Tests for the tool handler."""

    @pytest.mark.asyncio
    async def test_valid_input_returns_structured_content(self):
        """Valid input returns proper structured content."""
        result = await handle(
            user_id="",
            correlation_id="test-123",
            arguments={
                "problem_statement": "I am trying to get promoted, but my work is invisible, which costs my career growth.",
                "clusters": [
                    {"theme": "Understanding visibility", "questions": ["Why is my work invisible?", "Is it a communication issue?"]},
                    {"theme": "Key stakeholders", "questions": ["Who should I talk to?", "Who makes promotion decisions?"]},
                    {"theme": "Possible actions", "questions": ["What if I ask for feedback?"]},
                ],
                "unclustered": [],
            },
        )

        assert result.isError is not True
        assert len(result.content) == 1
        assert "Clustered" in result.content[0].text

        sc = result.structuredContent
        assert "clusters" in sc
        assert "unclustered" in sc
        assert "summary_markdown" in sc
        assert "assistant_guidance" in sc

    @pytest.mark.asyncio
    async def test_insufficient_questions_returns_error(self):
        """Fewer than 5 total questions returns error with guidance."""
        result = await handle(
            user_id="",
            correlation_id="test-123",
            arguments={
                "problem_statement": "Test problem",
                "clusters": [{"theme": "Test theme", "questions": ["Q1", "Q2", "Q3", "Q4"]}],
            },
        )

        assert result.isError is True
        sc = result.structuredContent
        assert sc["error_type"] == "insufficient_questions"
        assert sc["assistant_guidance"]["action"] == "REQUEST_MORE_QUESTIONS"

    @pytest.mark.asyncio
    async def test_missing_problem_statement_returns_error(self):
        """Empty problem statement returns error with guidance."""
        result = await handle(
            user_id="",
            correlation_id="test-123",
            arguments={
                "problem_statement": "",
                "clusters": [{"theme": "Test theme", "questions": ["Q1", "Q2", "Q3", "Q4", "Q5"]}],
            },
        )

        assert result.isError is True
        sc = result.structuredContent
        assert sc["error_type"] == "missing_problem_statement"
        assert sc["assistant_guidance"]["action"] == "RESTART_FLOW"

    @pytest.mark.asyncio
    async def test_guidance_uses_widget_rendered_action(self):
        """Successful response has WIDGET_RENDERED action with simple structure."""
        result = await handle(
            user_id="",
            correlation_id="test-123",
            arguments={
                "problem_statement": "Test problem statement",
                "clusters": [
                    {"theme": "Test theme", "questions": ["Q1", "Q2", "Q3", "Q4", "Q5"]},
                ],
                "unclustered": [],
            },
        )

        assert result.isError is not True
        guidance = result.structuredContent["assistant_guidance"]
        assert guidance["action"] == "WIDGET_RENDERED"
        # Simplified guidance - no prose, just intent codes
        assert "next_step" in guidance
