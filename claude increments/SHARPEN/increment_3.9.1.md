# SHARPEN V1 — INCREMENT 3.9.1: Mandatory Observable Refinement

## Claude Code Briefing

---

## Objective

Make observable elicitation mandatory, not optional. The LLM currently decides if pain is "abstract enough" to ask for observables — it's too lenient.

**Current state:** Observable question is optional ("If pain is abstract...")

**New state:** Observable question is mandatory. WHY must derive from observable, not raw pain.

---

## Design Rationale

### Problem

User gives vague pain:
```
"they feel disoriented and blocked in the first 4 weeks"
```

LLM accepts it and reframes directly:
```
WHY: "so new engineering hires feel oriented and unblocked within their first 4 weeks"
```

This is a paraphrase, not a sharpened outcome.

### Solution

Force the observable question ALWAYS:

```
Pain: "they feel disoriented and blocked in the first 4 weeks"
       ↑ captured in user_pain_verbatim

LLM MUST ask: "What would you see happening differently if onboarding worked?"

User: "They'd find documentation themselves and submit their first PR within 2 weeks"
       ↑ captured in user_observable_verbatim

WHY: "So they can find documentation independently and ship their first PR within 2 weeks"
       ↑ derived from observable, much sharper
```

### Why This Works

- Extra friction improves quality even when pain seems concrete
- Observable question forces user to think about measurable outcomes
- WHY derived from observable is inherently more actionable
- Pattern: structure beats instruction

---

## Files to Modify

1. `mcp_server/sharpen/tools/frame_initiative_intent.py`
2. `mcp_server/sharpen/tool_logic.py`
3. `tests/unit/mcp_sharpen/test_frame_initiative_intent.py`

---

## Change 1: `frame_initiative_intent.py` — Schema Update

### Update INPUT_SCHEMA

Add `user_observable_verbatim` field and rename boolean:

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
            "description": "User's EXACT words describing their pain, frustration, or problem. Copy-paste from their message. Must be non-empty.",
        },
        "user_observable_verbatim": {
            "type": "string",
            "description": "User's EXACT words describing what would be different if this worked. Must be non-empty — ALWAYS ask 'What would you see happening differently?' even if pain seems concrete.",
        },
        "why": {
            "type": "string",
            "description": "YOUR reframe of user_observable_verbatim into an outcome. Must be traceable to the observable quote, not the raw pain. Do not invent — derive from the observable.",
        },
        "who_stated_by_user": {
            "type": "boolean",
            "description": "True ONLY if user explicitly stated WHO in their own words. False if you inferred, generalized, or suggested it.",
        },
        "why_reframed_from_observable": {
            "type": "boolean",
            "description": "True ONLY if WHY was derived by reframing user_observable_verbatim (not user_pain_verbatim). False if WHY was generated without the observable question.",
        },
        "user_confirmed_framing": {
            "type": "boolean",
            "description": "True ONLY if you reflected WHO + WHY back and user explicitly confirmed (e.g. 'yes', 'correct', 'that's right').",
        },
    },
    "required": [
        "who",
        "user_pain_verbatim",
        "user_observable_verbatim",
        "why",
        "who_stated_by_user",
        "why_reframed_from_observable",
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
    user_observable_verbatim: Optional[str] = None
    why: Optional[str] = None
    who_stated_by_user: Optional[bool] = None
    why_reframed_from_observable: Optional[bool] = None
    user_confirmed_framing: Optional[bool] = None
```

---

## Change 2: `frame_initiative_intent.py` — DESCRIPTION Update

Update elicitation order to make observable mandatory:

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
- Skipping the observable question

ACTIVE BEHAVIORS:
- Ask ONE question at a time
- Wait for answer
- Quote user's exact words back to them
- ALWAYS ask the observable question (even if pain seems concrete)
- Reframe observable → outcome
- Confirm with user
- Call tool only after explicit user confirmation

ELICITATION ORDER (ALL STEPS MANDATORY):
1. WHO: "Who specifically is supposed to benefit from this?"
   → Wait for answer. Store exact words.
2. PAIN: "What's currently hard or frustrating for them?"
   → Wait for answer. Store EXACT quote in user_pain_verbatim.
3. OBSERVABLE: "What would you see happening differently if this worked?"
   → ALWAYS ASK THIS. Even if pain seems concrete.
   → Prompt for concrete behaviors or artifacts, not feelings.
   → Say: "Describe a concrete behavior or artifact you would see — not a feeling or general improvement."
   → Wait for answer. Store EXACT quote in user_observable_verbatim.
   
   GOOD observables (accept these):
   - "They'd submit their first PR within 2 weeks"
   - "They'd find documentation without asking"
   - "The onboarding checklist would exist and be current"
   
   BAD observables (push back on these):
   - "They'd feel more confident" ← feeling
   - "They'd understand the system better" ← meta state
   - "Onboarding would be smoother" ← vague improvement
   
   If user gives vague observable, push back:
   "That sounds like a feeling or general improvement. What concrete behavior or artifact would you actually see?"
4. REFRAME: Convert observable → outcome-phrased WHY
   → "So they can [outcome derived from observable]"
   → WHY must trace to observable, NOT raw pain.
5. CONFIRM: "To confirm: [WHO] needs something so that [WHY]. Correct?"
   → Wait for explicit "yes" / "correct" / confirmation.

CRITICAL: Do NOT ask about WHAT/solution yet. Problem understanding comes first.
CRITICAL: Do NOT skip the observable question. It sharpens vague pain into actionable outcomes.

PROVENANCE EVIDENCE REQUIRED:
This tool requires proof that data came from the user:
- user_pain_verbatim: Copy-paste the user's exact pain words. Must be non-empty.
- user_observable_verbatim: Copy-paste the user's exact observable words. Must be non-empty.
- who_stated_by_user: Did user say WHO? If false, tool rejects.
- why_reframed_from_observable: Is WHY derived from the observable (not raw pain)? If false, tool rejects.
- user_confirmed_framing: Did user confirm? If false, tool rejects.

If you cannot honestly set ALL booleans to true AND provide BOTH non-empty verbatim quotes, do NOT call the tool. Ask the missing question first.

EXAMPLE CONVERSATION:
  User: "I want to improve our onboarding"
  You: "Who specifically is supposed to benefit from this?"
  User: "New engineering hires"
  You: "What's currently hard or frustrating for new engineering hires?"
  User: "They feel disoriented and blocked in the first 4 weeks"
       ↑ THIS IS user_pain_verbatim — store exactly
  You: "What would you see happening differently if onboarding worked? Describe a concrete behavior or artifact — not a feeling or general improvement."
       ↑ ALWAYS ASK THIS — do not skip
  User: "They'd find documentation themselves and submit their first PR within 2 weeks"
       ↑ THIS IS user_observable_verbatim — store exactly
  You: "To confirm: New engineering hires need something so they can find documentation independently and ship their first PR within 2 weeks. Correct?"
       ↑ WHY reframed from observable, NOT from raw pain
  User: "Yes"
       ↑ NOW user_confirmed_framing = true
  → Call tool with:
    who="New engineering hires"
    user_pain_verbatim="They feel disoriented and blocked in the first 4 weeks"
    user_observable_verbatim="They'd find documentation themselves and submit their first PR within 2 weeks"
    why="So they can find documentation independently and ship their first PR within 2 weeks"
    who_stated_by_user=true
    why_reframed_from_observable=true
    user_confirmed_framing=true
"""
```

---

## Change 3: `frame_initiative_intent.py` — Guidance Constants

Add guidance for empty observable:

```python
GUIDANCE_PROVENANCE_FAILED = (
    "SHARPEN MODE STILL BINDING. "
    "Provenance check failed. You must have evidence from the user before calling this tool.\n"
    "- If WHO not stated: Ask 'Who specifically is supposed to benefit from this?'\n"
    "- If pain not stated: Ask 'What's currently hard or frustrating for them?'\n"
    "- If observable not stated: Ask 'What would you see happening differently if this worked? Describe a concrete behavior or artifact — not a feeling or general improvement.'\n"
    "- If WHY not derived from observable: Reframe the user's observable into an outcome first.\n"
    "- If not confirmed: Reflect WHO + WHY back and ask 'Correct?'\n"
    "Ask ONE question. Then stop and wait."
)

GUIDANCE_EMPTY_PAIN_VERBATIM = (
    "SHARPEN MODE STILL BINDING. "
    "user_pain_verbatim is empty. Do not call this tool until user has stated a pain. "
    "Ask: 'What's currently hard or frustrating for [WHO]?' "
    "Then store their exact answer in user_pain_verbatim."
)

GUIDANCE_EMPTY_OBSERVABLE_VERBATIM = (
    "SHARPEN MODE STILL BINDING. "
    "user_observable_verbatim is empty. Do not call this tool until user has answered the observable question. "
    "Ask: 'What would you see happening differently if this worked? Describe a concrete behavior or artifact — not a feeling or general improvement.' "
    "Then store their exact answer in user_observable_verbatim. "
    "ALWAYS ask this question — even if pain seems concrete."
)

GUIDANCE_MISSING_FIELDS = (
    "SHARPEN MODE STILL BINDING. "
    "Ask ONE question about the missing field:\n"
    "- Missing WHO: 'Who specifically is supposed to benefit from this?'\n"
    "- Missing WHY: First get pain, then observable, then reframe to outcome.\n"
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

Update handler to validate both verbatim fields:

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
    why_reframed = validated_request.why_reframed_from_observable or False
    user_confirmed = validated_request.user_confirmed_framing or False
    pain_verbatim = (validated_request.user_pain_verbatim or "").strip()
    observable_verbatim = (validated_request.user_observable_verbatim or "").strip()

    # Provenance validation
    provenance_result = validate_intent_provenance(
        who_stated_by_user=who_stated,
        why_reframed_from_observable=why_reframed,
        user_confirmed_framing=user_confirmed,
        user_pain_verbatim=pain_verbatim,
        user_observable_verbatim=observable_verbatim,
    )

    if not provenance_result["valid"]:
        error_type = provenance_result["error_type"]

        if error_type == "empty_pain_verbatim":
            guidance = GUIDANCE_EMPTY_PAIN_VERBATIM
        elif error_type == "empty_observable_verbatim":
            guidance = GUIDANCE_EMPTY_OBSERVABLE_VERBATIM
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
               has_pain_verbatim=bool(pain_verbatim),
               has_observable_verbatim=bool(observable_verbatim))

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Problem framing confirmed: {intent['who']} needs something so that {intent['why']}",
        )],
        structuredContent={
            "framing_intent": intent,
            "provenance": {
                "user_pain_verbatim": pain_verbatim,
                "user_observable_verbatim": observable_verbatim,
                "who_stated_by_user": True,
                "why_reframed_from_observable": True,
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

## Change 5: `tool_logic.py` — Update Provenance Validation

Replace `validate_intent_provenance` with updated signature:

```python
def validate_intent_provenance(
    who_stated_by_user: bool,
    why_reframed_from_observable: bool,
    user_confirmed_framing: bool,
    user_pain_verbatim: str,
    user_observable_verbatim: str,
) -> dict[str, Any]:
    """
    Validate provenance evidence for frame_initiative_intent.

    All three booleans must be True AND both verbatim fields must be non-empty.

    Applies defensive normalization to verbatim fields (strips whitespace).

    Args:
        who_stated_by_user: Did user explicitly state WHO?
        why_reframed_from_observable: Is WHY derived from the observable (not raw pain)?
        user_confirmed_framing: Did user explicitly confirm the framing?
        user_pain_verbatim: User's exact words describing the pain
        user_observable_verbatim: User's exact words describing what would be different

    Returns:
        {"valid": bool, "error_type": str | None, "error_details": str | None, "failed_checks": list}
    """
    # Defensive normalization
    user_pain_verbatim = (user_pain_verbatim or "").strip()
    user_observable_verbatim = (user_observable_verbatim or "").strip()

    # Pain verbatim is required first
    if not user_pain_verbatim:
        return {
            "valid": False,
            "error_type": "empty_pain_verbatim",
            "error_details": "user_pain_verbatim is empty. Do not call this tool until user has stated a pain.",
            "failed_checks": ["user_pain_verbatim"],
        }

    # Observable verbatim is required — ALWAYS ask
    if not user_observable_verbatim:
        return {
            "valid": False,
            "error_type": "empty_observable_verbatim",
            "error_details": "user_observable_verbatim is empty. Do not call this tool until user has answered the observable question.",
            "failed_checks": ["user_observable_verbatim"],
        }

    failed_checks = []

    if not who_stated_by_user:
        failed_checks.append("who_stated_by_user")
    if not why_reframed_from_observable:
        failed_checks.append("why_reframed_from_observable")
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

Update `TestValidateIntentProvenance` tests:

```python
class TestValidateIntentProvenance:
    """Tests for validate_intent_provenance function."""

    def test_all_true_with_both_verbatims_valid(self):
        """All provenance flags True with both verbatims is valid."""
        result = validate_intent_provenance(
            who_stated_by_user=True,
            why_reframed_from_observable=True,
            user_confirmed_framing=True,
            user_pain_verbatim="They feel disoriented and blocked",
            user_observable_verbatim="They'd find docs and submit first PR within 2 weeks",
        )

        assert result["valid"] is True
        assert result["failed_checks"] == []

    def test_empty_pain_verbatim_rejects(self):
        """Empty pain verbatim is rejected."""
        result = validate_intent_provenance(
            who_stated_by_user=True,
            why_reframed_from_observable=True,
            user_confirmed_framing=True,
            user_pain_verbatim="",
            user_observable_verbatim="They'd find docs",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_pain_verbatim"

    def test_empty_observable_verbatim_rejects(self):
        """Empty observable verbatim is rejected — observable is mandatory."""
        result = validate_intent_provenance(
            who_stated_by_user=True,
            why_reframed_from_observable=True,
            user_confirmed_framing=True,
            user_pain_verbatim="They feel blocked",
            user_observable_verbatim="",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_observable_verbatim"

    def test_who_not_stated_rejects(self):
        """who_stated_by_user=False is rejected."""
        result = validate_intent_provenance(
            who_stated_by_user=False,
            why_reframed_from_observable=True,
            user_confirmed_framing=True,
            user_pain_verbatim="Some pain",
            user_observable_verbatim="Some observable",
        )

        assert result["valid"] is False
        assert "who_stated_by_user" in result["failed_checks"]

    def test_why_not_reframed_from_observable_rejects(self):
        """why_reframed_from_observable=False is rejected."""
        result = validate_intent_provenance(
            who_stated_by_user=True,
            why_reframed_from_observable=False,
            user_confirmed_framing=True,
            user_pain_verbatim="Some pain",
            user_observable_verbatim="Some observable",
        )

        assert result["valid"] is False
        assert "why_reframed_from_observable" in result["failed_checks"]

    def test_not_confirmed_rejects(self):
        """user_confirmed_framing=False is rejected."""
        result = validate_intent_provenance(
            who_stated_by_user=True,
            why_reframed_from_observable=True,
            user_confirmed_framing=False,
            user_pain_verbatim="Some pain",
            user_observable_verbatim="Some observable",
        )

        assert result["valid"] is False
        assert "user_confirmed_framing" in result["failed_checks"]

    def test_multiple_failures_lists_all(self):
        """Multiple failed checks are all listed."""
        result = validate_intent_provenance(
            who_stated_by_user=False,
            why_reframed_from_observable=False,
            user_confirmed_framing=False,
            user_pain_verbatim="Some pain",
            user_observable_verbatim="Some observable",
        )

        assert result["valid"] is False
        assert len(result["failed_checks"]) == 3

    def test_whitespace_only_pain_verbatim_rejects(self):
        """Whitespace-only pain verbatim is treated as empty."""
        result = validate_intent_provenance(
            who_stated_by_user=True,
            why_reframed_from_observable=True,
            user_confirmed_framing=True,
            user_pain_verbatim="   ",
            user_observable_verbatim="Some observable",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_pain_verbatim"

    def test_whitespace_only_observable_verbatim_rejects(self):
        """Whitespace-only observable verbatim is treated as empty."""
        result = validate_intent_provenance(
            who_stated_by_user=True,
            why_reframed_from_observable=True,
            user_confirmed_framing=True,
            user_pain_verbatim="Some pain",
            user_observable_verbatim="   ",
        )

        assert result["valid"] is False
        assert result["error_type"] == "empty_observable_verbatim"

    def test_pain_checked_before_observable(self):
        """Pain verbatim is checked before observable verbatim."""
        result = validate_intent_provenance(
            who_stated_by_user=True,
            why_reframed_from_observable=True,
            user_confirmed_framing=True,
            user_pain_verbatim="",
            user_observable_verbatim="",
        )

        # Should fail on pain first, not observable
        assert result["error_type"] == "empty_pain_verbatim"
```

Update handler tests with new field:

```python
class TestFrameIntentHandlerProvenance:
    """Tests for handler provenance validation."""

    @pytest.mark.asyncio
    async def test_all_provenance_true_succeeds(self):
        """All provenance flags True with both verbatims succeeds."""
        arguments = {
            "who": "New engineering hires",
            "user_pain_verbatim": "They feel disoriented and blocked in the first 4 weeks",
            "user_observable_verbatim": "They'd find documentation themselves and submit their first PR within 2 weeks",
            "why": "So they can find documentation independently and ship their first PR within 2 weeks",
            "who_stated_by_user": True,
            "why_reframed_from_observable": True,
            "user_confirmed_framing": True,
        }

        result = await handle(arguments)

        assert result.isError is not True
        assert result.structuredContent["confirmed"] is True
        assert "provenance" in result.structuredContent

    @pytest.mark.asyncio
    async def test_empty_observable_verbatim_rejects(self):
        """Empty observable verbatim is rejected."""
        arguments = {
            "who": "New engineering hires",
            "user_pain_verbatim": "They feel blocked",
            "user_observable_verbatim": "",
            "why": "So they can work independently",
            "who_stated_by_user": True,
            "why_reframed_from_observable": True,
            "user_confirmed_framing": True,
        }

        result = await handle(arguments)

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_observable_verbatim"

    @pytest.mark.asyncio
    async def test_empty_observable_returns_specific_guidance(self):
        """Empty observable returns specific guidance about asking observable question."""
        arguments = {
            "who": "Team",
            "user_pain_verbatim": "They struggle",
            "user_observable_verbatim": "",
            "why": "To succeed",
            "who_stated_by_user": True,
            "why_reframed_from_observable": True,
            "user_confirmed_framing": True,
        }

        result = await handle(arguments)

        instruction = result.structuredContent["assistant_guidance"]["instruction"]
        assert "user_observable_verbatim is empty" in instruction
        assert "What would you see happening differently" in instruction

    @pytest.mark.asyncio
    async def test_valid_input_includes_both_verbatims_in_provenance(self):
        """Valid input includes both verbatims in provenance object."""
        arguments = {
            "who": "New hires",
            "user_pain_verbatim": "They feel lost",
            "user_observable_verbatim": "They'd navigate independently",
            "why": "So they can navigate independently",
            "who_stated_by_user": True,
            "why_reframed_from_observable": True,
            "user_confirmed_framing": True,
        }

        result = await handle(arguments)

        assert "provenance" in result.structuredContent
        provenance = result.structuredContent["provenance"]
        assert provenance["user_pain_verbatim"] == "They feel lost"
        assert provenance["user_observable_verbatim"] == "They'd navigate independently"
        assert provenance["why_reframed_from_observable"] is True

    @pytest.mark.asyncio
    async def test_why_reframed_from_observable_false_rejects(self):
        """why_reframed_from_observable=False is rejected."""
        arguments = {
            "who": "New hires",
            "user_pain_verbatim": "They feel blocked",
            "user_observable_verbatim": "They'd find docs",
            "why": "So they feel unblocked",  # This is from pain, not observable
            "who_stated_by_user": True,
            "why_reframed_from_observable": False,
            "user_confirmed_framing": True,
        }

        result = await handle(arguments)

        assert result.isError is True
        assert "why_reframed_from_observable" in result.structuredContent["failed_checks"]
```

Update existing tests to include observable field:

```python
@pytest.mark.asyncio
async def test_valid_input_returns_confirmed_true(self):
    """Valid input with provenance returns confirmed=True."""
    arguments = {
        "who": "My team",
        "user_pain_verbatim": "They waste time searching for info",
        "user_observable_verbatim": "They'd find information in under 5 minutes",
        "why": "So they can find information quickly",
        "who_stated_by_user": True,
        "why_reframed_from_observable": True,
        "user_confirmed_framing": True,
    }

    result = await handle(arguments)

    assert result.isError is not True
    assert result.structuredContent is not None
    assert result.structuredContent["confirmed"] is True
```

---

## Verification Checklist

### Schema (`frame_initiative_intent.py`)
- [ ] INPUT_SCHEMA has `user_pain_verbatim` field
- [ ] INPUT_SCHEMA has `user_observable_verbatim` field (NEW)
- [ ] INPUT_SCHEMA has `why_reframed_from_observable` (renamed from `why_reframed_from_pain`)
- [ ] `required` array includes `user_observable_verbatim`

### Pydantic Model (`frame_initiative_intent.py`)
- [ ] `FrameIntentRequest` has `user_observable_verbatim: Optional[str]`
- [ ] `FrameIntentRequest` has `why_reframed_from_observable: Optional[bool]`
- [ ] Does NOT have `why_reframed_from_pain`

### DESCRIPTION (`frame_initiative_intent.py`)
- [ ] Observable question marked as MANDATORY (not optional)
- [ ] Elicitation order includes OBSERVABLE step
- [ ] Example shows both verbatim fields
- [ ] WHY derivation explicitly from observable, not pain

### Logic (`tool_logic.py`)
- [ ] `validate_intent_provenance` has `user_observable_verbatim` parameter
- [ ] `validate_intent_provenance` has `why_reframed_from_observable` parameter
- [ ] Empty observable returns `empty_observable_verbatim` error
- [ ] Pain checked before observable (logical order)

### Handler (`frame_initiative_intent.py`)
- [ ] Extracts `observable_verbatim`
- [ ] Passes to `validate_intent_provenance`
- [ ] Returns both verbatims in `provenance` object
- [ ] Has `GUIDANCE_EMPTY_OBSERVABLE_VERBATIM` constant

### Tests
- [ ] `test_empty_observable_verbatim_rejects`
- [ ] `test_whitespace_only_observable_verbatim_rejects`
- [ ] `test_pain_checked_before_observable`
- [ ] All existing tests updated with observable field

---

## Risk Assessment

**Low risk.** This is a refinement to an already validated pattern.

**Breaking changes:**
- New required field: `user_observable_verbatim`
- Renamed boolean: `why_reframed_from_pain` → `why_reframed_from_observable`

**Mitigation:**
- Clear error messages explain what's missing
- DESCRIPTION explicitly marks observable as mandatory
- Guidance instructs LLM to ask observable question with explicit framing

---

## Known Gaps (Deferred)

**Gap:** Observable quality enforcement (structural)

**Description:** The guidance tells the LLM to:
1. Ask for "concrete behaviors or artifacts, not feelings"
2. Shows GOOD vs BAD examples
3. Instructs to push back if user gives vague observable

However, there is no structural validation that rejects abstract observables. The LLM could still accept "they feel confident" if it ignores the guidance.

**Why deferred:** 
- Requires keyword blocklist or NLP to detect abstract phrasing
- Adds complexity without proven need
- Guidance + examples + pushback instruction sets strong expectations
- Structure can come later if guidance proves insufficient

**Trigger to revisit:** If real usage shows LLMs accepting abstract observables like "they understand better" or "onboarding is smoother" despite the explicit guidance and examples.

**Potential fix:** Add `_is_abstract_observable()` blocklist check with patterns like "feel ", "understand", "confident", "smoother", "better", "improved".

---

**Document Status:** Ready for Claude Code execution
