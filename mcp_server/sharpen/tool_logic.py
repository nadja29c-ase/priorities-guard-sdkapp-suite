"""
Pure business logic for Sharpen tools.

Contains stateless functions that can be tested independently of MCP types.
"""

from typing import Any


# ============================================================================
# Constants for Vague Word Detection
# ============================================================================

# Words that indicate vague WHAT (not concrete deliverable)
VAGUE_WHAT_WORDS = [
    "improve", "better", "fix", "work on", "handle",
    "deal with", "address", "enhance", "optimize"
]

# Verbs that indicate activity-based WHAT (not artifact)
ACTIVITY_VERBS = [
    "do", "make", "create", "build", "work", "handle",
    "deal", "manage", "run", "execute", "perform"
]

# Words that indicate vague constraint value
VAGUE_CONSTRAINT_WORDS = [
    "soon", "flexible", "not sure", "whenever", "no rush",
    "asap", "when possible", "eventually", "sometime"
]

# Words that indicate vague definition of finished
VAGUE_FINISHED_WORDS = [
    "done", "complete", "finished", "ready", "working",
    "good", "acceptable", "satisfactory", "ok", "fine"
]


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
# Step 1: Initiative Framing Logic
# ============================================================================

def _contains_vague_word(text: str, vague_words: list[str]) -> bool:
    """Check if text contains any vague word (case-insensitive substring match)."""
    text_lower = text.lower()
    return any(word.lower() in text_lower for word in vague_words)


def _starts_with_activity_verb(text: str) -> bool:
    """Check if text starts with an activity verb (indicates activity, not artifact)."""
    text_lower = text.lower().strip()
    for verb in ACTIVITY_VERBS:
        if text_lower.startswith(verb + " ") or text_lower == verb:
            return True
    return False


def validate_initiative_intent(
    who: str | None,
    what: str | None,
    why: str | None = None,
) -> dict[str, Any]:
    """
    Validate WHO and WHAT for initiative intent framing.

    WHY is optional and never affects confidence — it's only used
    to stress-test WHAT clarity.

    Args:
        who: Who benefits from this work?
        what: What artifact/deliverable must exist?
        why: Optional — so that the beneficiary benefits how?

    Returns:
        Pure domain data with confidence and clarification needs
    """
    # Normalize inputs
    who = (who or "").strip()
    what = (what or "").strip()
    why = (why or "").strip() if why else None

    # Build framing intent
    framing_intent = {
        "who": who,
        "what": what,
        "why": why,
    }

    # Check WHO validity
    if not who or len(who) < 3:
        return {
            "framing_intent": framing_intent,
            "confidence": "low",
            "needs_clarification": True,
            "clarify_type": "WHO",
        }

    # Check WHAT validity
    if not what or len(what) < 5:
        return {
            "framing_intent": framing_intent,
            "confidence": "low",
            "needs_clarification": True,
            "clarify_type": "WHAT",
        }

    # Check for vague WHAT
    if _contains_vague_word(what, VAGUE_WHAT_WORDS):
        return {
            "framing_intent": framing_intent,
            "confidence": "medium",
            "needs_clarification": True,
            "clarify_type": "WHAT",
        }

    # Check for activity-based WHAT
    if _starts_with_activity_verb(what):
        return {
            "framing_intent": framing_intent,
            "confidence": "medium",
            "needs_clarification": True,
            "clarify_type": "WHAT",
        }

    # All valid — high confidence
    return {
        "framing_intent": framing_intent,
        "confidence": "high",
        "needs_clarification": False,
        "clarify_type": None,
    }


def validate_initiative_constraints(
    confirmed_intent: dict | None,
    constraint_type: str | None = None,
    constraint_value: str | None = None,
    definition_of_finished: str | None = None,
    user_claims_no_constraints: bool = False,
) -> dict[str, Any]:
    """
    Validate constraints and definition of finished for initiative framing.

    Requires confirmed intent from validate_initiative_intent.
    Rejects "no constraints" — forces user to identify MVP.

    Args:
        confirmed_intent: Output from frame_initiative_intent (who, what, why)
        constraint_type: time, capacity, budget, or forced_mvp
        constraint_value: The specific constraint in user's words
        definition_of_finished: How will you know WHAT is finished?
        user_claims_no_constraints: True if user claims no constraints

    Returns:
        Pure domain data with confidence and clarification needs
    """
    # Validate confirmed_intent exists and has required fields
    if not confirmed_intent:
        return {
            "initiative_framing": None,
            "confidence": "low",
            "needs_clarification": False,
            "clarify_type": None,
            "force_constraint": False,
            "intent_missing": True,
        }

    who = (confirmed_intent.get("who") or "").strip()
    what = (confirmed_intent.get("what") or "").strip()
    why = confirmed_intent.get("why")
    if why:
        why = why.strip() if why else None

    if not who or not what:
        return {
            "initiative_framing": None,
            "confidence": "low",
            "needs_clarification": False,
            "clarify_type": None,
            "force_constraint": False,
            "intent_missing": True,
        }

    # Normalize inputs
    constraint_type = (constraint_type or "").strip() or None
    constraint_value = (constraint_value or "").strip() or None
    definition_of_finished = (definition_of_finished or "").strip() or None

    # Build initiative framing (merge intent with constraints)
    initiative_framing = {
        "who": who,
        "what": what,
        "why": why,
        "constraint_type": constraint_type,
        "constraint_value": constraint_value,
        "definition_of_finished": definition_of_finished,
    }

    # Handle user claiming no constraints — framing is NOT finalized
    # This is a blocking clarification loop, not a valid state
    if user_claims_no_constraints:
        return {
            "initiative_framing": None,
            "confidence": "low",
            "needs_clarification": False,
            "clarify_type": None,
            "force_constraint": True,
            "intent_missing": False,
        }

    # Check constraint_type first — ONE dominant constraint must be identified
    if not constraint_type:
        return {
            "initiative_framing": initiative_framing,
            "confidence": "low",
            "needs_clarification": True,
            "clarify_type": "CONSTRAINT",
            "force_constraint": False,
            "intent_missing": False,
        }

    # Check constraint_value validity (constraint_type is guaranteed to exist)
    if not constraint_value:
        return {
            "initiative_framing": initiative_framing,
            "confidence": "low",
            "needs_clarification": True,
            "clarify_type": "CONSTRAINT",
            "force_constraint": False,
            "intent_missing": False,
        }

    if constraint_value and _contains_vague_word(constraint_value, VAGUE_CONSTRAINT_WORDS):
        return {
            "initiative_framing": initiative_framing,
            "confidence": "medium",
            "needs_clarification": True,
            "clarify_type": "CONSTRAINT",
            "force_constraint": False,
            "intent_missing": False,
        }

    # Check definition_of_finished validity
    if not definition_of_finished:
        return {
            "initiative_framing": initiative_framing,
            "confidence": "low",
            "needs_clarification": True,
            "clarify_type": "FINISHED",
            "force_constraint": False,
            "intent_missing": False,
        }

    if _contains_vague_word(definition_of_finished, VAGUE_FINISHED_WORDS):
        return {
            "initiative_framing": initiative_framing,
            "confidence": "medium",
            "needs_clarification": True,
            "clarify_type": "FINISHED",
            "force_constraint": False,
            "intent_missing": False,
        }

    # All valid — high confidence
    return {
        "initiative_framing": initiative_framing,
        "confidence": "high",
        "needs_clarification": False,
        "clarify_type": None,
        "force_constraint": False,
        "intent_missing": False,
    }
