# SHARPEN V1 — INCREMENT 3.10: Provenance-Based Validation for Frame Initiative Hypothesis

## Claude Code Briefing

---

## Objective

Replace unenforceable `confidence` field with explicit provenance evidence that prevents LLM prefilling WHAT. Same pattern as increment 3.9.

**Current state:** `confidence: "high"` — abstract, easy to rationalize

**New state:** Verbatim quote + provenance booleans — LLM must fabricate specific text to cheat

---

## Design Rationale

### Problem

The LLM prefills WHAT (the hypothesized solution) for the user and claims `confidence: "high"`. This is the same failure mode as `frame_initiative_intent`.

### Solution

Replace `confidence` with provenance evidence:

| Field | Purpose |
|-------|---------|
| `user_what_verbatim` | User's exact words describing their hypothesized solution — must be non-empty |
| `what_stated_by_user` | Boolean: did user state WHAT? |
| `user_confirmed_hypothesis` | Boolean: did user explicitly confirm? |

**Validation:** Reject unless ALL conditions pass.

### Why This Works

Same reasoning as 3.9:
- Verbatim quote required (non-empty) — LLM must fabricate specific text to cheat
- Two explicit booleans — LLM must lie consistently across both
- Empty verbatim — Tool rejects, WHAT must exist before calling

---

## Files to Modify

1. `mcp_server/sharpen/tools/frame_initiative_hypothesis.py`
2. `mcp_server/sharpen/tool_logic.py`
3. `tests/unit/mcp_sharpen/test_frame_initiative_hypothesis.py`

---

## Change 1: `frame_initiative_hypothesis.py` — Schema Update

### Replace INPUT_SCHEMA

```python
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
        "user_what_verbatim": {
            "type": "string",
            "description": "User's EXACT words describing their hypothesized solution. Copy-paste from their message. Must be non-empty — do not call this tool until user has stated a WHAT.",
        },
        "what_derived_from_verbatim": {
            "type": "string",
            "description": "The WHAT, optionally condensed for clarity but semantically equivalent to user_what_verbatim. Do not invent — derive from the verbatim.",
        },
        "what_stated_by_user": {
            "type": "boolean",
            "description": "True ONLY if user explicitly stated WHAT in their own words. False if you inferred, generalized, or suggested it.",
        },
        "user_confirmed_hypothesis": {
            "type": "boolean",
            "description": "True ONLY if you reflected the hypothesis back and user explicitly confirmed (e.g. 'yes', 'correct', 'that's right').",
        },
    },
    "required": [
        "who",
        "why",
        "user_what_verbatim",
        "what_derived_from_verbatim",
        "what_stated_by_user",
        "user_confirmed_hypothesis",
    ],
    "additionalProperties": False,
}
```

### Update Pydantic Model

```python
class FrameHypothesisRequest(BaseModel):
    """Expected input structure from ChatGPT."""
    who: Optional[str] = None
    why: Optional[str] = None
    user_what_verbatim: Optional[str] = None
    what_derived_from_verbatim: Optional[str] = None
    what_stated_by_user: Optional[bool] = None
    user_confirmed_hypothesis: Optional[bool] = None
```

---

## Change 2: `frame_initiative_hypothesis.py` — DESCRIPTION Update

```python
DESCRIPTION = """Records WHAT (the hypothesized solution) after problem is understood. Requires confirmed WHO + WHY from frame_initiative_intent.

SHARPEN MODE — BINDING RULES (not guidelines)
When user selects Sharpen, your default assistant behavior is SUSPENDED.

SUSPENDED BEHAVIORS:
- Suggesting solutions
- Improving or "fixing" user's hypothesis
- Offering alternatives unprompted
- Jumping to planning or breakdown
- Claiming user said something they didn't say

ACTIVE BEHAVIORS:
- Ask ONE question: "What do you think needs to exist to help with that?"
- Wait for answer
- Quote user's exact words back to them
- Reflect back as hypothesis
- Confirm with user
- Call tool only after provenance evidence is available and user confirms

WHAT AS HYPOTHESIS:
The user's WHAT is a hypothesis, not a commitment. Frame it that way:
- "You think [WHAT] might help [WHO] so that [WHY]."
- "This is your current hypothesis — we'll pressure-test it against constraints."

Do NOT evaluate whether it's a good solution. That comes later via constraints.

PROVENANCE EVIDENCE REQUIRED:
This tool requires proof that WHAT came from the user:
- user_what_verbatim: Copy-paste the user's exact words. Must be non-empty — do not call until WHAT is stated.
- what_stated_by_user: Did user say WHAT? If false, tool rejects.
- user_confirmed_hypothesis: Did user confirm? If false, tool rejects.

If you cannot honestly set ALL booleans to true AND provide a non-empty verbatim quote, do NOT call the tool. Ask the user first.

EXAMPLE CONVERSATION:
  [After frame_initiative_intent confirmed: who="New engineering hires", why="So they can find answers without interrupting others"]
  You: "What do you think needs to exist to help with that?"
  User: "A checklist they can follow in their first week"
       ↑ THIS IS user_what_verbatim — store exactly
  You: "Your hypothesis: A first-week checklist for new engineering hires so they can find answers without interrupting others. Correct?"
  User: "Yes"
       ↑ NOW user_confirmed_hypothesis = true
  → Call tool with:
    who="New engineering hires"
    why="So they can find answers without interrupting others"
    user_what_verbatim="A checklist they can follow in their first week"
    what_derived_from_verbatim="A first-week checklist"
    what_stated_by_user=true
    user_confirmed_hypothesis=true
"""
```

---

## Change 3: `frame_initiative_hypothesis.py` — Guidance Constants

Replace confidence-based guidance with provenance-based guidance:

```python
GUIDANCE_PROVENANCE_FAILED = (
    "SHARPEN MODE STILL BINDING. "
    "Provenance check failed. You must have evidence from the user before calling this tool.\n"
    "- If WHAT not stated: Ask 'What do you think needs to exist to help with that?'\n"
    "- If not confirmed: Reflect the hypothesis back and ask 'Correct?'\n"
    "Ask ONE question. Then stop and wait. Do not suggest solutions."
)

GUIDANCE_EMPTY_VERBATIM = (
    "SHARPEN MODE STILL BINDING. "
    "user_what_verbatim is empty. Do not call this tool until user has stated a WHAT. "
    "Ask: 'What do you think needs to exist to help with that?' "
    "Then store their exact answer in user_what_verbatim."
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
```

---

## Change 4: `frame_initiative_hypothesis.py` — Handler Update

Replace confidence check with provenance validation:

```python
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

    # Extract provenance flags (default to False if None)
    what_stated = validated_request.what_stated_by_user or False
    user_confirmed = validated_request.user_confirmed_hypothesis or False
    what_verbatim = (validated_request.user_what_verbatim or "").strip()

    # Provenance validation
    provenance_result = validate_hypothesis_provenance(
        what_stated_by_user=what_stated,
        user_confirmed_hypothesis=user_confirmed,
        user_what_verbatim=what_verbatim,
    )

    if not provenance_result["valid"]:
        error_type = provenance_result["error_type"]

        if error_type == "empty_verbatim":
            guidance = GUIDANCE_EMPTY_VERBATIM
        else:
            guidance = GUIDANCE_PROVENANCE_FAILED

        logger.info("frame_initiative_hypothesis.provenance_rejected",
                    error_type=error_type,
                    failed_checks=provenance_result.get("failed_checks", []))

        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=provenance_result["error_details"],
            )],
            structuredContent={
                "error": error_type,
                "failed_checks": provenance_result.get("failed_checks", []),
                "assistant_guidance": {
                    "action": "ASK_CLARIFYING",
                    "instruction": guidance,
                },
            },
            isError=True,
        )

    # Structural validation (maps input field to internal 'what')
    result = validate_initiative_hypothesis(
        who=validated_request.who,
        why=validated_request.why,
        what=validated_request.what_derived_from_verbatim,
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

    # Valid — return confirmed framing with provenance evidence
    framing = result["framing"]

    logger.info("frame_initiative_hypothesis.complete",
                who=framing["who"], what=framing["what"],
                has_verbatim=bool(what_verbatim))

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Hypothesis confirmed: {framing['who']} needs {framing['what']} so that {framing['why']}",
        )],
        structuredContent={
            "framing_intent": framing,
            "provenance": {
                "user_what_verbatim": what_verbatim,
                "what_stated_by_user": True,
                "user_confirmed_hypothesis": True,
            },
            "confirmed": True,
            "assistant_guidance": {
                "action": "PROCEED_TO_CONSTRAINTS",
                "instruction": GUIDANCE_CONFIRMED,
            },
        },
    )
```

---

## Change 5: `tool_logic.py` — Add Provenance Validation

Add new function after `validate_intent_provenance`:

```python
def validate_hypothesis_provenance(
    what_stated_by_user: bool,
    user_confirmed_hypothesis: bool,
    user_what_verbatim: str,
) -> dict[str, Any]:
    """
    Validate provenance evidence for frame_initiative_hypothesis.

    Both booleans must be True AND verbatim must be non-empty.

    Applies defensive normalization to user_what_verbatim (strips whitespace).

    Args:
        what_stated_by_user: Did user explicitly state WHAT?
        user_confirmed_hypothesis: Did user explicitly confirm the hypothesis?
        user_what_verbatim: User's exact words describing the hypothesis

    Returns:
        {"valid": bool, "error_type": str | None, "error_details": str | None, "failed_checks": list}
    """
    # Defensive normalization
    user_what_verbatim = (user_what_verbatim or "").strip()

    failed_checks = []

    # Verbatim is required — WHAT must exist before calling this tool
    if not user_what_verbatim:
        return {
            "valid": False,
            "error_type": "empty_verbatim",
            "error_details": "user_what_verbatim is empty. Do not call this tool until user has stated a WHAT.",
            "failed_checks": ["user_what_verbatim"],
        }

    if not what_stated_by_user:
        failed_checks.append("what_stated_by_user")
    if not user_confirmed_hypothesis:
        failed_checks.append("user_confirmed_hypothesis")

    if failed_checks:
        return {
            "valid": False,
            "error_type": "provenance_failed",
            "error_details": f"Provenance checks failed: {', '.join(failed_checks)}. Get evidence from user first.",
            "failed_checks": failed_checks,
        }

    return {
        "valid": True,
        "error_type": None,
        "error_details": None,
        "failed_checks": [],
    }
```

---

## Change 6: `frame_initiative_hypothesis.py` — Update Imports

```python
from ..tool_logic import validate_initiative_hypothesis, validate_hypothesis_provenance
```

---

## Unit Tests

### Update `test_frame_initiative_hypothesis.py`

Add new test class for provenance validation:

```python
# ============================================================================
# Provenance Validation Tests (tool_logic.py)
# ============================================================================


class TestValidateHypothesisProvenance:
    """Tests for validate_hypothesis_provenance function."""

    def test_all_true_with_verbatim_valid(self):
        """All provenance flags True with verbatim is valid."""
        from mcp_server.sharpen.tool_logic import validate_hypothesis_provenance

        result = validate_hypothesis_provenance(
            what_stated_by_user=True,
            user_confirmed_hypothesis=True,
            user_what_verbatim="A checklist they can follow",
        )

        assert result["valid"] is True
        assert result["failed_checks"] == []

    def test_empty_verbatim_rejects(self):
        """Empty verbatim is rejected — WHAT must exist."""
        from mcp_server.sharpen.tool_logic import validate_hypothesis_provenance

        result = validate_hypothesis_provenance(
            what_stated_by_user=True,
            user_confirmed_hypothesis=True,
            user_what_verbatim="",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_verbatim"

    def test_what_not_stated_rejects(self):
        """what_stated_by_user=False is rejected."""
        from mcp_server.sharpen.tool_logic import validate_hypothesis_provenance

        result = validate_hypothesis_provenance(
            what_stated_by_user=False,
            user_confirmed_hypothesis=True,
            user_what_verbatim="Some what",
        )

        assert result["valid"] is False
        assert "what_stated_by_user" in result["failed_checks"]

    def test_not_confirmed_rejects(self):
        """user_confirmed_hypothesis=False is rejected."""
        from mcp_server.sharpen.tool_logic import validate_hypothesis_provenance

        result = validate_hypothesis_provenance(
            what_stated_by_user=True,
            user_confirmed_hypothesis=False,
            user_what_verbatim="Some what",
        )

        assert result["valid"] is False
        assert "user_confirmed_hypothesis" in result["failed_checks"]

    def test_multiple_failures_lists_all(self):
        """Multiple failed checks are all listed."""
        from mcp_server.sharpen.tool_logic import validate_hypothesis_provenance

        result = validate_hypothesis_provenance(
            what_stated_by_user=False,
            user_confirmed_hypothesis=False,
            user_what_verbatim="Some what",
        )

        assert result["valid"] is False
        assert len(result["failed_checks"]) == 2

    def test_whitespace_only_verbatim_rejects(self):
        """Whitespace-only verbatim is treated as empty."""
        from mcp_server.sharpen.tool_logic import validate_hypothesis_provenance

        result = validate_hypothesis_provenance(
            what_stated_by_user=True,
            user_confirmed_hypothesis=True,
            user_what_verbatim="   ",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_verbatim"


class TestFrameHypothesisHandlerProvenance:
    """Tests for handler provenance validation."""

    @pytest.mark.asyncio
    async def test_all_provenance_true_succeeds(self):
        """All provenance flags True with verbatim succeeds."""
        arguments = {
            "who": "New engineering hires",
            "why": "So they can find answers without interrupting others",
            "user_what_verbatim": "A checklist they can follow in their first week",
            "what_derived_from_verbatim": "A first-week checklist",
            "what_stated_by_user": True,
            "user_confirmed_hypothesis": True,
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert result.structuredContent["confirmed"] is True
        assert "provenance" in result.structuredContent

    @pytest.mark.asyncio
    async def test_provenance_false_rejects(self):
        """Any provenance flag False is rejected."""
        arguments = {
            "who": "New engineering hires",
            "why": "So they can contribute",
            "user_what_verbatim": "Some solution",
            "what_derived_from_verbatim": "A solution",
            "what_stated_by_user": True,
            "user_confirmed_hypothesis": False,
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "provenance_failed"

    @pytest.mark.asyncio
    async def test_empty_verbatim_rejects(self):
        """Empty verbatim is rejected."""
        arguments = {
            "who": "New engineering hires",
            "why": "So they can contribute",
            "user_what_verbatim": "",
            "what_derived_from_verbatim": "A solution",
            "what_stated_by_user": True,
            "user_confirmed_hypothesis": True,
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_verbatim"

    @pytest.mark.asyncio
    async def test_provenance_failure_returns_guidance(self):
        """Provenance failure returns actionable guidance."""
        arguments = {
            "who": "Someone",
            "why": "For reasons",
            "user_what_verbatim": "Something",
            "what_derived_from_verbatim": "A thing",
            "what_stated_by_user": False,
            "user_confirmed_hypothesis": False,
        }

        result = await handle(arguments)

        assert "assistant_guidance" in result.structuredContent
        instruction = result.structuredContent["assistant_guidance"]["instruction"]
        assert "SHARPEN MODE STILL BINDING" in instruction

    @pytest.mark.asyncio
    async def test_empty_verbatim_returns_specific_guidance(self):
        """Empty verbatim returns specific guidance about getting WHAT."""
        arguments = {
            "who": "Team",
            "why": "Some reason",
            "user_what_verbatim": "",
            "what_derived_from_verbatim": "Something",
            "what_stated_by_user": True,
            "user_confirmed_hypothesis": True,
        }

        result = await handle(arguments)

        instruction = result.structuredContent["assistant_guidance"]["instruction"]
        assert "user_what_verbatim is empty" in instruction

    @pytest.mark.asyncio
    async def test_failed_checks_listed_in_response(self):
        """Failed provenance checks are listed in response."""
        arguments = {
            "who": "Team",
            "why": "Reason",
            "user_what_verbatim": "What",
            "what_derived_from_verbatim": "Thing",
            "what_stated_by_user": False,
            "user_confirmed_hypothesis": True,
        }

        result = await handle(arguments)

        assert "failed_checks" in result.structuredContent
        assert "what_stated_by_user" in result.structuredContent["failed_checks"]

    @pytest.mark.asyncio
    async def test_valid_input_includes_provenance(self):
        """Valid input includes provenance object in response."""
        arguments = {
            "who": "New hires",
            "why": "So they can navigate independently",
            "user_what_verbatim": "An onboarding guide",
            "what_derived_from_verbatim": "An onboarding guide",
            "what_stated_by_user": True,
            "user_confirmed_hypothesis": True,
        }

        result = await handle(arguments)

        assert "provenance" in result.structuredContent
        provenance = result.structuredContent["provenance"]
        assert provenance["user_what_verbatim"] == "An onboarding guide"
        assert provenance["what_stated_by_user"] is True
        assert provenance["user_confirmed_hypothesis"] is True
```

Update existing handler tests to include provenance flags:

```python
@pytest.mark.asyncio
async def test_valid_input_returns_proceed_action(self):
    """Valid input returns action='PROCEED_TO_CONSTRAINTS'."""
    arguments = {
        "who": "New engineering hires",
        "why": "So they can contribute without interruptions",
        "user_what_verbatim": "A first-week checklist",
        "what_derived_from_verbatim": "A first-week checklist",
        "what_stated_by_user": True,
        "user_confirmed_hypothesis": True,
    }

    result = await handle(arguments)

    assert result.isError is not True
    assert result.structuredContent["confirmed"] is True
    assert result.structuredContent["assistant_guidance"]["action"] == "PROCEED_TO_CONSTRAINTS"

@pytest.mark.asyncio
async def test_missing_prior_step_returns_refuse_action(self):
    """Missing prior step returns action='REFUSE'."""
    arguments = {
        "who": "",
        "why": "",
        "user_what_verbatim": "A checklist",
        "what_derived_from_verbatim": "A checklist",
        "what_stated_by_user": True,
        "user_confirmed_hypothesis": True,
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
        "user_what_verbatim": "Something",
        "what_derived_from_verbatim": "",
        "what_stated_by_user": True,
        "user_confirmed_hypothesis": True,
    }

    result = await handle(arguments)

    assert result.isError is True
    assert result.structuredContent["error"] == "missing_what"
    assert result.structuredContent["assistant_guidance"]["action"] == "ASK_CLARIFYING"

@pytest.mark.asyncio
async def test_valid_input_includes_framing_intent(self):
    """Valid input includes framing_intent with who, why, what."""
    arguments = {
        "who": "New engineering hires",
        "why": "So they can find answers without interrupting",
        "user_what_verbatim": "A first-week checklist",
        "what_derived_from_verbatim": "A first-week checklist",
        "what_stated_by_user": True,
        "user_confirmed_hypothesis": True,
    }

    result = await handle(arguments)

    assert "framing_intent" in result.structuredContent
    assert result.structuredContent["framing_intent"]["who"] == "New engineering hires"
    assert result.structuredContent["framing_intent"]["why"] == "So they can find answers without interrupting"
    assert result.structuredContent["framing_intent"]["what"] == "A first-week checklist"

@pytest.mark.asyncio
async def test_text_content_for_valid_input(self):
    """Valid input returns human-readable text content."""
    arguments = {
        "who": "New engineering hires",
        "why": "So they can contribute",
        "user_what_verbatim": "A checklist",
        "what_derived_from_verbatim": "A checklist",
        "what_stated_by_user": True,
        "user_confirmed_hypothesis": True,
    }

    result = await handle(arguments)

    assert len(result.content) == 1
    assert "Hypothesis confirmed" in result.content[0].text
    assert "New engineering hires" in result.content[0].text
    assert "A checklist" in result.content[0].text
```

---

## Verification Checklist

### Schema (`frame_initiative_hypothesis.py`)
- [ ] INPUT_SCHEMA has `user_what_verbatim` field (non-empty required)
- [ ] INPUT_SCHEMA has `what_derived_from_verbatim` field (derived from verbatim)
- [ ] INPUT_SCHEMA has TWO boolean provenance fields
- [ ] INPUT_SCHEMA does NOT have `confidence` field
- [ ] INPUT_SCHEMA does NOT have plain `what` field
- [ ] `required` array includes all new fields

### Pydantic Model (`frame_initiative_hypothesis.py`)
- [ ] `FrameHypothesisRequest` has `user_what_verbatim: Optional[str]`
- [ ] `FrameHypothesisRequest` has `what_derived_from_verbatim: Optional[str]`
- [ ] `FrameHypothesisRequest` has TWO `Optional[bool]` provenance fields
- [ ] `FrameHypothesisRequest` does NOT have `confidence` field
- [ ] `FrameHypothesisRequest` does NOT have plain `what` field

### DESCRIPTION (`frame_initiative_hypothesis.py`)
- [ ] Explains provenance evidence requirement
- [ ] Shows example with verbatim quote
- [ ] Does NOT mention `confidence`

### Logic (`tool_logic.py`)
- [ ] `validate_hypothesis_provenance` function added
- [ ] Checks TWO booleans
- [ ] Defensive normalization applied
- [ ] Returns `failed_checks` list

### Handler (`frame_initiative_hypothesis.py`)
- [ ] Imports `validate_hypothesis_provenance`
- [ ] Calls `validate_hypothesis_provenance` before structural validation
- [ ] Passes `what_derived_from_verbatim` to `validate_initiative_hypothesis` as `what`
- [ ] Output `framing_intent.what` remains unchanged for downstream compatibility
- [ ] Returns `provenance` object in success response
- [ ] Does NOT check `confidence`

### Tests
- [ ] `TestValidateHypothesisProvenance` class added
- [ ] `TestFrameHypothesisHandlerProvenance` class added
- [ ] Existing tests updated with provenance flags
- [ ] All tests pass

---

## Risk Assessment

**Low risk.** Same proven pattern as 3.9.

**Breaking changes:**
- `confidence` field removed
- `what` field renamed to `what_derived_from_verbatim` (enforces derivation relationship)
- Two new required boolean fields
- One new required string field (`user_what_verbatim`)
- Output `framing_intent.what` unchanged for downstream compatibility

**Mitigation:**
- Clear error messages explain what's missing
- DESCRIPTION shows exact usage
- Provenance failures return actionable guidance

---

**Document Status:** Ready for Claude Code execution
