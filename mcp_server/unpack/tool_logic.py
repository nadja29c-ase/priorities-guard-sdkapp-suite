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
