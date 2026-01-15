"""
Pure business logic for Sharpen tools.

Contains stateless functions that can be tested independently of MCP types.
Structural validation only — semantic quality is the LLM's job.
"""

from typing import Any


def generate_checklist_markdown(project_name: str, items: list[dict]) -> str:
    """
    Generate markdown checklist grouped by deliverable.

    Args:
        project_name: Name of the project
        items: List of work items, each with task_name, deliverable, and optional estimate_hours

    Returns:
        Formatted markdown string
    """
    # Group items by deliverable
    deliverables: dict[str, list[dict]] = {}
    for item in items:
        deliverable = item["deliverable"]
        if deliverable not in deliverables:
            deliverables[deliverable] = []
        deliverables[deliverable].append(item)

    # Build markdown
    lines = [f"# {project_name} — Work Plan", ""]

    for deliverable_name, tasks in deliverables.items():
        lines.append(f"## {deliverable_name}")
        for task in tasks:
            task_name = task["task_name"]
            estimate = task.get("estimate_hours")
            if estimate is not None:
                lines.append(f"- [ ] {task_name} ({estimate}h)")
            else:
                lines.append(f"- [ ] {task_name}")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append("Generated with Sharpen • priority-guard.com")

    return "\n".join(lines)


def export_checklist(project_name: str, items: list[dict]) -> dict[str, Any]:
    """
    Export work items as a markdown checklist.

    Args:
        project_name: Name of the project
        items: List of work items

    Returns:
        Pure domain data (no MCP/transport concerns)
    """
    markdown = generate_checklist_markdown(project_name, items)

    return {
        "project_name": project_name,
        "item_count": len(items),
        "checklist_markdown": markdown,
    }


# ============================================================================
# Step 1: Initiative Framing Logic (Structural Validation Only)
# ============================================================================


def validate_initiative_intent(
    who: str | None,
    what: str | None,
    why: str | None = None,
) -> dict[str, Any]:
    """
    Validate structure of WHO and WHAT for initiative intent.

    Structural validation only — semantic quality is LLM's job.

    Args:
        who: Who benefits from this work?
        what: What artifact/deliverable must exist?
        why: Optional — so that the beneficiary benefits how?

    Returns:
        framing_intent dict + valid flag
    """
    # Normalize inputs
    who = (who or "").strip()
    what = (what or "").strip()
    why = (why or "").strip() if why else None

    # Structural validation only
    valid = bool(who) and bool(what)

    missing = []
    if not who:
        missing.append("who")
    if not what:
        missing.append("what")

    return {
        "framing_intent": {
            "who": who,
            "what": what,
            "why": why,
        },
        "valid": valid,
        "missing": missing,
    }


def validate_initiative_constraints(
    constraint_type: str | None = None,
    constraint_value: str | None = None,
    definition_of_finished: str | None = None,
    user_claims_no_constraints: bool = False,
) -> dict[str, Any]:
    """
    Validate structure of constraints and definition of finished.

    Structural validation only — semantic quality is LLM's job.

    Args:
        constraint_type: time, capacity, budget, or forced_mvp
        constraint_value: The specific constraint in user's words
        definition_of_finished: How will you know WHAT is finished?
        user_claims_no_constraints: True if user claims no constraints

    Returns:
        constraint_framing dict + valid flag + force_constraint flag
    """
    # Handle user claiming no constraints — return early
    if user_claims_no_constraints:
        return {
            "constraint_framing": None,
            "valid": False,
            "missing": [],
            "force_constraint": True,
        }

    # Normalize inputs
    constraint_type = (constraint_type or "").strip() or None
    constraint_value = (constraint_value or "").strip() or None
    definition_of_finished = (definition_of_finished or "").strip() or None

    # Build constraint framing
    constraint_framing = {
        "constraint_type": constraint_type,
        "constraint_value": constraint_value,
        "definition_of_finished": definition_of_finished,
    }

    # Structural validation
    valid = bool(constraint_type) and bool(constraint_value) and bool(definition_of_finished)

    missing = []
    if not constraint_type:
        missing.append("constraint_type")
    if not constraint_value:
        missing.append("constraint_value")
    if not definition_of_finished:
        missing.append("definition_of_finished")

    return {
        "constraint_framing": constraint_framing,
        "valid": valid,
        "missing": missing,
        "force_constraint": False,
    }
