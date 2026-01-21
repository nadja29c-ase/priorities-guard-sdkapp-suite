# SHARPEN V1 — INCREMENT 3.6.1: Primary Beneficiary Validation

## Objective

Reject WHO with multiple stakeholders. Force primary beneficiary selection.

---

## Files to Modify

1. `mcp_server/sharpen/tool_logic.py`
2. `mcp_server/sharpen/tools/frame_initiative_intent.py`

---

## Change 1: `tool_logic.py`

### Add helper function (before `validate_initiative_intent`)

```python
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
```

### Update `validate_initiative_intent` return structure

After structural validation passes (all fields present), add:

```python
# Check for multiple stakeholders
if _has_multiple_stakeholders(who):
    return {
        "framing_intent": {"who": who, "what": what, "why": why},
        "valid": False,
        "missing": [],
        "multiple_stakeholders": True,
    }
```

Ensure the valid=True return includes `"multiple_stakeholders": False`.

---

## Change 2: `frame_initiative_intent.py`

### Update INPUT_SCHEMA `who` description

```python
"who": {
    "type": "string",
    "description": "ONE primary beneficiary. Who benefits first and foremost? Not multiple audiences. ACCORDING TO THE USER.",
},
```

### Add guidance constant

```python
GUIDANCE_MULTIPLE_STAKEHOLDERS = (
    "SHARPEN MODE STILL BINDING. "
    "Multiple stakeholders detected. Ask: 'Who benefits first and foremost?' "
    "Then stop and wait. Frame confirmation as '[WHO] primarily benefits from this.'"
)
```

### Update handler

After structural validation, before returning success:

```python
# Check for multiple stakeholders
if result.get("multiple_stakeholders"):
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text="Multiple stakeholders detected. Need primary beneficiary.",
        )],
        structuredContent={
            "error": "multiple_stakeholders",
            "who_provided": result["framing_intent"]["who"],
            "recovery_hint": "Ask user to name ONE primary beneficiary",
            "assistant_guidance": {
                "action": "ASK_CLARIFYING",
                "instruction": GUIDANCE_MULTIPLE_STAKEHOLDERS,
            },
        },
        isError=True,
    )
```

---

## Unit Tests

### `test_tool_logic.py` (add to TestValidateInitiativeIntent)

```python
def test_multiple_stakeholders_and_pattern(self):
    """WHO with 'and' returns multiple_stakeholders=True."""
    result = validate_initiative_intent(
        who="The team and the client",
        what="A dashboard",
        why="To track progress",
    )
    assert result["valid"] is False
    assert result["multiple_stakeholders"] is True

def test_multiple_stakeholders_comma_pattern(self):
    """WHO with comma list returns multiple_stakeholders=True."""
    result = validate_initiative_intent(
        who="Engineers, designers, PMs",
        what="A dashboard",
        why="To track progress",
    )
    assert result["valid"] is False
    assert result["multiple_stakeholders"] is True

def test_multiple_stakeholders_or_pattern(self):
    """WHO with 'or' returns multiple_stakeholders=True."""
    result = validate_initiative_intent(
        who="The client or leadership",
        what="A report",
        why="To show progress",
    )
    assert result["valid"] is False
    assert result["multiple_stakeholders"] is True

def test_composite_audience_sales_and_marketing(self):
    """Known composite 'Sales and Marketing' is valid."""
    result = validate_initiative_intent(
        who="Sales and Marketing team",
        what="A dashboard",
        why="To track leads",
    )
    assert result["valid"] is True
    assert result.get("multiple_stakeholders") is False

def test_composite_audience_r_and_d(self):
    """Known composite 'Research and Development' is valid."""
    result = validate_initiative_intent(
        who="Research and Development",
        what="A tool",
        why="To speed up experiments",
    )
    assert result["valid"] is True
    assert result.get("multiple_stakeholders") is False

def test_single_stakeholder_valid(self):
    """WHO with single stakeholder is valid."""
    result = validate_initiative_intent(
        who="New engineering hires",
        what="A checklist",
        why="To onboard faster",
    )
    assert result["valid"] is True
    assert result.get("multiple_stakeholders") is False
```

---

## Out of Scope

- DESCRIPTION changes
- Other tools

---

**Document Status:** Ready for Claude Code execution