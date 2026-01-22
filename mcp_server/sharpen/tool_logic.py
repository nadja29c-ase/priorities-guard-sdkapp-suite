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

# Known composite terms that represent single audiences
_COMPOSITE_AUDIENCES = [
    "sales and marketing",
    "research and development",
    "r&d",
    "product and engineering",
    "product and design",
    "design and engineering",
    "ops and support",
    "hr and recruiting",
    "finance and accounting",
    "parents and caregivers",
    "customers and prospects",
]


def _has_multiple_stakeholders(who: str) -> bool:
    """Detect if WHO contains multiple distinct stakeholders."""
    who_lower = who.lower()

    # Allow known composite audiences
    for phrase in _COMPOSITE_AUDIENCES:
        if phrase in who_lower:
            return False

    # Detect multiple stakeholder patterns
    if " and " in who_lower:
        return True
    if " or " in who_lower:
        return True
    if ", " in who_lower:
        return True

    return False


def validate_initiative_intent(
    who: str | None,
    why: str | None,
) -> dict[str, Any]:
    """
    Validate structure of WHO and WHY for initiative intent.

    Structural validation only — semantic quality is LLM's job.

    Args:
        who: Who benefits from this work?
        why: So that the beneficiary benefits how? (outcome-phrased)

    Returns:
        framing_intent dict + valid flag
    """
    # Normalize inputs
    who = (who or "").strip()
    why = (why or "").strip()

    # Structural validation only — both are required
    missing = []
    if not who:
        missing.append("who")
    if not why:
        missing.append("why")

    # If any fields missing, return early
    if missing:
        return {
            "framing_intent": {
                "who": who,
                "why": why,
            },
            "valid": False,
            "missing": missing,
        }

    # Check for multiple stakeholders
    if _has_multiple_stakeholders(who):
        return {
            "framing_intent": {"who": who, "why": why},
            "valid": False,
            "missing": [],
            "multiple_stakeholders": True,
        }

    return {
        "framing_intent": {
            "who": who,
            "why": why,
        },
        "valid": True,
        "missing": [],
        "multiple_stakeholders": False,
    }


def validate_initiative_hypothesis(
    who: str | None,
    why: str | None,
    what: str | None,
) -> dict[str, Any]:
    """
    Validate structure of WHAT hypothesis given confirmed WHO + WHY.

    Structural validation only — semantic quality is LLM's job.

    Args:
        who: Confirmed WHO from frame_initiative_intent
        why: Confirmed WHY from frame_initiative_intent
        what: User's hypothesized solution

    Returns:
        framing dict + valid flag
    """
    # Normalize inputs
    who = (who or "").strip()
    why = (why or "").strip()
    what = (what or "").strip()

    # Check prior step completed
    missing_prior = []
    if not who:
        missing_prior.append("who")
    if not why:
        missing_prior.append("why")

    if missing_prior:
        return {
            "framing": None,
            "valid": False,
            "error_type": "missing_prior_step",
            "error_details": f"frame_initiative_intent must be completed first. Missing: {', '.join(missing_prior)}",
        }

    # Check WHAT provided
    if not what:
        return {
            "framing": None,
            "valid": False,
            "error_type": "missing_what",
            "error_details": "WHAT hypothesis required.",
        }

    return {
        "framing": {
            "who": who,
            "why": why,
            "what": what,
        },
        "valid": True,
        "error_type": None,
        "error_details": None,
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
    deferred: list[str] | None,
    selected_name: str | None,
    sculpted: dict | None,
    confidence: str | None,
) -> dict[str, Any]:
    """
    Validate cutoff selection for select_focus_deliverable tool.

    Supports two paths:
    - Selection: Pick existing deliverable by exact name from remaining
    - Sculpting: Define new focus that replaces one or more remaining deliverables

    Validation order:
    1. Confidence must be "high"
    2. Framing must be complete
    3. Deliverables must exist and not be empty
    4. Duplicate deliverable names check
    5. Deferred validation (required, all names must exist in confirmed)
    6. Compute remaining = confirmed - deferred
    7. Over-cutting check (at least one must remain)
    8. Auto-select if only one remains
    9. Ambiguity check if multiple remain without selection
    10. Selection/sculpt validates against remaining (not confirmed)

    Args:
        framing: Combined initiative_framing from Step 1
        deliverables: Confirmed deliverables from Step 2.1
        deferred: List of deliverable names explicitly deferred during realism/value loop
        selected_name: Name of deliverable chosen as focus (selection path)
        sculpted: Dict with name, description, replaces (sculpt path)
        confidence: LLM's confidence level

    Returns:
        {
            "valid": bool,
            "error_type": str | None,
            "error_details": str | None,
            "focus_deliverable": dict | None,
            "deferred_deliverables": list[dict] | None,
            "auto_selected": bool | None,  # True if single remaining was auto-selected
            "remaining_names": list[str] | None,  # For ambiguous_remaining error
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
    confirmed_names_set = set(confirmed_names)
    if len(confirmed_names) != len(confirmed_names_set):
        return {
            "valid": False,
            "error_type": "duplicate_deliverable_names",
            "error_details": "Confirmed deliverables contain duplicate names. Each deliverable must have a unique name.",
            "focus_deliverable": None,
            "deferred_deliverables": None,
        }

    # 5. Deferred validation
    if deferred is None:
        return {
            "valid": False,
            "error_type": "missing_deferred",
            "error_details": "deferred_deliverables parameter required. Run realism/value loop first.",
            "focus_deliverable": None,
            "deferred_deliverables": None,
        }

    # Validate all deferred names exist in confirmed
    invalid_deferred = [name for name in deferred if name not in confirmed_names_set]
    if invalid_deferred:
        return {
            "valid": False,
            "error_type": "invalid_deferred",
            "error_details": f"These deferred names are not in confirmed deliverables: {', '.join(invalid_deferred)}",
            "focus_deliverable": None,
            "deferred_deliverables": None,
        }

    # 6. Compute remaining deliverables
    deferred_set = set(deferred)
    remaining = [d for d in deliverables if d.get("name", "") not in deferred_set]
    remaining_names_set = set(d.get("name", "") for d in remaining)

    # 7. Over-cutting check
    if len(remaining) == 0:
        return {
            "valid": False,
            "error_type": "over_cutting",
            "error_details": "All deliverables were deferred. At least one must remain.",
            "focus_deliverable": None,
            "deferred_deliverables": None,
        }

    # Check selection method presence
    has_selected = selected_name is not None and (
        isinstance(selected_name, str) and selected_name.strip()
    )
    has_sculpted = sculpted is not None

    # Both methods provided
    if has_selected and has_sculpted:
        return {
            "valid": False,
            "error_type": "both_selection_methods",
            "error_details": "Provide selected_deliverable_name OR sculpted_deliverable, not both.",
            "focus_deliverable": None,
            "deferred_deliverables": None,
        }

    # 8. Auto-select if only one remains and no explicit selection
    if len(remaining) == 1 and not has_selected and not has_sculpted:
        focus = {
            "name": remaining[0].get("name", ""),
            "description": remaining[0].get("description", ""),
        }
        # Deferred output includes all explicit deferrals
        deferred_output = [
            {"name": d.get("name", ""), "description": d.get("description", "")}
            for d in deliverables
            if d.get("name", "") in deferred_set
        ]
        return {
            "valid": True,
            "error_type": None,
            "error_details": None,
            "focus_deliverable": focus,
            "deferred_deliverables": deferred_output,
            "auto_selected": True,
        }

    # 9. Ambiguity check — multiple remaining but no selection
    if not has_selected and not has_sculpted:
        remaining_names = [d.get("name", "") for d in remaining]
        return {
            "valid": False,
            "error_type": "ambiguous_remaining",
            "error_details": f"Multiple deliverables remain: {', '.join(remaining_names)}. Select one.",
            "focus_deliverable": None,
            "deferred_deliverables": None,
            "remaining_names": remaining_names,
        }

    # 10. Selection path — validate against remaining
    if has_selected:
        selected_name = selected_name.strip()

        if selected_name not in remaining_names_set:
            # Check if it was deferred
            if selected_name in deferred_set:
                return {
                    "valid": False,
                    "error_type": "selection_was_deferred",
                    "error_details": f"'{selected_name}' was deferred. Select from remaining: {', '.join(remaining_names_set)}",
                    "focus_deliverable": None,
                    "deferred_deliverables": None,
                }
            # Check if it exists at all
            if selected_name not in confirmed_names_set:
                return {
                    "valid": False,
                    "error_type": "selection_not_found",
                    "error_details": f"'{selected_name}' does not match any confirmed deliverable.",
                    "focus_deliverable": None,
                    "deferred_deliverables": None,
                }

        # Find the selected deliverable
        focus = None
        for d in remaining:
            if d.get("name", "") == selected_name:
                focus = {
                    "name": d.get("name", ""),
                    "description": d.get("description", ""),
                }
                break

        # Compute deferred output: explicit deferrals + implicit deferrals (remaining but not selected)
        deferred_output = [
            {"name": d.get("name", ""), "description": d.get("description", "")}
            for d in deliverables
            if d.get("name", "") in deferred_set
               or (d.get("name", "") in remaining_names_set and d.get("name", "") != selected_name)
        ]

        return {
            "valid": True,
            "error_type": None,
            "error_details": None,
            "focus_deliverable": focus,
            "deferred_deliverables": deferred_output,
        }

    # 11. Sculpt path — validate replaces against remaining
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

    # Validate all replaces exist in REMAINING (not just confirmed)
    invalid_replaces = [r for r in replaces if r not in remaining_names_set]
    if invalid_replaces:
        # Check if any were deferred
        deferred_in_replaces = [r for r in invalid_replaces if r in deferred_set]
        if deferred_in_replaces:
            return {
                "valid": False,
                "error_type": "replaces_includes_deferred",
                "error_details": f"Cannot sculpt from deferred deliverables: {', '.join(deferred_in_replaces)}",
                "focus_deliverable": None,
                "deferred_deliverables": None,
            }
        return {
            "valid": False,
            "error_type": "invalid_replaces",
            "error_details": f"These names are not in remaining deliverables: {', '.join(invalid_replaces)}",
            "focus_deliverable": None,
            "deferred_deliverables": None,
        }

    # Build focus (clean output — no process metadata)
    focus = {
        "name": sculpt_name,
        "description": sculpt_description,
    }

    # Deferred = explicit deferrals + (remaining minus replaced)
    replaces_set = set(replaces)
    deferred_output = [
        {"name": d.get("name", ""), "description": d.get("description", "")}
        for d in deliverables
        if d.get("name", "") in deferred_set
           or (d.get("name", "") in remaining_names_set and d.get("name", "") not in replaces_set)
    ]

    return {
        "valid": True,
        "error_type": None,
        "error_details": None,
        "focus_deliverable": focus,
        "deferred_deliverables": deferred_output,
        "_internal_replaces": replaces,  # For handler guidance only, not in Step 3 contract
    }


# ============================================================================
# Step 3: Commit Good Enough Logic (Structural Validation Only)
# ============================================================================


def validate_good_enough(
    framing: dict | None,
    focus: dict | None,
    weeks_deliverable: str | None,
    confidence: str | None,
) -> dict[str, Any]:
    """
    Validate Step 3: week's deliverable stopping line.

    Args:
        framing: Combined initiative_framing from Step 1
        focus: Focus deliverable from Step 2.2
        weeks_deliverable: User's concrete deliverable for this week
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

    # Check weeks_deliverable exists and is non-empty
    if not weeks_deliverable or not weeks_deliverable.strip():
        return {
            "valid": False,
            "error_type": "empty_definition",
            "error_details": "Week's deliverable required.",
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
            "weeks_deliverable": weeks_deliverable.strip(),
        },
    }
