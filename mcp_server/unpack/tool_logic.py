"""
Unpack tool logic - pure functions.

No MCP types here. Tools call these functions and wrap results
in MCP response format.

Wording is decoupled from logic — handlers map types to phrases.
"""

from typing import Literal


# Clarification types (handlers map these to user-friendly phrases)
ClarifyType = Literal["GOAL", "OBSTACLE", "COST", "GENERAL"]


def formulate_problem(
    actor: str,
    goal: str,
    obstacle: str,
    cost: str,
) -> dict:
    """
    Construct a structured problem statement from LLM-extracted components.

    Args:
        actor: Who is experiencing the problem
        goal: What they're trying to achieve
        obstacle: What keeps blocking progress
        cost: Impact in terms of time, money, energy, or clarity

    Returns:
        Dict with formulated_problem, confidence, and optional clarify info.
        Wording is decoupled — returns type enums, not strings.
    """
    # Normalize inputs (strip whitespace)
    actor = (actor or "").strip()
    goal = (goal or "").strip()
    obstacle = (obstacle or "").strip()
    cost = (cost or "").strip()

    # Core components (goal, obstacle) must be present for medium+
    # Actor can be short (e.g., "I"), cost can be inferred
    core_components = {"goal": goal, "obstacle": obstacle}
    core_filled = {k: v for k, v in core_components.items() if v}

    all_components = {"actor": actor, "goal": goal, "obstacle": obstacle, "cost": cost}
    total_filled = len([v for v in all_components.values() if v])

    # Determine confidence based on component quality
    confidence: Literal["high", "medium", "low"]

    if len(core_filled) < 2:
        # Missing core component (goal or obstacle) -> low
        confidence = "low"
    elif total_filled == 4:
        # All 4 present - check detail quality (except actor which can be short)
        goal_detailed = len(goal) >= 5
        obstacle_detailed = len(obstacle) >= 5
        cost_detailed = len(cost) >= 5

        if goal_detailed and obstacle_detailed and cost_detailed:
            confidence = "high"
        else:
            confidence = "medium"
    else:
        # Core present but something else weak/missing
        confidence = "medium"

    # Use defaults for empty components (to construct full_statement)
    actor_display = actor or "I"
    goal_display = goal or "[goal unclear]"
    obstacle_display = obstacle or "[obstacle unclear]"
    cost_display = cost or "[cost unclear]"

    # Handle "I" vs other actors for grammar
    if actor_display.lower() == "i":
        verb = "am"
    else:
        verb = "is"

    # Construct full statement
    full_statement = (
        f"{actor_display} {verb} trying to {goal_display}, "
        f"but {obstacle_display} keeps happening, "
        f"which costs {cost_display}."
    )

    # Determine clarification type based on what's missing or weak
    clarify_type: ClarifyType | None = None
    if confidence != "high":
        if not goal or len(goal) < 5:
            clarify_type = "GOAL"
        elif not obstacle or len(obstacle) < 5:
            clarify_type = "OBSTACLE"
        elif not cost or len(cost) < 5:
            clarify_type = "COST"
        else:
            # Components present but may need more clarity
            clarify_type = "GENERAL"

    # Build result
    result = {
        "formulated_problem": {
            "actor": actor_display,
            "goal": goal_display,
            "obstacle": obstacle_display,
            "cost": cost_display,
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

# Valid uncertainty types for clustering
VALID_UNCERTAINTY_TYPES = frozenset([
    "causes",
    "constraints",
    "unknowns",
    "dependencies",
    "risks",
    "options",
])

# Insight templates per uncertainty type
INSIGHT_TEMPLATES = {
    "causes": "These questions focus on what may be driving {topic}.",
    "constraints": "These questions explore what might be limiting options around {topic}.",
    "unknowns": "These questions identify missing information about {topic}.",
    "dependencies": "These questions consider how others factor into {topic}.",
    "risks": "These questions examine what could go wrong with {topic}.",
    "options": "These questions explore possible approaches to {topic}.",
}


def generate_insight(label: str, uncertainty_type: str) -> str:
    """Generate a structural insight for a cluster."""
    template = INSIGHT_TEMPLATES.get(uncertainty_type, INSIGHT_TEMPLATES["unknowns"])
    # Use label as topic, lowercase for natural reading
    topic = label.lower()
    return template.format(topic=topic)


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
        "## Questions by Uncertainty Type",
        "",
    ]

    for cluster in clusters:
        lines.append(f"### {cluster['label']} ({cluster['uncertainty_type']})")
        for q in cluster["questions"]:
            lines.append(f"- {q}")
        lines.append(f"_{cluster['insight']}_")
        lines.append("")

    if unclustered:
        lines.append("### Unclustered")
        for q in unclustered:
            lines.append(f"- {q}")
        lines.append("_These questions don't fit a single uncertainty type._")
        lines.append("")

    lines.extend([
        "---",
        "Generated with Unpack • fulfilling-productivity.com"
    ])

    return "\n".join(lines)


def cluster_questions(
    problem_statement: str,
    questions: list[str],
    clusters: list[dict],
    unclustered: list[str] | None = None,
) -> dict:
    """
    Validate clustered questions and generate summary.

    ChatGPT performs semantic clustering before calling this function.
    This function validates structure, generates insights, and creates summary markdown.

    Args:
        problem_statement: Confirmed problem from formulate_problem
        questions: All questions collected
        clusters: ChatGPT-generated clusters with label, uncertainty_type, questions
        unclustered: Questions that don't fit any cluster (optional)

    Returns:
        Dict with:
        - clusters: Validated clusters with insights added
        - unclustered: Questions that don't fit
        - summary_markdown: Pre-formatted export
        - error (if validation fails): error_type and details
    """
    # Normalize unclustered
    unclustered = unclustered or []

    # ============================================================
    # VALIDATION
    # ============================================================

    # Check problem statement
    if not problem_statement or not problem_statement.strip():
        return {
            "error": True,
            "error_type": "missing_problem_statement",
        }

    # Check minimum questions
    if len(questions) < 3:
        return {
            "error": True,
            "error_type": "insufficient_questions",
            "count": len(questions),
            "required_minimum": 3,
        }

    # Validate clusters structure
    if not clusters:
        return {
            "error": True,
            "error_type": "invalid_clusters",
            "detail": "No clusters provided",
        }

    # ============================================================
    # PROCESS CLUSTERS
    # ============================================================

    processed_clusters = []
    for i, cluster in enumerate(clusters):
        # Validate required fields
        label = cluster.get("label", "").strip()
        uncertainty_type = cluster.get("uncertainty_type", "").strip().lower()
        cluster_questions_list = cluster.get("questions", [])

        if not label:
            label = f"Cluster {i + 1}"

        # Map invalid uncertainty types to "unknowns"
        if uncertainty_type not in VALID_UNCERTAINTY_TYPES:
            uncertainty_type = "unknowns"

        # Ensure at least one question in cluster
        if not cluster_questions_list:
            continue  # Skip empty clusters

        # Generate insight
        insight = generate_insight(label, uncertainty_type)

        processed_clusters.append({
            "id": f"cluster_{i + 1}",
            "label": label,
            "uncertainty_type": uncertainty_type,
            "questions": cluster_questions_list,
            "insight": insight,
        })

    # If no valid clusters after processing, return error
    if not processed_clusters:
        return {
            "error": True,
            "error_type": "invalid_clusters",
            "detail": "No valid clusters after validation",
        }

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
    }
