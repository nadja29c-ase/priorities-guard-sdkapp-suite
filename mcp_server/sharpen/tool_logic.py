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
    why: str | None,
) -> dict[str, Any]:
    """
    Validate structure of WHO, WHAT, and WHY for initiative intent.

    Structural validation only — semantic quality is LLM's job.

    Args:
        who: Who benefits from this work?
        what: What artifact/deliverable must exist?
        why: Mandatory — so that the beneficiary benefits how?

    Returns:
        framing_intent dict + valid flag
    """
    # Normalize inputs
    who = (who or "").strip()
    what = (what or "").strip()
    why = (why or "").strip()

    # Structural validation only — all three are required
    valid = bool(who) and bool(what) and bool(why)

    missing = []
    if not who:
        missing.append("who")
    if not what:
        missing.append("what")
    if not why:
        missing.append("why")

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
    user_claims_no_constraints: bool = False,
) -> dict[str, Any]:
    """
    Validate structure of constraints.

    Structural validation only — semantic quality is LLM's job.

    Args:
        constraint_type: time, capacity, budget, or forced_mvp
        constraint_value: The specific constraint in user's words
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

    # Build constraint framing
    constraint_framing = {
        "constraint_type": constraint_type,
        "constraint_value": constraint_value,
    }

    # Structural validation
    valid = bool(constraint_type) and bool(constraint_value)

    missing = []
    if not constraint_type:
        missing.append("constraint_type")
    if not constraint_value:
        missing.append("constraint_value")

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

    Required fields: who, what, why, constraint_type, constraint_value

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
        "why",
        "constraint_type",
        "constraint_value",
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
    sculpted: dict | None,
    confidence: str | None,
) -> dict[str, Any]:
    """
    Validate cutoff selection for select_cutoff_deliverable tool.

    Supports two paths:
    - Selection: Pick existing deliverable by exact name
    - Sculpting: Define new focus that replaces one or more confirmed deliverables

    Validation order:
    1. Confidence must be "high"
    2. Framing must be complete
    3. Deliverables must exist and not be empty
    4. Duplicate deliverable names check
    5. Mutual exclusivity: exactly one of selected_name or sculpted
    6. If selected_name: validate exact match
    7. If sculpted: validate sculpt

    Args:
        framing: Combined initiative_framing from Step 1
        deliverables: Confirmed deliverables from Step 2.1
        selected_name: Name of deliverable chosen as cutoff (selection path)
        sculpted: Dict with name, description, replaces (sculpt path)
        confidence: LLM's confidence level

    Returns:
        {
            "valid": bool,
            "error_type": str | None,
            "error_details": str | None,
            "focus_deliverable": dict | None,
            "deferred_deliverables": list[dict] | None,
            "_internal_replaces": list[str] | None,  # Only for sculpt path, handler use only
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
    confirmed_names = [d.get("name", "") for d in deliverables]
    if len(confirmed_names) != len(set(confirmed_names)):
        return {
            "valid": False,
            "error_type": "duplicate_deliverable_names",
            "error_details": "Confirmed deliverables contain duplicate names. Each deliverable must have a unique name.",
            "focus_deliverable": None,
            "deferred_deliverables": None,
        }

    # 5. Mutual exclusivity check
    has_selected = selected_name is not None and (
        isinstance(selected_name, str) and selected_name.strip()
    )
    has_sculpted = sculpted is not None

    if has_selected and has_sculpted:
        return {
            "valid": False,
            "error_type": "both_selection_methods",
            "error_details": "Provide selected_deliverable_name OR sculpted_deliverable, not both.",
            "focus_deliverable": None,
            "deferred_deliverables": None,
        }

    if not has_selected and not has_sculpted:
        return {
            "valid": False,
            "error_type": "no_selection_method",
            "error_details": "Provide selected_deliverable_name OR sculpted_deliverable.",
            "focus_deliverable": None,
            "deferred_deliverables": None,
        }

    # 6. Selection path
    if has_selected:
        selected_name = selected_name.strip()

        # Find matching deliverable (case-sensitive)
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

    # 7. Sculpt path
    sculpt_name = (sculpted.get("name") or "").strip()
    sculpt_description = (sculpted.get("description") or "").strip()
    replaces = sculpted.get("replaces") or []

    # Validate sculpt name not empty
    if not sculpt_name:
        return {
            "valid": False,
            "error_type": "empty_sculpt_name",
            "error_details": "Sculpted deliverable must have a name.",
            "focus_deliverable": None,
            "deferred_deliverables": None,
        }

    # Validate replaces not empty
    if not replaces:
        return {
            "valid": False,
            "error_type": "empty_replaces",
            "error_details": "Sculpted deliverable must replace at least one confirmed deliverable.",
            "focus_deliverable": None,
            "deferred_deliverables": None,
        }

    # Validate all replaces exist in confirmed_deliverables
    confirmed_names_set = set(confirmed_names)
    invalid_replaces = [r for r in replaces if r not in confirmed_names_set]
    if invalid_replaces:
        return {
            "valid": False,
            "error_type": "invalid_replaces",
            "error_details": f"These names are not in confirmed deliverables: {', '.join(invalid_replaces)}",
            "focus_deliverable": None,
            "deferred_deliverables": None,
        }

    # Build focus (clean output — no process metadata)
    focus = {
        "name": sculpt_name,
        "description": sculpt_description,
    }

    # Compute deferred (confirmed minus replaced)
    replaces_set = set(replaces)
    deferred = [
        {"name": d.get("name", ""), "description": d.get("description", "")}
        for d in deliverables
        if d.get("name", "") not in replaces_set
    ]

    return {
        "valid": True,
        "error_type": None,
        "error_details": None,
        "focus_deliverable": focus,
        "deferred_deliverables": deferred,
        "_internal_replaces": replaces,  # For handler guidance only, not in Step 3 contract
    }


# ============================================================================
# Step 3: Commit Good Enough Logic (Structural Validation Only)
# ============================================================================


def validate_good_enough(
    framing: dict | None,
    focus: dict | None,
    good_enough: str | None,
    confidence: str | None,
) -> dict[str, Any]:
    """
    Validate Step 3: good enough stopping line.

    Args:
        framing: Combined initiative_framing from Step 1
        focus: Focus deliverable from Step 2.2
        good_enough: User's definition of "good enough" to stop this week
        confidence: LLM's confidence level

    Returns:
        dict with keys:
        - valid: bool
        - error_type: str | None
        - error_details: str | None
        - sharpened_scope: dict | None (if valid)
    """
    # Check confidence first
    if confidence != "high":
        return {
            "valid": False,
            "error_type": "confidence_too_low",
            "error_details": f"Confidence '{confidence}' rejected. Only 'high' accepted.",
            "sharpened_scope": None,
        }

    # Check framing exists
    if not framing:
        return {
            "valid": False,
            "error_type": "missing_framing",
            "error_details": "Initiative framing required. Complete Step 1 first.",
            "sharpened_scope": None,
        }

    # Check framing has required fields
    required_framing = ["who", "what", "why", "constraint_type", "constraint_value"]
    missing_framing = [f for f in required_framing if not framing.get(f)]
    if missing_framing:
        return {
            "valid": False,
            "error_type": "missing_framing",
            "error_details": f"Initiative framing incomplete. Missing: {', '.join(missing_framing)}",
            "sharpened_scope": None,
        }

    # Check focus exists
    if not focus:
        return {
            "valid": False,
            "error_type": "missing_focus",
            "error_details": "Focus deliverable required. Complete Step 2 first.",
            "sharpened_scope": None,
        }

    # Check focus has name
    if not focus.get("name"):
        return {
            "valid": False,
            "error_type": "missing_focus",
            "error_details": "Focus deliverable name required.",
            "sharpened_scope": None,
        }

    # Check good_enough exists and is non-empty
    if not good_enough or not good_enough.strip():
        return {
            "valid": False,
            "error_type": "empty_definition",
            "error_details": "Good enough definition required.",
            "sharpened_scope": None,
        }

    # All valid — build sharpened scope
    return {
        "valid": True,
        "error_type": None,
        "error_details": None,
        "sharpened_scope": {
            "initiative_framing": framing,
            "focus_deliverable": focus,
            "good_enough_definition": good_enough.strip(),
        },
    }
