# SHARPEN V1 — INCREMENT 3.8: Split Intent Tool for WHY→WHAT Sequence Enforcement

## Claude Code Briefing

---

## Objective

Split `frame_initiative_intent` into two tools to structurally enforce the elicitation sequence: WHO + WHY first, WHAT second.

**Current state:** Single tool collects WHO, WHAT, WHY — LLM can ask in any order

**New state:** Two tools with dependency — Tool 2 requires Tool 1's output as input

---

## Design Rationale

### Problem

DESCRIPTION guidance says "ask pain/WHY first, then WHAT as hypothesis" but LLM ignores it. LLM frequently:
- Asks WHAT before understanding the problem
- Treats WHAT as solution rather than hypothesis
- Skips pain elicitation entirely

### Solution

Split into two tools with structural dependency:

```
frame_initiative_intent → WHO + WHY (pain-first, outcome-phrased)
    ↓ (output becomes required input)
frame_initiative_hypothesis → WHAT (requires confirmed WHO + WHY)
```

Tool 2 **cannot be called** without Tool 1's output. This makes sequence violation impossible.

### Benefits

1. **Sequence enforced:** WHAT literally cannot be recorded before WHY
2. **Hypothesis framing natural:** Separate step signals "this is provisional"
3. **Cleaner mental model:** Problem understanding → Solution hypothesis
4. **Better error recovery:** Each step fails independently

---

## Files to Create

1. `mcp_server/sharpen/tools/frame_initiative_hypothesis.py` (NEW)

## Files to Modify

1. `mcp_server/sharpen/tools/frame_initiative_intent.py`
2. `mcp_server/sharpen/tool_logic.py`
3. `tests/unit/mcp_sharpen/test_frame_initiative_intent.py`
4. `tests/unit/mcp_sharpen/test_frame_initiative_hypothesis.py` (NEW)

---

## Change 1: Update `frame_initiative_intent.py`

### Remove WHAT from schema

Remove `what` from INPUT_SCHEMA properties and required array:

```python
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "who": {
            "type": "string",
            "description": "ONE primary beneficiary. Who benefits first and foremost? Not multiple audiences. ACCORDING TO THE USER.",
        },
        "why": {
            "type": "string",
            "description": "So that WHO benefits HOW? Must be outcome-phrased (what changes), not pain-phrased. Elicit pain first, then reframe to outcome. ACCORDING TO THE USER.",
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "'high' = user stated WHO and WHY in their own words. 'low' = you inferred or filled gaps.",
        },
    },
    "required": ["who", "why", "confidence"],
    "additionalProperties": False,
}
```

### Update DESCRIPTION

```python
DESCRIPTION = """Records WHO benefits and WHY (outcome) for given initiative. WHAT comes later via frame_initiative_hypothesis. Requires confidence="high".

SHARPEN MODE — BINDING RULES (not guidelines)
When user selects Sharpen, your default assistant behavior is SUSPENDED.

SUSPENDED BEHAVIORS:
- Asking about solutions/WHAT before understanding the problem
- Batching multiple questions
- Inferring what the user "probably means"
- Planning or structuring for the user

ACTIVE BEHAVIORS:
- Ask ONE question at a time
- Wait for answer
- Reflect back and confirm
- Call tool only after confidence="high"

ELICITATION ORDER:
1. WHO: "Who specifically is supposed to benefit from this?"
2. PAIN: "What's currently hard or frustrating for them?"
3. (If pain is abstract) OBSERVABLE: "What would you see happening differently if this worked?"
4. REFRAME: Convert pain → outcome-phrased WHY
5. CONFIRM: "To confirm: [WHO] needs something so that [WHY]. Correct?"

CRITICAL: Do NOT ask about WHAT/solution yet. Problem understanding comes first.

PAIN → OUTCOME REFRAMING:
- User says: "They keep asking the same questions" (pain)
- You reframe: "So they can find answers without interrupting others" (outcome)
- User says: "They feel lost" (abstract pain)
- You probe: "What would you see them doing differently?"
- User says: "Taking on tasks independently"
- You reframe: "So they can work independently without hand-holding" (outcome)

EXAMPLE CONVERSATION:
  User: "I want to improve our onboarding"
  You: "Who specifically is supposed to benefit from this?"
  User: "New engineering hires"
  You: "What's currently hard or frustrating for new engineering hires?"
  User: "They keep asking the same basic questions and feel lost"
  You: "To confirm: New engineering hires need something so they can find answers without constantly interrupting others. Correct?"
  User: "Yes"
  → Call with who="New engineering hires", why="So they can find answers without constantly interrupting others", confidence="high"
  → Tool returns guidance to proceed to frame_initiative_hypothesis

CONFIDENCE:
HIGH: who="New engineering hires" why="So they can contribute without constant interruptions" — concrete, user-confirmed, outcome-phrased.
LOW: who="users" why="because onboarding matters" — vague, motivational, not outcome-phrased.
"""
```

### Update Pydantic Model

```python
class FrameIntentRequest(BaseModel):
    """Expected input structure from ChatGPT."""
    who: Optional[str] = None
    why: Optional[str] = None
    confidence: Optional[Literal["high", "medium", "low"]] = None
```

### Update GUIDANCE_CONFIRMED

```python
GUIDANCE_CONFIRMED = (
    "SHARPEN MODE STILL BINDING. "
    "Problem understanding confirmed. Now ask about the hypothesized solution:\n"
    "'What do you think needs to exist to help with that?'\n"
    "Then stop and wait. Do not suggest solutions.\n\n"
    "When user answers → call frame_initiative_hypothesis with the WHAT."
)
```

### Update GUIDANCE_MISSING_FIELDS

```python
GUIDANCE_MISSING_FIELDS = (
    "SHARPEN MODE STILL BINDING. "
    "Ask ONE question about the missing field:\n"
    "- Missing WHO: 'Who specifically is supposed to benefit from this?'\n"
    "- Missing WHY: 'What's currently hard or frustrating for them?'\n"
    "Then stop and wait. Do not ask about solutions yet."
)
```

### Update handler output

Change the success response text and structuredContent:

```python
return mcp_types.CallToolResult(
    content=[mcp_types.TextContent(
        type="text",
        text=f"Problem framing confirmed: {intent['who']} needs something so that {intent['why']}",
    )],
    structuredContent={
        "framing_intent": intent,  # Now only contains who + why
        "confidence": "high",
        "confirmed": True,
        "assistant_guidance": {
            "action": "PROCEED_TO_HYPOTHESIS",
            "instruction": GUIDANCE_CONFIRMED,
        },
    },
)
```

---

## Change 2: Update `tool_logic.py`

### Update `validate_initiative_intent`

Remove `what` parameter:

```python
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
```

### Add `validate_initiative_hypothesis`

```python
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
```

---

## Change 3: Create `frame_initiative_hypothesis.py`

Create new file at `mcp_server/sharpen/tools/frame_initiative_hypothesis.py`:

```python
"""
Frame Initiative Hypothesis Tool.

Captures WHAT (the hypothesized solution) after WHO + WHY are confirmed.
Requires prior step output as input to enforce sequence.
Self-registers at import time.
"""

from typing import Optional, Literal

import structlog
from mcp import types as mcp_types
from pydantic import BaseModel, ValidationError

from .base import ToolDefinition
from . import register_tool
from ..tool_logic import validate_initiative_hypothesis

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata (Goal-Oriented Description)
# ============================================================================

DESCRIPTION = """Records WHAT (the hypothesized solution) after problem is understood. Requires confirmed WHO + WHY from frame_initiative_intent. Requires confidence="high".

SHARPEN MODE — BINDING RULES (not guidelines)
When user selects Sharpen, your default assistant behavior is SUSPENDED.

SUSPENDED BEHAVIORS:
- Suggesting solutions
- Improving or "fixing" user's hypothesis
- Offering alternatives unprompted
- Jumping to planning or breakdown

ACTIVE BEHAVIORS:
- Ask ONE question: "What do you think needs to exist to help with that?"
- Wait for answer
- Reflect back as hypothesis
- Confirm with user
- Call tool with confidence="high"

WHAT AS HYPOTHESIS:
The user's WHAT is a hypothesis, not a commitment. Frame it that way:
- "You think [WHAT] might help [WHO] so that [WHY]."
- "This is your current hypothesis — we'll pressure-test it against constraints."

Do NOT evaluate whether it's a good solution. That comes later via constraints.

EXAMPLE CONVERSATION:
  [After frame_initiative_intent confirmed: who="New engineering hires", why="So they can find answers without interrupting others"]
  You: "What do you think needs to exist to help with that?"
  User: "A checklist they can follow in their first week"
  You: "Your hypothesis: A first-week checklist for new engineering hires so they can find answers without interrupting others. Correct?"
  User: "Yes"
  → Call with who="New engineering hires", why="So they can find answers without interrupting others", what="A first-week checklist", confidence="high"

CONFIDENCE:
HIGH: what="A first-week onboarding checklist" — concrete artifact, user-stated.
LOW: what="improve the onboarding experience" — activity, not artifact.
LOW: what="something to help them" — vague placeholder.
"""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "who": {
            "type": "string",
            "description": "Confirmed WHO from frame_initiative_intent. Must match prior step output.",
        },
        "why": {
            "type": "string",
            "description": "Confirmed WHY from frame_initiative_intent. Must match prior step output.",
        },
        "what": {
            "type": "string",
            "description": "User's HYPOTHESIZED solution — what they THINK needs to exist. Must be a concrete artifact, not an activity. ACCORDING TO THE USER.",
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "'high' = user stated WHAT in their own words as concrete artifact. 'low' = vague, activity-based, or inferred.",
        },
    },
    "required": ["who", "why", "what", "confidence"],
    "additionalProperties": False,
}


# ============================================================================
# Pydantic Models for Validation
# ============================================================================


class FrameHypothesisRequest(BaseModel):
    """Expected input structure from ChatGPT."""
    who: Optional[str] = None
    why: Optional[str] = None
    what: Optional[str] = None
    confidence: Optional[Literal["high", "medium", "low"]] = None


# ============================================================================
# Assistant Guidance Messages
# ============================================================================

GUIDANCE_CONFIDENCE_REJECTED = (
    "SHARPEN MODE STILL BINDING. "
    "WHAT must be a concrete artifact, not an activity or vague goal. "
    "Ask: 'What specific thing would exist that doesn't exist today?' "
    "Then stop and wait. Do not suggest solutions."
)

GUIDANCE_MISSING_PRIOR_STEP = (
    "SHARPEN MODE STILL BINDING. "
    "Cannot record hypothesis without confirmed problem understanding. "
    "Complete frame_initiative_intent first to establish WHO + WHY."
)

GUIDANCE_MISSING_WHAT = (
    "SHARPEN MODE STILL BINDING. "
    "Ask: 'What do you think needs to exist to help with that?' "
    "Then stop and wait. Do not suggest solutions."
)

GUIDANCE_CONFIRMED = (
    "SHARPEN MODE STILL BINDING. "
    "Hypothesis recorded. Now establish constraints.\n"
    "Ask: 'What's the one constraint that limits this most — a deadline, limited hours, or a budget cap?' "
    "Then stop and wait. Do not suggest constraints.\n\n"
    "When user answers → call frame_initiative_constraints."
)


# ============================================================================
# Tool Handler
# ============================================================================


async def handle(arguments: dict) -> mcp_types.CallToolResult:
    """Handle frame_initiative_hypothesis tool call."""
    logger.debug("frame_initiative_hypothesis.handle.start",
                 argument_keys=list(arguments.keys()))

    # Pydantic validation
    try:
        validated_request = FrameHypothesisRequest.model_validate(arguments)
    except ValidationError as e:
        logger.warning("frame_initiative_hypothesis.validation_failed", error=str(e.errors()))
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text="Invalid input format.")],
            structuredContent={"error": "validation_error", "details": e.errors()},
            isError=True,
        )

    # Reject low/medium confidence
    if validated_request.confidence != "high":
        logger.info("frame_initiative_hypothesis.confidence_rejected",
                    confidence=validated_request.confidence)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=f"Confidence '{validated_request.confidence}' rejected. Only 'high' accepted.",
            )],
            structuredContent={
                "error": "confidence_too_low",
                "confidence_provided": validated_request.confidence,
                "assistant_guidance": {
                    "action": "ASK_CLARIFYING",
                    "instruction": GUIDANCE_CONFIDENCE_REJECTED,
                },
            },
            isError=True,
        )

    # Structural validation
    result = validate_initiative_hypothesis(
        who=validated_request.who,
        why=validated_request.why,
        what=validated_request.what,
    )

    # Handle validation failures
    if not result["valid"]:
        error_type = result["error_type"]

        if error_type == "missing_prior_step":
            guidance = GUIDANCE_MISSING_PRIOR_STEP
            action = "REFUSE"
        elif error_type == "missing_what":
            guidance = GUIDANCE_MISSING_WHAT
            action = "ASK_CLARIFYING"
        else:
            guidance = "Unexpected error. Ask user to restate their hypothesized solution."
            action = "ASK_CLARIFYING"

        logger.info("frame_initiative_hypothesis.rejected",
                    error_type=error_type, action=action)

        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=result["error_details"],
            )],
            structuredContent={
                "error": error_type,
                "details": result["error_details"],
                "assistant_guidance": {
                    "action": action,
                    "instruction": guidance,
                },
            },
            isError=True,
        )

    # Valid — return confirmed framing
    framing = result["framing"]

    logger.info("frame_initiative_hypothesis.complete",
                who=framing["who"], what=framing["what"], confidence="high")

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Hypothesis confirmed: {framing['who']} needs {framing['what']} so that {framing['why']}",
        )],
        structuredContent={
            "framing_intent": framing,
            "confidence": "high",
            "confirmed": True,
            "assistant_guidance": {
                "action": "PROCEED_TO_CONSTRAINTS",
                "instruction": GUIDANCE_CONFIRMED,
            },
        },
    )


# ============================================================================
# Self-register at import time
# ============================================================================

register_tool(ToolDefinition(
    name="frame_initiative_hypothesis",
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    handle=handle,
    # OpenAI compliance annotations
    read_only_hint=False,
    destructive_hint=False,
    open_world_hint=False,
))
```

---

## Change 4: Register new tool in `__init__.py`

Add import in `mcp_server/sharpen/tools/__init__.py`:

```python
from . import frame_initiative_hypothesis  # Add with other imports
```

---

## Unit Tests

### Update `test_frame_initiative_intent.py`

Remove all tests involving `what` parameter. Update remaining tests to only use `who` and `why`.

Example update for `test_valid_intent_returns_framing`:

```python
def test_valid_intent_returns_framing(self):
    """Valid intent returns framing_intent with who and why."""
    result = validate_initiative_intent(
        who="New engineering hires",
        why="So they can contribute without interruptions",
    )

    assert result["valid"] is True
    assert result["framing_intent"]["who"] == "New engineering hires"
    assert result["framing_intent"]["why"] == "So they can contribute without interruptions"
    assert "what" not in result["framing_intent"]
```

### Create `test_frame_initiative_hypothesis.py`

```python
"""
Tests for frame_initiative_hypothesis tool.

Tests both pure logic (tool_logic.py) and handler.
"""

import pytest

from mcp_server.sharpen.tool_logic import validate_initiative_hypothesis
from mcp_server.sharpen.tools.frame_initiative_hypothesis import handle


class TestValidateInitiativeHypothesis:
    """Tests for validate_initiative_hypothesis function."""

    def test_valid_hypothesis_returns_framing(self):
        """Valid hypothesis returns complete framing."""
        result = validate_initiative_hypothesis(
            who="New engineering hires",
            why="So they can contribute without interruptions",
            what="A first-week onboarding checklist",
        )

        assert result["valid"] is True
        assert result["framing"]["who"] == "New engineering hires"
        assert result["framing"]["why"] == "So they can contribute without interruptions"
        assert result["framing"]["what"] == "A first-week onboarding checklist"

    def test_missing_who_rejects(self):
        """Missing WHO from prior step is rejected."""
        result = validate_initiative_hypothesis(
            who="",
            why="So they can contribute",
            what="A checklist",
        )

        assert result["valid"] is False
        assert result["error_type"] == "missing_prior_step"
        assert "who" in result["error_details"]

    def test_missing_why_rejects(self):
        """Missing WHY from prior step is rejected."""
        result = validate_initiative_hypothesis(
            who="New hires",
            why="",
            what="A checklist",
        )

        assert result["valid"] is False
        assert result["error_type"] == "missing_prior_step"
        assert "why" in result["error_details"]

    def test_missing_what_rejects(self):
        """Missing WHAT hypothesis is rejected."""
        result = validate_initiative_hypothesis(
            who="New hires",
            why="So they can contribute",
            what="",
        )

        assert result["valid"] is False
        assert result["error_type"] == "missing_what"

    def test_whitespace_trimmed(self):
        """Whitespace in inputs is trimmed."""
        result = validate_initiative_hypothesis(
            who="  New hires  ",
            why="  So they contribute  ",
            what="  A checklist  ",
        )

        assert result["valid"] is True
        assert result["framing"]["who"] == "New hires"
        assert result["framing"]["why"] == "So they contribute"
        assert result["framing"]["what"] == "A checklist"


class TestFrameHypothesisHandler:
    """Tests for frame_initiative_hypothesis handler."""

    @pytest.mark.asyncio
    async def test_valid_input_returns_proceed_action(self):
        """Valid input returns action='PROCEED_TO_CONSTRAINTS'."""
        arguments = {
            "who": "New engineering hires",
            "why": "So they can contribute without interruptions",
            "what": "A first-week checklist",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert result.structuredContent["confirmed"] is True
        assert result.structuredContent["assistant_guidance"]["action"] == "PROCEED_TO_CONSTRAINTS"

    @pytest.mark.asyncio
    async def test_low_confidence_returns_clarifying_action(self):
        """Low confidence returns action='ASK_CLARIFYING'."""
        arguments = {
            "who": "New hires",
            "why": "So they contribute",
            "what": "something",
            "confidence": "low",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "confidence_too_low"
        assert result.structuredContent["assistant_guidance"]["action"] == "ASK_CLARIFYING"

    @pytest.mark.asyncio
    async def test_missing_prior_step_returns_refuse_action(self):
        """Missing prior step returns action='REFUSE'."""
        arguments = {
            "who": "",
            "why": "",
            "what": "A checklist",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "missing_prior_step"
        assert result.structuredContent["assistant_guidance"]["action"] == "REFUSE"

    @pytest.mark.asyncio
    async def test_missing_what_returns_clarifying_action(self):
        """Missing WHAT returns action='ASK_CLARIFYING'."""
        arguments = {
            "who": "New hires",
            "why": "So they contribute",
            "what": "",
            "confidence": "high",
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "missing_what"
        assert result.structuredContent["assistant_guidance"]["action"] == "ASK_CLARIFYING"
```

---

## Downstream Impact

### `frame_initiative_constraints.py`

No changes needed — it already receives framing and doesn't care about the split.

### `identify_e2e_deliverables.py`

Needs to validate `initiative_framing` still contains `what`. The framing object passed forward should now come from `frame_initiative_hypothesis`, which includes all three fields.

Verify `validate_initiative_framing_complete` in `tool_logic.py` still checks for `what`:

```python
required_fields = [
    "who",
    "what",  # ← Still required
    "why",
    "constraint_type",
    "constraint_value",
]
```

This is correct — downstream tools receive the complete framing.

---

## Verification Checklist

### `frame_initiative_intent.py`
- [ ] INPUT_SCHEMA only has `who`, `why`, `confidence`
- [ ] `required` array is `["who", "why", "confidence"]`
- [ ] DESCRIPTION says "WHAT comes later via frame_initiative_hypothesis"
- [ ] DESCRIPTION does NOT ask about solutions
- [ ] GUIDANCE_CONFIRMED points to `frame_initiative_hypothesis`
- [ ] Pydantic model has no `what` field
- [ ] Handler output `framing_intent` contains only `who` + `why`

### `frame_initiative_hypothesis.py`
- [ ] File created at correct path
- [ ] INPUT_SCHEMA requires `who`, `why`, `what`, `confidence`
- [ ] DESCRIPTION frames WHAT as hypothesis
- [ ] GUIDANCE_CONFIRMED points to `frame_initiative_constraints`
- [ ] Handler validates prior step completed
- [ ] Handler output `framing_intent` contains `who` + `why` + `what`

### `tool_logic.py`
- [ ] `validate_initiative_intent` signature is `(who, why)`
- [ ] `validate_initiative_hypothesis` function added
- [ ] `validate_initiative_hypothesis` checks prior step fields

### `tools/__init__.py`
- [ ] `frame_initiative_hypothesis` imported

### Tests
- [ ] `test_frame_initiative_intent.py` updated (no `what` tests)
- [ ] `test_frame_initiative_hypothesis.py` created
- [ ] All tests pass

---

## Risk Assessment

**Medium risk.** This changes the Step 1 flow:

Before: 1 tool call
After: 2 tool calls

**Mitigation:**
- Each tool has clear guidance pointing to next step
- Error messages explain what's missing
- Flow is linear, not branching

**Potential issue:** LLM might try to call old combined tool or skip hypothesis step. DESCRIPTION and guidance should prevent this.

---

**Document Status:** Ready for Claude Code execution
