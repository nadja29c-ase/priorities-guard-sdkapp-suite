"""
Unit tests for cluster_questions tool.

Tests both the pure tool_logic function and the tool handler.
"""

import pytest
from mcp_server.unpack.tool_logic import (
    cluster_questions,
    generate_insight,
    generate_summary_markdown,
    MissingProblemStatementError,
    InsufficientQuestionsError,
    InvalidClustersError,
    HallucinatedQuestionsError,
)
from mcp_server.unpack.tools.cluster_questions import handle


class TestClusterQuestionsLogic:
    """Tests for the pure cluster_questions function."""

    def test_valid_input_returns_clusters_with_insights(self):
        """Valid input returns clusters with insights added."""
        result = cluster_questions(
            problem_statement="I am trying to get respect at work, but the team keeps interrupting me, which costs my confidence.",
            questions=[
                "Why does the team interrupt me?",
                "Should I talk to my manager?",
                "What if it gets worse?",
                "Is this intentional?",
            ],
            clusters=[
                {"theme": "Understanding the behavior", "questions": ["Why does the team interrupt me?", "Is this intentional?"]},
                {"theme": "How to respond", "questions": ["Should I talk to my manager?"]},
                {"theme": "Potential consequences", "questions": ["What if it gets worse?"]},
            ],
            unclustered=[],
        )

        assert "error" not in result
        assert len(result["clusters"]) == 3

        # Check insights were added
        for cluster in result["clusters"]:
            assert "insight" in cluster
            assert cluster["insight"].startswith("These questions explore")

        # Check themes are preserved
        assert result["clusters"][0]["theme"] == "Understanding the behavior"

        # Check unclustered is present (empty)
        assert result["unclustered"] == []

        # Check summary markdown exists
        assert "summary_markdown" in result
        assert result["summary_markdown"].startswith("# Unpack Summary")

    def test_fewer_than_3_questions_raises_error(self):
        """Fewer than 3 questions raises InsufficientQuestionsError."""
        with pytest.raises(InsufficientQuestionsError) as exc_info:
            cluster_questions(
                problem_statement="Test problem",
                questions=["Why?", "What?"],
                clusters=[{"theme": "Test theme", "questions": ["Why?"]}],
            )

        assert exc_info.value.error_type == "insufficient_questions"
        assert exc_info.value.extra["count"] == 2
        assert exc_info.value.extra["required_minimum"] == 3

    def test_empty_problem_statement_raises_error(self):
        """Empty problem statement raises MissingProblemStatementError."""
        with pytest.raises(MissingProblemStatementError) as exc_info:
            cluster_questions(
                problem_statement="",
                questions=["Q1", "Q2", "Q3"],
                clusters=[{"theme": "Test theme", "questions": ["Q1"]}],
            )

        assert exc_info.value.error_type == "missing_problem_statement"

    def test_whitespace_problem_statement_raises_error(self):
        """Whitespace-only problem statement raises MissingProblemStatementError."""
        with pytest.raises(MissingProblemStatementError) as exc_info:
            cluster_questions(
                problem_statement="   ",
                questions=["Q1", "Q2", "Q3"],
                clusters=[{"theme": "Test theme", "questions": ["Q1"]}],
            )

        assert exc_info.value.error_type == "missing_problem_statement"

    def test_with_unclustered_questions(self):
        """Unclustered questions are preserved in output."""
        result = cluster_questions(
            problem_statement="Test problem statement here",
            questions=["Why?", "What's for lunch?", "Should I?"],
            clusters=[
                {"theme": "Root causes", "questions": ["Why?"]},
                {"theme": "Options to consider", "questions": ["Should I?"]},
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
                questions=["Q1", "Q2", "Q3"],
                clusters=[],
            )

        assert exc_info.value.error_type == "invalid_clusters"

    def test_cluster_with_no_questions_skipped(self):
        """Clusters with no questions are skipped."""
        result = cluster_questions(
            problem_statement="Test problem statement here",
            questions=["Q1", "Q2", "Q3"],
            clusters=[
                {"theme": "Empty theme", "questions": []},  # Empty - should be skipped
                {"theme": "Valid theme", "questions": ["Q1", "Q2", "Q3"]},
            ],
        )

        assert "error" not in result
        assert len(result["clusters"]) == 1
        assert result["clusters"][0]["theme"] == "Valid theme"

    def test_cluster_ids_assigned(self):
        """Clusters get unique IDs."""
        result = cluster_questions(
            problem_statement="Test problem statement here",
            questions=["Q1", "Q2", "Q3"],
            clusters=[
                {"theme": "First theme", "questions": ["Q1"]},
                {"theme": "Second theme", "questions": ["Q2", "Q3"]},
            ],
        )

        assert "error" not in result
        assert result["clusters"][0]["id"] == "cluster_1"
        assert result["clusters"][1]["id"] == "cluster_2"

    def test_hallucinated_questions_raises_error(self):
        """Clusters with questions not in provided list raises HallucinatedQuestionsError."""
        with pytest.raises(HallucinatedQuestionsError) as exc_info:
            cluster_questions(
                problem_statement="Test problem statement",
                questions=["Q1", "Q2", "Q3"],
                clusters=[
                    {"theme": "Test theme", "questions": ["Q1", "Q99"]},  # Q99 not in list
                ],
            )

        assert exc_info.value.error_type == "hallucinated_questions"
        assert "Q99" in exc_info.value.extra["hallucinated"]

    def test_hallucinated_unclustered_raises_error(self):
        """Unclustered questions not in provided list raises HallucinatedQuestionsError."""
        with pytest.raises(HallucinatedQuestionsError) as exc_info:
            cluster_questions(
                problem_statement="Test problem statement",
                questions=["Q1", "Q2", "Q3"],
                clusters=[
                    {"theme": "Test theme", "questions": ["Q1"]},
                ],
                unclustered=["Q2", "Q_fake"],  # Q_fake not in list
            )

        assert exc_info.value.error_type == "hallucinated_questions"
        assert "Q_fake" in exc_info.value.extra["hallucinated"]

    def test_empty_theme_gets_default(self):
        """Empty theme gets default 'Theme N' name."""
        result = cluster_questions(
            problem_statement="Test problem statement here",
            questions=["Q1", "Q2", "Q3"],
            clusters=[
                {"theme": "", "questions": ["Q1", "Q2", "Q3"]},
            ],
        )

        assert "error" not in result
        assert result["clusters"][0]["theme"] == "Theme 1"


class TestGenerateInsight:
    """Tests for insight generation."""

    def test_insight_uses_theme(self):
        """Insight includes the theme in lowercase."""
        insight = generate_insight("Understanding Team Dynamics")
        assert "These questions explore understanding team dynamics." == insight

    def test_insight_lowercases_theme(self):
        """Insight lowercases the theme."""
        insight = generate_insight("ROOT CAUSE ANALYSIS")
        assert "root cause analysis" in insight


class TestGenerateSummaryMarkdown:
    """Tests for summary markdown generation."""

    def test_summary_starts_with_header(self):
        """Summary starts with '# Unpack Summary'."""
        md = generate_summary_markdown(
            problem_statement="Test problem",
            clusters=[{"theme": "Test theme", "questions": ["Q1"], "insight": "Test insight"}],
            unclustered=[],
        )
        assert md.startswith("# Unpack Summary")

    def test_summary_contains_problem(self):
        """Summary contains problem statement."""
        md = generate_summary_markdown(
            problem_statement="My specific problem statement",
            clusters=[{"theme": "Test theme", "questions": ["Q1"], "insight": "Test insight"}],
            unclustered=[],
        )
        assert "## Problem" in md
        assert "My specific problem statement" in md

    def test_summary_contains_clusters_by_theme(self):
        """Summary contains cluster headings with theme."""
        md = generate_summary_markdown(
            problem_statement="Test",
            clusters=[
                {"theme": "Understanding the root cause", "questions": ["Why?"], "insight": "Insight here"},
            ],
            unclustered=[],
        )
        assert "### Understanding the root cause" in md
        assert "- Why?" in md
        assert "_Insight here_" in md

    def test_summary_uses_questions_by_theme_header(self):
        """Summary uses 'Questions by Theme' section header."""
        md = generate_summary_markdown(
            problem_statement="Test",
            clusters=[{"theme": "Test", "questions": ["Q1"], "insight": "Insight"}],
            unclustered=[],
        )
        assert "## Questions by Theme" in md

    def test_summary_contains_other_questions(self):
        """Summary contains 'Other Questions' section when unclustered present."""
        md = generate_summary_markdown(
            problem_statement="Test",
            clusters=[{"theme": "Test theme", "questions": ["Q1"], "insight": "Insight"}],
            unclustered=["Random question"],
        )
        assert "### Other Questions" in md
        assert "- Random question" in md
        assert "_These questions didn't fit a clear theme._" in md

    def test_summary_ends_with_attribution(self):
        """Summary ends with attribution."""
        md = generate_summary_markdown(
            problem_statement="Test",
            clusters=[{"theme": "Test theme", "questions": ["Q1"], "insight": "Insight"}],
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
                "questions": [
                    "Why is my work invisible?",
                    "Who should I talk to?",
                    "What if I ask for feedback?",
                ],
                "clusters": [
                    {"theme": "Understanding visibility", "questions": ["Why is my work invisible?"]},
                    {"theme": "Key stakeholders", "questions": ["Who should I talk to?"]},
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
        """Fewer than 3 questions returns error with guidance."""
        result = await handle(
            user_id="",
            correlation_id="test-123",
            arguments={
                "problem_statement": "Test problem",
                "questions": ["Q1", "Q2"],  # Only 2
                "clusters": [{"theme": "Test theme", "questions": ["Q1"]}],
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
                "questions": ["Q1", "Q2", "Q3"],
                "clusters": [{"theme": "Test theme", "questions": ["Q1"]}],
            },
        )

        assert result.isError is True
        sc = result.structuredContent
        assert sc["error_type"] == "missing_problem_statement"
        assert sc["assistant_guidance"]["action"] == "RESTART_FLOW"

    @pytest.mark.asyncio
    async def test_guidance_contains_present_clusters_action(self):
        """Successful response has PRESENT_CLUSTERS action."""
        result = await handle(
            user_id="",
            correlation_id="test-123",
            arguments={
                "problem_statement": "Test problem statement",
                "questions": ["Q1", "Q2", "Q3"],
                "clusters": [
                    {"theme": "Test theme", "questions": ["Q1", "Q2", "Q3"]},
                ],
                "unclustered": [],
            },
        )

        assert result.isError is not True
        guidance = result.structuredContent["assistant_guidance"]
        assert guidance["action"] == "PRESENT_CLUSTERS"
        assert "Do NOT offer advice" in guidance["instruction"]

    @pytest.mark.asyncio
    async def test_insight_uses_structural_framing(self):
        """Insights use structural framing, not user-state framing."""
        result = await handle(
            user_id="",
            correlation_id="test-123",
            arguments={
                "problem_statement": "Test problem",
                "questions": ["Why?", "What?", "How?"],
                "clusters": [
                    {"theme": "Root cause analysis", "questions": ["Why?", "What?", "How?"]},
                ],
            },
        )

        assert result.isError is not True
        cluster = result.structuredContent["clusters"][0]
        insight = cluster["insight"]

        # Should use structural framing
        assert "These questions explore" in insight
        # Should NOT use user-state framing
        assert "You're uncertain" not in insight
        assert "You are uncertain" not in insight
