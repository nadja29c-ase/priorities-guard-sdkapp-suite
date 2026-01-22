# SHARPEN V1 — INCREMENT 3.9: Provenance-Based Validation for Frame Initiative Intent

## Claude Code Briefing

---

## Objective

Replace unenforceable `confidence` field with explicit provenance evidence that prevents LLM prefilling. The LLM must provide auditable proof that WHO and WHY came from the user.

**Current state:** `confidence: "high"` — abstract, easy to rationalize

**New state:** Verbatim quote + provenance booleans — LLM must fabricate specific text to cheat

---

## Design Rationale

### Problem

The LLM prefills WHY for the user and claims `confidence: "high"`. This happens because:
- `confidence` collapses three facts (source, transformation, confirmation) into one soft label
- The LLM can self-justify "high" without evidence
- No structural audit trail exists

### Solution

Replace `confidence` with provenance evidence:

| Field | Purpose |
|-------|---------|
| `user_pain_verbatim` | User's exact words describing the problem — must be non-empty |
| `who_stated_by_user` | Boolean: did user state WHO? |
| `why_reframed_from_pain` | Boolean: is WHY derived from the verbatim pain? |
| `user_confirmed_framing` | Boolean: did user explicitly confirm? |

`pain_stated_by_user` is intentionally omitted — it's derived from `bool(user_pain_verbatim.strip())`.

**Validation:** Reject unless ALL conditions pass.

### Why This Works

| Old Approach | Failure Mode |
|--------------|--------------|
| `confidence="high"` | LLM self-rationalizes |

| New Approach | Enforcement |
|--------------|-------------|
| Verbatim quote required (non-empty) | LLM must fabricate specific text to cheat |
| Three explicit booleans | LLM must lie consistently across all three |
| Empty verbatim | Tool rejects — pain must exist before calling |

---

## Files to Modify

1. `mcp_server/sharpen/tools/frame_initiative_intent.py`
2. `mcp_server/sharpen/tool_logic.py`
3. `tests/unit/mcp_sharpen/test_frame_initiative_intent.py`

---

## Change 1: `frame_initiative_intent.py` — Schema Update

### Replace INPUT_SCHEMA

```python
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "who": {
            "type": "string",
            "description": "ONE primary beneficiary. Who benefits first and foremost? Not multiple audiences. ACCORDING TO THE USER.",
        },
        "user_pain_verbatim": {
            "type": "string",
            "description": "User's EXACT words describing their pain, frustration, or problem. Copy-paste from their message. Must be non-empty — do not call this tool until user has stated a pain.",
        },
        "why": {
            "type": "string",
            "description": "YOUR reframe of user_pain_verbatim into an outcome. Must be traceable to the pain quote. Do not invent — derive from the verbatim pain.",
        },
        "who_stated_by_user": {
            "type": "boolean",
            "description": "True ONLY if user explicitly stated WHO in their own words. False if you inferred, generalized, or suggested it.",
        },
        "why_reframed_from_pain": {
            "type": "boolean",
            "description": "True ONLY if WHY was derived by reframing user_pain_verbatim. False if WHY was generated without a prior pain statement.",
        },
        "user_confirmed_framing": {
            "type": "boolean",
            "description": "True ONLY if you reflected WHO + WHY back and user explicitly confirmed (e.g. 'yes', 'correct', 'that's right').",
        },
    },
    "required": [
        "who",
        "user_pain_verbatim",
        "why",
        "who_stated_by_user",
        "why_reframed_from_pain",
        "user_confirmed_framing",
    ],
    "additionalProperties": False,
}
```

### Update Pydantic Model

```python
class FrameIntentRequest(BaseModel):
    """Expected input structure from ChatGPT."""
    who: Optional[str] = None
    user_pain_verbatim: Optional[str] = None
    why: Optional[str] = None
    who_stated_by_user: Optional[bool] = None
    why_reframed_from_pain: Optional[bool] = None
    user_confirmed_framing: Optional[bool] = None
```

---

## Change 2: `frame_initiative_intent.py` — DESCRIPTION Update

```python
DESCRIPTION = """Records WHO benefits and WHY (outcome) for given initiative. WHAT comes later via frame_initiative_hypothesis.

SHARPEN MODE — BINDING RULES (not guidelines)
When user selects Sharpen, your default assistant behavior is SUSPENDED.

SUSPENDED BEHAVIORS:
- Asking about solutions/WHAT before understanding the problem
- Batching multiple questions
- Inferring or prefilling WHO/WHY on behalf of the user
- Planning or structuring for the user
- Claiming user said something they didn't say

ACTIVE BEHAVIORS:
- Ask ONE question at a time
- Wait for answer
- Quote user's exact words back to them
- Reframe pain → outcome
- Confirm with user
- Call tool only after explicit user confirmation

ELICITATION ORDER:
1. WHO: "Who specifically is supposed to benefit from this?"
   → Wait for answer. Store exact words.
2. PAIN: "What's currently hard or frustrating for them?"
   → Wait for answer. Store EXACT quote in user_pain_verbatim.
3. (If pain is abstract) OBSERVABLE: "What would you see happening differently if this worked?"
   → Wait for answer. Update user_pain_verbatim with more concrete quote.
4. REFRAME: Convert pain → outcome-phrased WHY
   → "So they can [outcome derived from pain]"
5. CONFIRM: "To confirm: [WHO] needs something so that [WHY]. Correct?"
   → Wait for explicit "yes" / "correct" / confirmation.

CRITICAL: Do NOT ask about WHAT/solution yet. Problem understanding comes first.

PROVENANCE EVIDENCE REQUIRED:
This tool requires proof that data came from the user:
- user_pain_verbatim: Copy-paste the user's exact words. Must be non-empty — do not call until pain is stated.
- who_stated_by_user: Did user say WHO? If false, tool rejects.
- why_reframed_from_pain: Is WHY derived from the verbatim? If false, tool rejects.
- user_confirmed_framing: Did user confirm? If false, tool rejects.

If you cannot honestly set ALL booleans to true AND provide a non-empty verbatim quote, do NOT call the tool. Ask the missing question first.

EXAMPLE CONVERSATION:
  User: "I want to improve our onboarding"
  You: "Who specifically is supposed to benefit from this?"
  User: "New engineering hires"
  You: "What's currently hard or frustrating for new engineering hires?"
  User: "They keep asking the same basic questions and feel lost"
       ↑ THIS IS user_pain_verbatim — store exactly
  You: "To confirm: New engineering hires need something so they can find answers without constantly interrupting others. Correct?"
       ↑ WHY reframed from "asking same questions" → "find answers without interrupting"
  User: "Yes"
       ↑ NOW user_confirmed_framing = true
  → Call tool with:
    who="New engineering hires"
    user_pain_verbatim="They keep asking the same basic questions and feel lost"
    why="So they can find answers without constantly interrupting others"
    who_stated_by_user=true
    why_reframed_from_pain=true
    user_confirmed_framing=true
"""
```

---

## Change 3: `frame_initiative_intent.py` — Guidance Constants

Replace confidence-based guidance with provenance-based guidance:

```python
GUIDANCE_PROVENANCE_FAILED = (
    "SHARPEN MODE STILL BINDING. "
    "Provenance check failed. You must have evidence from the user before calling this tool.\n"
    "- If WHO not stated: Ask 'Who specifically is supposed to benefit from this?'\n"
    "- If pain not stated: Ask 'What's currently hard or frustrating for them?'\n"
    "- If WHY not derived from pain: Reframe the user's pain into an outcome first.\n"
    "- If not confirmed: Reflect WHO + WHY back and ask 'Correct?'\n"
    "Ask ONE question. Then stop and wait."
)

GUIDANCE_EMPTY_VERBATIM = (
    "SHARPEN MODE STILL BINDING. "
    "user_pain_verbatim is empty. Do not call this tool until user has stated a pain. "
    "Ask: 'What's currently hard or frustrating for [WHO]?' "
    "Then store their exact answer in user_pain_verbatim."
)

GUIDANCE_MISSING_FIELDS = (
    "SHARPEN MODE STILL BINDING. "
    "Ask ONE question about the missing field:\n"
    "- Missing WHO: 'Who specifically is supposed to benefit from this?'\n"
    "- Missing WHY: First get the pain, then reframe to outcome.\n"
    "Then stop and wait. Do not ask about solutions yet."
)

GUIDANCE_MULTIPLE_STAKEHOLDERS = (
    "SHARPEN MODE STILL BINDING. "
    "Multiple stakeholders detected. Ask: 'Who benefits first and foremost?' "
    "Then stop and wait. Frame confirmation as '[WHO] primarily benefits from this.'"
)

GUIDANCE_CONFIRMED = (
    "SHARPEN MODE STILL BINDING. "
    "Problem understanding confirmed with evidence. Now ask about the hypothesized solution:\n"
    "'What do you think needs to exist to help with that?'\n"
    "Then stop and wait. Do not suggest solutions.\n\n"
    "When user answers → call frame_initiative_hypothesis with the WHAT."
)
```

---

## Change 4: `frame_initiative_intent.py` — Handler Update

Replace confidence check with provenance validation:

```python
async def handle(arguments: dict) -> mcp_types.CallToolResult:
    """Handle frame_initiative_intent tool call."""
    logger.debug("frame_initiative_intent.handle.start",
                argument_keys=list(arguments.keys()))

    # Pydantic validation
    try:
        validated_request = FrameIntentRequest.model_validate(arguments)
    except ValidationError as e:
        logger.warning("frame_initiative_intent.validation_failed", error=str(e.errors()))
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text="Invalid input format.")],
            structuredContent={"error": "validation_error", "details": e.errors()},
            isError=True,
        )

    # Extract provenance flags (default to False if None)
    who_stated = validated_request.who_stated_by_user or False
    why_reframed = validated_request.why_reframed_from_pain or False
    user_confirmed = validated_request.user_confirmed_framing or False
    pain_verbatim = (validated_request.user_pain_verbatim or "").strip()

    # Provenance validation
    provenance_result = validate_intent_provenance(
        who_stated_by_user=who_stated,
        why_reframed_from_pain=why_reframed,
        user_confirmed_framing=user_confirmed,
        user_pain_verbatim=pain_verbatim,
    )

    if not provenance_result["valid"]:
        error_type = provenance_result["error_type"]
        
        if error_type == "empty_verbatim":
            guidance = GUIDANCE_EMPTY_VERBATIM
        else:
            guidance = GUIDANCE_PROVENANCE_FAILED
        
        logger.info("frame_initiative_intent.provenance_rejected",
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

    # Structural validation (who, why content)
    result = validate_initiative_intent(
        who=validated_request.who,
        why=validated_request.why,
    )

    # If structurally invalid, return error
    if not result["valid"]:
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

        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=f"Missing required fields: {', '.join(result['missing'])}",
            )],
            structuredContent={
                "error": "missing_fields",
                "missing": result["missing"],
                "assistant_guidance": {
                    "action": "ASK_CLARIFYING",
                    "instruction": GUIDANCE_MISSING_FIELDS,
                },
            },
            isError=True,
        )

    # Valid — return confirmed framing with provenance evidence
    intent = result["framing_intent"]

    logger.info("frame_initiative_intent.complete",
               who=intent["who"], why=intent["why"],
               has_verbatim=bool(pain_verbatim))

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Problem framing confirmed: {intent['who']} needs something so that {intent['why']}",
        )],
        structuredContent={
            "framing_intent": intent,
            "provenance": {
                "user_pain_verbatim": pain_verbatim,
                "who_stated_by_user": True,
                "why_reframed_from_pain": True,
                "user_confirmed_framing": True,
            },
            "confirmed": True,
            "assistant_guidance": {
                "action": "PROCEED_TO_HYPOTHESIS",
                "instruction": GUIDANCE_CONFIRMED,
            },
        },
    )
```

---

## Change 5: `tool_logic.py` — Add Provenance Validation

Add new function after `validate_initiative_intent`:

```python
def validate_intent_provenance(
    who_stated_by_user: bool,
    why_reframed_from_pain: bool,
    user_confirmed_framing: bool,
    user_pain_verbatim: str,
) -> dict[str, Any]:
    """
    Validate provenance evidence for frame_initiative_intent.

    All three booleans must be True AND verbatim must be non-empty.
    pain_stated is derived from verbatim presence (not a separate field).

    Applies defensive normalization to user_pain_verbatim (strips whitespace).

    Args:
        who_stated_by_user: Did user explicitly state WHO?
        why_reframed_from_pain: Is WHY derived from the stated pain?
        user_confirmed_framing: Did user explicitly confirm the framing?
        user_pain_verbatim: User's exact words describing the pain

    Returns:
        {"valid": bool, "error_type": str | None, "error_details": str | None, "failed_checks": list}
    """
    # Defensive normalization — whitespace-only is empty
    user_pain_verbatim = (user_pain_verbatim or "").strip()

    failed_checks = []

    # Verbatim is required — pain must exist before calling this tool
    if not user_pain_verbatim:
        return {
            "valid": False,
            "error_type": "empty_verbatim",
            "error_details": "user_pain_verbatim is empty. Do not call this tool until user has stated a pain.",
            "failed_checks": ["user_pain_verbatim"],
        }

    if not who_stated_by_user:
        failed_checks.append("who_stated_by_user")
    if not why_reframed_from_pain:
        failed_checks.append("why_reframed_from_pain")
    if not user_confirmed_framing:
        failed_checks.append("user_confirmed_framing")

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

## Unit Tests

### Update `test_frame_initiative_intent.py`

Add new test class for provenance validation:

```python
# ============================================================================
# Provenance Validation Tests (tool_logic.py)
# ============================================================================


class TestValidateIntentProvenance:
    """Tests for validate_intent_provenance function."""

    def test_all_true_with_verbatim_valid(self):
        """All provenance flags True with verbatim is valid."""
        from mcp_server.sharpen.tool_logic import validate_intent_provenance
        
        result = validate_intent_provenance(
            who_stated_by_user=True,
            why_reframed_from_pain=True,
            user_confirmed_framing=True,
            user_pain_verbatim="They keep asking the same questions",
        )
        
        assert result["valid"] is True
        assert result["failed_checks"] == []

    def test_empty_verbatim_rejects(self):
        """Empty verbatim is rejected — pain must exist."""
        from mcp_server.sharpen.tool_logic import validate_intent_provenance
        
        result = validate_intent_provenance(
            who_stated_by_user=True,
            why_reframed_from_pain=True,
            user_confirmed_framing=True,
            user_pain_verbatim="",
        )
        
        assert result["valid"] is False
        assert result["error_type"] == "empty_verbatim"

    def test_who_not_stated_rejects(self):
        """who_stated_by_user=False is rejected."""
        from mcp_server.sharpen.tool_logic import validate_intent_provenance
        
        result = validate_intent_provenance(
            who_stated_by_user=False,
            why_reframed_from_pain=True,
            user_confirmed_framing=True,
            user_pain_verbatim="Some pain",
        )
        
        assert result["valid"] is False
        assert "who_stated_by_user" in result["failed_checks"]

    def test_why_not_reframed_rejects(self):
        """why_reframed_from_pain=False is rejected."""
        from mcp_server.sharpen.tool_logic import validate_intent_provenance
        
        result = validate_intent_provenance(
            who_stated_by_user=True,
            why_reframed_from_pain=False,
            user_confirmed_framing=True,
            user_pain_verbatim="Some pain",
        )
        
        assert result["valid"] is False
        assert "why_reframed_from_pain" in result["failed_checks"]

    def test_not_confirmed_rejects(self):
        """user_confirmed_framing=False is rejected."""
        from mcp_server.sharpen.tool_logic import validate_intent_provenance
        
        result = validate_intent_provenance(
            who_stated_by_user=True,
            why_reframed_from_pain=True,
            user_confirmed_framing=False,
            user_pain_verbatim="Some pain",
        )
        
        assert result["valid"] is False
        assert "user_confirmed_framing" in result["failed_checks"]

    def test_multiple_failures_lists_all(self):
        """Multiple failed checks are all listed."""
        from mcp_server.sharpen.tool_logic import validate_intent_provenance
        
        result = validate_intent_provenance(
            who_stated_by_user=False,
            why_reframed_from_pain=False,
            user_confirmed_framing=False,
            user_pain_verbatim="Some pain",  # verbatim present, so we get boolean failures
        )
        
        assert result["valid"] is False
        assert len(result["failed_checks"]) == 3

    def test_whitespace_only_verbatim_rejects(self):
        """Whitespace-only verbatim is treated as empty."""
        from mcp_server.sharpen.tool_logic import validate_intent_provenance
        
        result = validate_intent_provenance(
            who_stated_by_user=True,
            why_reframed_from_pain=True,
            user_confirmed_framing=True,
            user_pain_verbatim="   ",  # Whitespace only
        )
        
        assert result["valid"] is False
        assert result["error_type"] == "empty_verbatim"


class TestFrameIntentHandlerProvenance:
    """Tests for handler provenance validation."""

    @pytest.mark.asyncio
    async def test_all_provenance_true_succeeds(self):
        """All provenance flags True with verbatim succeeds."""
        arguments = {
            "who": "New engineering hires",
            "user_pain_verbatim": "They keep asking the same questions",
            "why": "So they can find answers without interrupting others",
            "who_stated_by_user": True,
            "why_reframed_from_pain": True,
            "user_confirmed_framing": True,
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
            "user_pain_verbatim": "Some pain",
            "why": "So they can do something",
            "who_stated_by_user": True,
            "why_reframed_from_pain": True,
            "user_confirmed_framing": False,  # Not confirmed!
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "provenance_failed"

    @pytest.mark.asyncio
    async def test_empty_verbatim_rejects(self):
        """Empty verbatim is rejected."""
        arguments = {
            "who": "New engineering hires",
            "user_pain_verbatim": "",  # Empty!
            "why": "So they can do something",
            "who_stated_by_user": True,
            "why_reframed_from_pain": True,
            "user_confirmed_framing": True,
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_verbatim"

    @pytest.mark.asyncio
    async def test_provenance_failure_returns_guidance(self):
        """Provenance failure returns actionable guidance."""
        arguments = {
            "who": "Someone",
            "user_pain_verbatim": "Some pain",
            "why": "For reasons",
            "who_stated_by_user": False,
            "why_reframed_from_pain": False,
            "user_confirmed_framing": False,
        }

        result = await handle(arguments)

        assert "assistant_guidance" in result.structuredContent
        instruction = result.structuredContent["assistant_guidance"]["instruction"]
        assert "SHARPEN MODE STILL BINDING" in instruction
```

Update existing handler tests to include provenance flags:

```python
@pytest.mark.asyncio
async def test_valid_input_returns_confirmed_true(self):
    """Valid input with provenance returns confirmed=True."""
    arguments = {
        "who": "My team",
        "user_pain_verbatim": "They waste time searching for info",
        "why": "So they can find information quickly",
        "who_stated_by_user": True,
        "why_reframed_from_pain": True,
        "user_confirmed_framing": True,
    }

    result = await handle(arguments)

    assert result.isError is not True
    assert result.structuredContent["confirmed"] is True
```

---

## Verification Checklist

### Schema (`frame_initiative_intent.py`)
- [ ] INPUT_SCHEMA has `user_pain_verbatim` field (non-empty required)
- [ ] INPUT_SCHEMA has THREE boolean provenance fields (not four)
- [ ] INPUT_SCHEMA does NOT have `confidence` field
- [ ] INPUT_SCHEMA does NOT have `pain_stated_by_user` field
- [ ] `required` array includes all new fields

### Pydantic Model (`frame_initiative_intent.py`)
- [ ] `FrameIntentRequest` has `user_pain_verbatim: Optional[str]`
- [ ] `FrameIntentRequest` has THREE `Optional[bool]` provenance fields
- [ ] `FrameIntentRequest` does NOT have `confidence` field
- [ ] `FrameIntentRequest` does NOT have `pain_stated_by_user` field

### DESCRIPTION (`frame_initiative_intent.py`)
- [ ] Explains provenance evidence requirement
- [ ] Shows example with verbatim quote (no `pain_stated_by_user`)
- [ ] Does NOT mention `confidence`

### Logic (`tool_logic.py`)
- [ ] `validate_intent_provenance` function added
- [ ] Checks THREE booleans (not four)
- [ ] Rejects empty verbatim first (not as inconsistency)
- [ ] Returns `failed_checks` list

### Handler (`frame_initiative_intent.py`)
- [ ] Calls `validate_intent_provenance` before structural validation
- [ ] Returns `provenance` object in success response (THREE booleans)
- [ ] Does NOT check `confidence`

### Tests
- [ ] `TestValidateIntentProvenance` class added
- [ ] Tests check for `empty_verbatim` error (not `empty_verbatim_inconsistent`)
- [ ] `TestFrameIntentHandlerProvenance` class added
- [ ] Existing tests updated with provenance flags (THREE, not four)
- [ ] All tests pass

---

## Risk Assessment

**Medium risk.** This changes the Step 1.1 schema significantly.

**Breaking changes:**
- `confidence` field removed
- Three new required boolean fields
- One new required string field (`user_pain_verbatim`)

**Mitigation:**
- Clear error messages explain what's missing
- DESCRIPTION shows exact usage
- Provenance failures return actionable guidance

**Expected LLM behavior change:**
- LLM will initially fail provenance checks
- Error messages will force it to ask questions
- After a few interactions, LLM learns the pattern

This is intentional — the failures are the enforcement mechanism.

---

**Document Status:** Ready for Claude Code execution
