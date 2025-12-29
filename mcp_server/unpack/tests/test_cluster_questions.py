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
                {"label": "Root cause", "uncertainty_type": "causes", "questions": ["Why does the team interrupt me?", "Is this intentional?"]},
                {"label": "Response options", "uncertainty_type": "options", "questions": ["Should I talk to my manager?"]},
                {"label": "Potential risks", "uncertainty_type": "risks", "questions": ["What if it gets worse?"]},
            ],
            unclustered=[],
        )

        assert "error" not in result
        assert len(result["clusters"]) == 3

        # Check insights were added
        for cluster in result["clusters"]:
            assert "insight" in cluster
            assert cluster["insight"].startswith("These questions")

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
                clusters=[{"label": "Test", "uncertainty_type": "causes", "questions": ["Why?"]}],
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
                clusters=[{"label": "Test", "uncertainty_type": "causes", "questions": ["Q1"]}],
            )

        assert exc_info.value.error_type == "missing_problem_statement"

    def test_whitespace_problem_statement_raises_error(self):
        """Whitespace-only problem statement raises MissingProblemStatementError."""
        with pytest.raises(MissingProblemStatementError) as exc_info:
            cluster_questions(
                problem_statement="   ",
                questions=["Q1", "Q2", "Q3"],
                clusters=[{"label": "Test", "uncertainty_type": "causes", "questions": ["Q1"]}],
            )

        assert exc_info.value.error_type == "missing_problem_statement"

    def test_with_unclustered_questions(self):
        """Unclustered questions are preserved in output."""
        result = cluster_questions(
            problem_statement="Test problem statement here",
            questions=["Why?", "What's for lunch?", "Should I?"],
            clusters=[
                {"label": "Causes", "uncertainty_type": "causes", "questions": ["Why?"]},
                {"label": "Options", "uncertainty_type": "options", "questions": ["Should I?"]},
            ],
            unclustered=["What's for lunch?"],
        )

        assert "error" not in result
        assert result["unclustered"] == ["What's for lunch?"]
        # Summary should include unclustered section
        assert "Unclustered" in result["summary_markdown"]
        assert "What's for lunch?" in result["summary_markdown"]

    def test_invalid_uncertainty_type_maps_to_unknowns(self):
        """Invalid uncertainty type maps to 'unknowns' instead of rejecting."""
        result = cluster_questions(
            problem_statement="Test problem statement here",
            questions=["Q1", "Q2", "Q3"],
            clusters=[
                {"label": "Test", "uncertainty_type": "invalid_type", "questions": ["Q1", "Q2", "Q3"]},
            ],
        )

        assert "error" not in result
        assert result["clusters"][0]["uncertainty_type"] == "unknowns"

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
                {"label": "Empty", "uncertainty_type": "causes", "questions": []},  # Empty - should be skipped
                {"label": "Valid", "uncertainty_type": "options", "questions": ["Q1", "Q2", "Q3"]},
            ],
        )

        assert "error" not in result
        assert len(result["clusters"]) == 1
        assert result["clusters"][0]["label"] == "Valid"

    def test_cluster_ids_assigned(self):
        """Clusters get unique IDs."""
        result = cluster_questions(
            problem_statement="Test problem statement here",
            questions=["Q1", "Q2", "Q3"],
            clusters=[
                {"label": "First", "uncertainty_type": "causes", "questions": ["Q1"]},
                {"label": "Second", "uncertainty_type": "risks", "questions": ["Q2", "Q3"]},
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
                    {"label": "Test", "uncertainty_type": "causes", "questions": ["Q1", "Q99"]},  # Q99 not in list
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
                    {"label": "Test", "uncertainty_type": "causes", "questions": ["Q1"]},
                ],
                unclustered=["Q2", "Q_fake"],  # Q_fake not in list
            )

        assert exc_info.value.error_type == "hallucinated_questions"
        assert "Q_fake" in exc_info.value.extra["hallucinated"]


class TestGenerateInsight:
    """Tests for insight generation."""

    def test_causes_insight(self):
        """Causes insight uses correct template."""
        insight = generate_insight("Team dynamics", "causes")
        assert "These questions focus on what may be driving" in insight
        assert "team dynamics" in insight

    def test_constraints_insight(self):
        """Constraints insight uses correct template."""
        insight = generate_insight("Time limits", "constraints")
        assert "These questions explore what might be limiting" in insight

    def test_unknowns_insight(self):
        """Unknowns insight uses correct template."""
        insight = generate_insight("Market data", "unknowns")
        assert "These questions identify missing information" in insight

    def test_dependencies_insight(self):
        """Dependencies insight uses correct template."""
        insight = generate_insight("Stakeholder buy-in", "dependencies")
        assert "These questions consider how others factor" in insight

    def test_risks_insight(self):
        """Risks insight uses correct template."""
        insight = generate_insight("Failure scenarios", "risks")
        assert "These questions examine what could go wrong" in insight

    def test_options_insight(self):
        """Options insight uses correct template."""
        insight = generate_insight("Approaches", "options")
        assert "These questions explore possible approaches" in insight


class TestGenerateSummaryMarkdown:
    """Tests for summary markdown generation."""

    def test_summary_starts_with_header(self):
        """Summary starts with '# Unpack Summary'."""
        md = generate_summary_markdown(
            problem_statement="Test problem",
            clusters=[{"label": "Test", "uncertainty_type": "causes", "questions": ["Q1"], "insight": "Test insight"}],
            unclustered=[],
        )
        assert md.startswith("# Unpack Summary")

    def test_summary_contains_problem(self):
        """Summary contains problem statement."""
        md = generate_summary_markdown(
            problem_statement="My specific problem statement",
            clusters=[{"label": "Test", "uncertainty_type": "causes", "questions": ["Q1"], "insight": "Test insight"}],
            unclustered=[],
        )
        assert "## Problem" in md
        assert "My specific problem statement" in md

    def test_summary_contains_clusters(self):
        """Summary contains cluster headings with type."""
        md = generate_summary_markdown(
            problem_statement="Test",
            clusters=[
                {"label": "Root cause", "uncertainty_type": "causes", "questions": ["Why?"], "insight": "Insight here"},
            ],
            unclustered=[],
        )
        assert "### Root cause (causes)" in md
        assert "- Why?" in md
        assert "_Insight here_" in md

    def test_summary_contains_unclustered(self):
        """Summary contains unclustered section when present."""
        md = generate_summary_markdown(
            problem_statement="Test",
            clusters=[{"label": "Test", "uncertainty_type": "causes", "questions": ["Q1"], "insight": "Insight"}],
            unclustered=["Random question"],
        )
        assert "### Unclustered" in md
        assert "- Random question" in md
        assert "_These questions don't fit a single uncertainty type._" in md

    def test_summary_ends_with_attribution(self):
        """Summary ends with attribution."""
        md = generate_summary_markdown(
            problem_statement="Test",
            clusters=[{"label": "Test", "uncertainty_type": "causes", "questions": ["Q1"], "insight": "Insight"}],
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
                    {"label": "Visibility causes", "uncertainty_type": "causes", "questions": ["Why is my work invisible?"]},
                    {"label": "Stakeholders", "uncertainty_type": "dependencies", "questions": ["Who should I talk to?"]},
                    {"label": "Options", "uncertainty_type": "options", "questions": ["What if I ask for feedback?"]},
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
                "clusters": [{"label": "Test", "uncertainty_type": "causes", "questions": ["Q1"]}],
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
                "clusters": [{"label": "Test", "uncertainty_type": "causes", "questions": ["Q1"]}],
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
                    {"label": "Test", "uncertainty_type": "causes", "questions": ["Q1", "Q2", "Q3"]},
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
                    {"label": "Root cause", "uncertainty_type": "causes", "questions": ["Why?", "What?", "How?"]},
                ],
            },
        )

        assert result.isError is not True
        cluster = result.structuredContent["clusters"][0]
        insight = cluster["insight"]

        # Should use structural framing
        assert "These questions" in insight
        # Should NOT use user-state framing
        assert "You're uncertain" not in insight
        assert "You are uncertain" not in insight
