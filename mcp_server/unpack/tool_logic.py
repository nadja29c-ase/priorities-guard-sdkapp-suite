"""
Unpack tool logic - pure functions.

No MCP types here. Tools call these functions and wrap results
in MCP response format.

Wording is decoupled from logic — handlers map types to phrases.
"""

from typing import Literal


# Clarification types (handlers map these to user-friendly phrases)
ClarifyType = Literal["GOAL", "OBSTACLE"]


# ============================================================================
# Exceptions for cluster validation (handlers map to ToolUsageError)
# ============================================================================

class ClusterValidationError(Exception):
    """Base exception for cluster validation failures."""
    def __init__(self, error_type: str, detail: str | None = None, **kwargs):
        self.error_type = error_type
        self.detail = detail
        self.extra = kwargs
        super().__init__(f"{error_type}: {detail}" if detail else error_type)


class MissingProblemStatementError(ClusterValidationError):
    """Raised when problem statement is missing."""
    def __init__(self):
        super().__init__("missing_problem_statement", "Problem statement is required")


class InsufficientQuestionsError(ClusterValidationError):
    """Raised when fewer than 5 questions provided."""
    def __init__(self, count: int):
        super().__init__(
            "insufficient_questions",
            f"Need at least 5 questions, got {count}",
            count=count,
            required_minimum=5,
        )


class InvalidClustersError(ClusterValidationError):
    """Raised when clusters are invalid or empty."""
    def __init__(self, detail: str):
        super().__init__("invalid_clusters", detail)


def formulate_problem(
    actor: str,
    goal: str,
    obstacle: str,
) -> dict:
    """
    Construct a structured problem statement from LLM-extracted components.

    Args:
        actor: Who is experiencing the problem
        goal: What they're trying to achieve
        obstacle: What keeps blocking progress

    Returns:
        Dict with formulated_problem, confidence, and optional clarify info.
        Wording is decoupled — returns type enums, not strings.
    """
    # Normalize inputs (strip whitespace)
    actor = (actor or "").strip()
    goal = (goal or "").strip()
    obstacle = (obstacle or "").strip()

    def is_valid(value: str) -> bool:
        """Check if value is meaningful, not a placeholder."""
        if not value or len(value) < 5:
            return False
        lower = value.lower()
        return "[" not in lower and "unclear" not in lower

    goal_valid = is_valid(goal)
    obstacle_valid = is_valid(obstacle)

    # Determine confidence
    confidence: Literal["high", "medium", "low"]
    if goal_valid and obstacle_valid:
        confidence = "high"
    elif goal_valid or obstacle_valid:
        confidence = "medium"
    else:
        confidence = "low"

    # Display values (keep placeholders for output)
    actor_display = actor or "I"
    goal_display = goal if goal_valid else "[goal unclear]"
    obstacle_display = obstacle if obstacle_valid else "[obstacle unclear]"

    # Handle "I" vs other actors for grammar
    if actor_display.lower() == "i":
        verb = "am"
    else:
        verb = "is"

    # Construct full statement
    full_statement = (
        f"{actor_display} {verb} trying to {goal_display}, "
        f"but {obstacle_display}."
    )

    # Determine clarification type based on what's invalid
    clarify_type: ClarifyType | None = None
    if confidence != "high":
        if not goal_valid:
            clarify_type = "GOAL"
        else:
            clarify_type = "OBSTACLE"

    # Build result
    result = {
        "formulated_problem": {
            "actor": actor_display,
            "goal": goal_display,
            "obstacle": obstacle_display,
            "full_statement": full_statement,
        },
        "confidence": confidence,
        "needs_clarification": clarify_type is not None,
    }

    if clarify_type:
        result["clarify"] = {"type": clarify_type}

    return result


# ============================================================================
# Cluster Questions Logic
# ============================================================================


def generate_summary_markdown(
    problem_statement: str,
    clusters: list[dict],
    unclustered: list[str],
) -> str:
    """Generate markdown summary for export."""
    lines = [
        "# Unpack Summary",
        "",
        "## Problem",
        problem_statement,
        "",
        "## Questions by Theme",
        "",
    ]

    for cluster in clusters:
        lines.append(f"### {cluster['theme']}")
        for q in cluster["questions"]:
            lines.append(f"- {q}")
        lines.append("")

    if unclustered:
        lines.append("### Other Questions")
        for q in unclustered:
            lines.append(f"- {q}")
        lines.append("_These questions didn't fit a clear theme._")
        lines.append("")

    lines.extend([
        "---",
        "Generated with Unpack • fulfilling-productivity.com"
    ])

    return "\n".join(lines)


def cluster_questions(
    problem_statement: str,
    clusters: list[dict],
    unclustered: list[str] | None = None,
) -> dict:
    """
    Validate clustered questions and generate summary.

    ChatGPT performs semantic clustering before calling this function.
    This function validates structure and creates summary markdown.

    Args:
        problem_statement: Confirmed problem from formulate_problem
        clusters: ChatGPT-generated clusters with theme and questions
        unclustered: Questions that don't fit any cluster (optional)

    Returns:
        Dict with:
        - clusters: Validated clusters
        - unclustered: Questions that don't fit
        - summary_markdown: Pre-formatted export
        - total_questions: Count of all questions (clustered + unclustered)

    Raises:
        MissingProblemStatementError: If problem_statement is empty
        InsufficientQuestionsError: If fewer than 5 total questions
        InvalidClustersError: If clusters are empty or invalid
    """
    # Normalize unclustered
    unclustered = unclustered or []

    # ============================================================
    # VALIDATION
    # ============================================================

    # Check problem statement
    if not problem_statement or not problem_statement.strip():
        raise MissingProblemStatementError()

    # Validate clusters structure
    if not clusters:
        raise InvalidClustersError("No clusters provided")

    # ============================================================
    # PROCESS CLUSTERS
    # ============================================================

    processed_clusters = []
    total_questions = 0

    for i, cluster in enumerate(clusters):
        # Validate required fields
        theme = cluster.get("theme", "").strip()
        cluster_questions_list = cluster.get("questions", [])

        # Validate questions is a list
        if not isinstance(cluster_questions_list, list):
            raise InvalidClustersError("Cluster questions must be a list")

        if not theme:
            theme = f"Theme {i + 1}"

        # Skip empty clusters
        if not cluster_questions_list:
            continue

        # Single questions don't form a cluster — move to unclustered
        if len(cluster_questions_list) == 1:
            unclustered.append(cluster_questions_list[0])
            continue

        total_questions += len(cluster_questions_list)

        processed_clusters.append({
            "id": f"cluster_{i + 1}",
            "theme": theme,
            "questions": cluster_questions_list,
        })

    # Add unclustered to total (includes singles moved from clusters)
    total_questions += len(unclustered)

    # Check minimum questions (after counting all)
    if total_questions < 5:
        raise InsufficientQuestionsError(count=total_questions)

    # If no valid clusters after processing, raise error
    if not processed_clusters:
        raise InvalidClustersError("No valid clusters after validation")

    # ============================================================
    # GENERATE OUTPUT
    # ============================================================

    summary_markdown = generate_summary_markdown(
        problem_statement=problem_statement,
        clusters=processed_clusters,
        unclustered=unclustered,
    )

    return {
        "clusters": processed_clusters,
        "unclustered": unclustered,
        "summary_markdown": summary_markdown,
        "total_questions": total_questions,
    }
