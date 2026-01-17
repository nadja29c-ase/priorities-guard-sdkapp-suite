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


# ============================================================================
# Step 2: Deliverable Identification Logic (Structural Validation Only)
# ============================================================================


def validate_initiative_framing_complete(framing: dict | None) -> dict[str, Any]:
    """
    Validate that initiative_framing from Step 1 is complete.

    Required fields: who, what, constraint_type, constraint_value, definition_of_finished
    Optional: why (can be None or empty)

    Args:
        framing: Combined initiative_framing object from Step 1

    Returns:
        {"valid": bool, "missing": list[str]}
    """
    if framing is None:
        return {
            "valid": False,
            "missing": ["initiative_framing (entire object missing)"],
        }

    required_fields = [
        "who",
        "what",
        "constraint_type",
        "constraint_value",
        "definition_of_finished",
    ]

    missing = []
    for field in required_fields:
        value = framing.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)

    return {
        "valid": len(missing) == 0,
        "missing": missing,
    }


def validate_e2e_deliverables(
    framing: dict | None,
    deliverables: list[dict] | None,
    confidence: str | None,
) -> dict[str, Any]:
    """
    Validate deliverables for identify_e2e_deliverables tool.

    Validation order:
    1. Confidence must be "high"
    2. Framing must be complete
    3. Deliverables must exist and be valid

    Args:
        framing: Combined initiative_framing from Step 1
        deliverables: List of candidate deliverables
        confidence: LLM's confidence level

    Returns:
        {
            "valid": bool,
            "error_type": str | None,
            "error_details": str | None,
            "confirmed_deliverables": list[dict] | None,
            "count": int,
        }
    """
    # 1. Confidence check first
    if confidence != "high":
        return {
            "valid": False,
            "error_type": "confidence_too_low",
            "error_details": f"Confidence '{confidence}' rejected. Only 'high' accepted.",
            "confirmed_deliverables": None,
            "count": 0,
        }

    # 2. Framing validation
    framing_result = validate_initiative_framing_complete(framing)
    if not framing_result["valid"]:
        return {
            "valid": False,
            "error_type": "missing_framing",
            "error_details": f"Missing framing fields: {', '.join(framing_result['missing'])}",
            "confirmed_deliverables": None,
            "count": 0,
        }

    # 3. Deliverables validation
    if deliverables is None or len(deliverables) == 0:
        return {
            "valid": False,
            "error_type": "empty_deliverables",
            "error_details": "No deliverables provided.",
            "confirmed_deliverables": None,
            "count": 0,
        }

    if len(deliverables) > 10:
        return {
            "valid": False,
            "error_type": "too_many_deliverables",
            "error_details": f"Maximum 10 deliverables allowed. Received {len(deliverables)}.",
            "confirmed_deliverables": None,
            "count": len(deliverables),
        }

    # Validate each deliverable and normalize
    confirmed = []
    for i, d in enumerate(deliverables):
        name = d.get("name")
        if name is None or (isinstance(name, str) and not name.strip()):
            return {
                "valid": False,
                "error_type": "invalid_deliverable",
                "error_details": f"Deliverable at index {i} has empty or missing name.",
                "confirmed_deliverables": None,
                "count": len(deliverables),
            }

        # Normalize: ensure description exists (empty string if missing)
        confirmed.append({
            "name": name.strip() if isinstance(name, str) else name,
            "description": (d.get("description") or "").strip(),
        })

    return {
        "valid": True,
        "error_type": None,
        "error_details": None,
        "confirmed_deliverables": confirmed,
        "count": len(confirmed),
    }


def validate_cutoff_selection(
    framing: dict | None,
    deliverables: list[dict] | None,
    selected_name: str | None,
    confidence: str | None,
) -> dict[str, Any]:
    """
    Validate cutoff selection for select_cutoff_deliverable tool.

    Validation order:
    1. Confidence must be "high"
    2. Framing must be complete
    3. Deliverables must exist
    4. Selected name must match exactly one deliverable

    Args:
        framing: Combined initiative_framing from Step 1
        deliverables: Confirmed deliverables from Step 2.1
        selected_name: Name of deliverable chosen as cutoff
        confidence: LLM's confidence level

    Returns:
        {
            "valid": bool,
            "error_type": str | None,
            "error_details": str | None,
            "focus_deliverable": dict | None,
            "deferred_deliverables": list[dict] | None,
        }
    """
    # 1. Confidence check first
    if confidence != "high":
        return {
            "valid": False,
            "error_type": "confidence_too_low",
            "error_details": f"Confidence '{confidence}' rejected. Only 'high' accepted.",
            "focus_deliverable": None,
            "deferred_deliverables": None,
        }

    # 2. Framing validation
    framing_result = validate_initiative_framing_complete(framing)
    if not framing_result["valid"]:
        return {
            "valid": False,
            "error_type": "missing_framing",
            "error_details": f"Missing framing fields: {', '.join(framing_result['missing'])}",
            "focus_deliverable": None,
            "deferred_deliverables": None,
        }

    # 3. Deliverables validation
    if deliverables is None or len(deliverables) == 0:
        return {
            "valid": False,
            "error_type": "missing_deliverables",
            "error_details": "No confirmed deliverables provided.",
            "focus_deliverable": None,
            "deferred_deliverables": None,
        }

    # 4. Duplicate name check (prevents silent data loss)
    names = [d.get("name", "") for d in deliverables]
    if len(names) != len(set(names)):
        return {
            "valid": False,
            "error_type": "duplicate_deliverable_names",
            "error_details": "Confirmed deliverables contain duplicate names. Each deliverable must have a unique name.",
            "focus_deliverable": None,
            "deferred_deliverables": None,
        }

    # 5. Selection validation
    if selected_name is None or (isinstance(selected_name, str) and not selected_name.strip()):
        return {
            "valid": False,
            "error_type": "empty_selection",
            "error_details": "No deliverable selected.",
            "focus_deliverable": None,
            "deferred_deliverables": None,
        }

    selected_name = selected_name.strip() if isinstance(selected_name, str) else selected_name

    # 6. Find matching deliverable (case-sensitive)
    focus = None
    deferred = []
    for d in deliverables:
        d_name = d.get("name", "")
        if d_name == selected_name:
            focus = {
                "name": d_name,
                "description": d.get("description", ""),
            }
        else:
            deferred.append({
                "name": d_name,
                "description": d.get("description", ""),
            })

    if focus is None:
        return {
            "valid": False,
            "error_type": "selection_not_found",
            "error_details": f"'{selected_name}' does not match any confirmed deliverable.",
            "focus_deliverable": None,
            "deferred_deliverables": None,
        }

    return {
        "valid": True,
        "error_type": None,
        "error_details": None,
        "focus_deliverable": focus,
        "deferred_deliverables": deferred,
    }
