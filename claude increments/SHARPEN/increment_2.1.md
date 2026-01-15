# SHARPEN V1 — INCREMENT 2.1: Refactor to LLM-Driven Semantic Evaluation

## Claude Code Briefing

---

## Objective

Refactor Step 1 tools to remove backend vagueness/confidence evaluation. Move semantic reasoning to the LLM via goal-oriented tool descriptions. Backend becomes a structural checkpoint only.

---

## Why This Change

**Current approach (wrong):**
- Backend uses substring matching to detect "vague" words
- Backend calculates confidence levels
- Backend decides when to clarify vs. proceed
- Result: False positives ("Create deployment script" flagged as activity), brittle logic, duplicates LLM capability

**New approach (correct):**
- Backend validates structure only (required fields present, not empty)
- LLM evaluates semantic quality (vague? concrete? artifact or activity?)
- LLM decides when to call tool (only when WHO/WHAT are clear and confirmed)
- Tool description explains the goal, criteria, and facilitator role

**Core insight:** The LLM is better at semantic reasoning. Let it do that job. Backend should be a checkpoint, not a judge.

---

## What Sharpen Is (Context for Changes)

Sharpen is **pre-planning thinking work** — breakdown and elimination, not planning.

Step 1 exists to lock in WHO and WHAT before breakdown begins. Without clear WHO and WHAT, you can't evaluate what work to eliminate.

Sharpen's job is to maximize work not done.

---

## Files to Change

```
mcp_server/sharpen/
├── tool_logic.py                           # SIMPLIFY
├── tools/
│   ├── frame_initiative_intent.py          # SIMPLIFY + NEW DESCRIPTION
│   └── frame_initiative_constraints.py     # SIMPLIFY + NEW DESCRIPTION
└── tests/
    ├── test_frame_initiative_intent.py     # UPDATE
    └── test_frame_initiative_constraints.py # UPDATE
```

---

## Changes to `tool_logic.py`

### Remove

Delete these constants entirely:
```python
# DELETE ALL OF THIS:
VAGUE_WHAT_WORDS = [...]
ACTIVITY_VERBS = [...]
VAGUE_CONSTRAINT_WORDS = [...]
VAGUE_FINISHED_WORDS = [...]

def _contains_vague_word(text: str, vague_words: list[str]) -> bool:
    ...

def _starts_with_activity_verb(text: str) -> bool:
    ...
```

### Simplify `validate_initiative_intent`

**Before:** Returns confidence, needs_clarification, clarify_type based on vague word detection.

**After:** Returns structural validation only.

```python
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

    return {
        "framing_intent": {
            "who": who,
            "what": what,
            "why": why,
        },
        "valid": valid,
        "missing": [] if valid else [f for f in ["who", "what"] if not locals()[f]],
    }
```

### Simplify `validate_initiative_constraints`

**Before:** Returns confidence, needs_clarification, clarify_type, force_constraint based on vague word detection.

**After:** Returns structural validation + force_constraint flag only.

```python
def validate_initiative_constraints(
    confirmed_intent: dict | None,
    constraint_type: str | None = None,
    constraint_value: str | None = None,
    definition_of_finished: str | None = None,
    user_claims_no_constraints: bool = False,
) -> dict[str, Any]:
    """
    Validate structure of constraints and definition of finished.
    
    Structural validation only — semantic quality is LLM's job.
    
    Args:
        confirmed_intent: Output from frame_initiative_intent (who, what, why)
        constraint_type: time, capacity, budget, or forced_mvp
        constraint_value: The specific constraint in user's words
        definition_of_finished: How will you know WHAT is finished?
        user_claims_no_constraints: True if user claims no constraints

    Returns:
        initiative_framing dict + valid flag + force_constraint flag
    """
    # Validate confirmed_intent exists
    if not confirmed_intent:
        return {
            "initiative_framing": None,
            "valid": False,
            "intent_missing": True,
            "force_constraint": False,
        }

    who = (confirmed_intent.get("who") or "").strip()
    what = (confirmed_intent.get("what") or "").strip()
    why = confirmed_intent.get("why")
    if why:
        why = why.strip() if why else None

    if not who or not what:
        return {
            "initiative_framing": None,
            "valid": False,
            "intent_missing": True,
            "force_constraint": False,
        }

    # Normalize inputs
    constraint_type = (constraint_type or "").strip() or None
    constraint_value = (constraint_value or "").strip() or None
    definition_of_finished = (definition_of_finished or "").strip() or None

    # Handle user claiming no constraints — return early, don't build framing
    if user_claims_no_constraints:
        return {
            "initiative_framing": None,
            "valid": False,
            "intent_missing": False,
            "force_constraint": True,
        }

    # Build initiative framing
    initiative_framing = {
        "who": who,
        "what": what,
        "why": why,
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
        "initiative_framing": initiative_framing,
        "valid": valid,
        "missing": missing,
        "intent_missing": False,
        "force_constraint": False,
    }
```

---

## Changes to `frame_initiative_intent.py`

### New Tool Description (Goal-Oriented)

```python
DESCRIPTION = """Records the confirmed WHO and WHAT of an initiative after the user has articulated them clearly.

PURPOSE: This tool creates a checkpoint — it locks in the beneficiary and concrete outcome before breakdown begins. Without clear WHO and WHAT, you cannot evaluate what work to eliminate.

CALL ONLY WHEN:
- User has stated WHO benefits (specific person or group, not "someone", "people", "users")
- User has stated WHAT must exist (a concrete artifact or deliverable, not an activity like "work on X" or vague like "improve Y")
- User has confirmed both

DO NOT CALL when WHO or WHAT are still vague, abstract, or unconfirmed. Ask clarifying questions first.

FACILITATOR ROLE: Your job is to draw out clarity through questions. Never suggest what WHO or WHAT should be. Never give examples. Use the user's exact words."""
```

### Simplified Handler

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

    # Structural validation only
    result = validate_initiative_intent(
        who=validated_request.who,
        what=validated_request.what,
        why=validated_request.why,
    )

    # If structurally invalid, return error
    if not result["valid"]:
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=f"Missing required fields: {', '.join(result['missing'])}",
            )],
            structuredContent={
                "error": "missing_fields",
                "missing": result["missing"],
                "assistant_guidance": {
                    "instruction": "Ask the user to provide the missing information. Do not suggest what it should be.",
                },
            },
            isError=True,
        )

    # Valid — return confirmed framing
    intent = result["framing_intent"]
    
    logger.info("frame_initiative_intent.complete", who=intent["who"], what=intent["what"])

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Intent confirmed: {intent['who']} needs {intent['what']}" + 
                 (f" so that {intent['why']}" if intent.get("why") else ""),
        )],
        structuredContent={
            "framing_intent": intent,
            "confirmed": True,
            "assistant_guidance": {
                "instruction": "Present the confirmed intent to the user. Then proceed to capture constraints by calling frame_initiative_constraints. Do not suggest what constraints might be — ask the user.",
            },
        },
    )
```

### Remove

- `GUIDANCE_CLARIFY_WHO`
- `GUIDANCE_CLARIFY_WHAT`  
- `GUIDANCE_CONFIRM`
- All confidence/clarification logic

---

## Changes to `frame_initiative_constraints.py`

### New Tool Description (Goal-Oriented)

```python
DESCRIPTION = """Records the confirmed CONSTRAINT and DEFINITION OF FINISHED for an initiative.

PURPOSE: This tool locks in the dominant constraint and success criteria before breakdown begins. Without a clear constraint, scope expands endlessly. Without a definition of finished, work is never done.

REQUIRES: Confirmed intent from frame_initiative_intent (pass as confirmed_intent).

CALL ONLY WHEN:
- User has stated ONE dominant constraint:
  - time: specific deadline ("by March 15", "within 2 weeks")
  - capacity: specific availability ("4 hours per week", "2 focused sessions")
  - budget: specific limit ("under $500", "no external spend")
  - forced_mvp: smallest result worth continuing (use when user initially claimed no constraints)
- User has stated a concrete definition of finished (verifiable condition, not "done" or "ready")
- User has confirmed both

SPECIAL CASE — NO CONSTRAINTS CLAIMED:
If user says "no constraints", set user_claims_no_constraints=true. 
Then ask: "What is the smallest concrete result that would make this initiative worth continuing?"
Use their answer as constraint_type="forced_mvp" with their answer as constraint_value.

DO NOT CALL when constraint or definition of finished are vague or unconfirmed. Ask clarifying questions first.

FACILITATOR ROLE: Your job is to surface real limits through questions. Never suggest constraints. Never estimate for the user. Wait for their numbers."""
```

### Simplified Handler

```python
async def handle(arguments: dict) -> mcp_types.CallToolResult:
    """Handle frame_initiative_constraints tool call."""
    logger.debug("frame_initiative_constraints.handle.start",
                argument_keys=list(arguments.keys()))

    # Pydantic validation
    try:
        validated_request = FrameConstraintsRequest.model_validate(arguments)
    except ValidationError as e:
        logger.warning("frame_initiative_constraints.validation_failed", error=str(e.errors()))
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text="Invalid input format.")],
            structuredContent={"error": "validation_error", "details": e.errors()},
            isError=True,
        )

    # Convert to dict for pure function
    confirmed_intent = None
    if validated_request.confirmed_intent:
        confirmed_intent = validated_request.confirmed_intent.model_dump()

    # Structural validation
    result = validate_initiative_constraints(
        confirmed_intent=confirmed_intent,
        constraint_type=validated_request.constraint_type,
        constraint_value=validated_request.constraint_value,
        definition_of_finished=validated_request.definition_of_finished,
        user_claims_no_constraints=validated_request.user_claims_no_constraints,
    )

    # Handle missing intent
    if result["intent_missing"]:
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Confirmed intent is required. Call frame_initiative_intent first.",
            )],
            structuredContent={
                "error": "intent_missing",
                "assistant_guidance": {
                    "instruction": "Call frame_initiative_intent first and get user confirmation before capturing constraints.",
                },
            },
            isError=True,
        )

    # Handle force constraint (user claimed no constraints)
    if result["force_constraint"]:
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="User claims no constraints. Ask for smallest concrete result worth continuing.",
            )],
            structuredContent={
                "force_constraint": True,
                "assistant_guidance": {
                    "instruction": "Ask: 'What is the smallest concrete result that would make this initiative worth continuing?' Wait for their answer — do not suggest. Use their answer as constraint_type='forced_mvp' and constraint_value=their answer. Then call this tool again.",
                },
            },
        )

    # If structurally invalid (missing fields)
    if not result["valid"]:
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=f"Missing required fields: {', '.join(result['missing'])}",
            )],
            structuredContent={
                "error": "missing_fields",
                "missing": result["missing"],
                "initiative_framing": result["initiative_framing"],
                "assistant_guidance": {
                    "instruction": "Ask the user to provide the missing information. Do not suggest what it should be. Do not estimate for them.",
                },
            },
            isError=True,
        )

    # Valid — return confirmed framing
    framing = result["initiative_framing"]
    
    logger.info("frame_initiative_constraints.complete",
                constraint_type=framing["constraint_type"],
                definition_of_finished=framing["definition_of_finished"][:50])

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Framing complete: {framing['who']} needs {framing['what']}. "
                 f"Constraint: {framing['constraint_type']} — {framing['constraint_value']}. "
                 f"Finished when: {framing['definition_of_finished']}",
        )],
        structuredContent={
            "initiative_framing": framing,
            "confirmed": True,
            "assistant_guidance": {
                "instruction": "Present the complete framing to the user using their exact words. Ask them to confirm. Only after confirmation, proceed to Step 2 (deliverable identification). Do not suggest what deliverables might be.",
            },
        },
    )
```

### Remove

- `GUIDANCE_INTENT_MISSING`
- `GUIDANCE_FORCE_CONSTRAINT`
- `GUIDANCE_CLARIFY_CONSTRAINT`
- `GUIDANCE_CLARIFY_FINISHED`
- `GUIDANCE_CONFIRM_COMPLETE`
- All confidence/clarification logic

---

## Test Updates

### `test_frame_initiative_intent.py`

**Remove tests for:**
- Vague word detection
- Activity verb detection
- Confidence levels
- Clarify types

**Keep/update tests for:**
- Empty WHO returns `valid=False`, `missing=["who"]`
- Empty WHAT returns `valid=False`, `missing=["what"]`
- Valid WHO + WHAT returns `valid=True`
- WHY is optional and included when provided
- Handler returns `confirmed=True` for valid input
- Handler returns `isError=True` for missing fields

### `test_frame_initiative_constraints.py`

**Remove tests for:**
- Vague constraint value detection
- Vague definition of finished detection
- Confidence levels
- Clarify types

**Keep/update tests for:**
- Missing confirmed_intent returns `intent_missing=True`
- `user_claims_no_constraints=True` returns `force_constraint=True`, `initiative_framing=None`
- Missing constraint_type returns `valid=False`
- Missing constraint_value returns `valid=False`
- Missing definition_of_finished returns `valid=False`
- Valid input returns `valid=True` with merged framing
- Handler returns `confirmed=True` for valid input
- Handler returns `isError=True` for missing fields

---

## Summary of Changes

| Component | Before | After |
|-----------|--------|-------|
| Vague word constants | In `tool_logic.py` | Deleted |
| Vague word detection | Backend substring matching | LLM semantic reasoning |
| Confidence calculation | Backend logic | Removed (LLM decides when to call) |
| Clarify type logic | Backend decides | Removed (LLM asks clarifying questions) |
| Tool description | Mechanical | Goal-oriented with criteria |
| Handler logic | Complex branching | Simple: valid or invalid |
| assistant_guidance | Multiple action types | Single instruction per state |

---

## Success Criteria

1. ✅ No vague word detection in backend
2. ✅ No confidence calculation in backend
3. ✅ Tool descriptions explain purpose, criteria, and facilitator role
4. ✅ Backend validates structure only (fields present, not empty)
5. ✅ `force_constraint` flow still works (user claims no constraints)
6. ✅ All tests pass (updated for new contract)
7. ✅ Facilitator role reinforced in descriptions

---

## Notes for Claude Code

1. **Delete aggressively.** Remove all vague word constants and detection functions. They're not needed.

2. **Simplify handlers.** No more confidence/clarify branching. Just: valid → return confirmed, invalid → return error with missing fields.

3. **Tool descriptions do the work.** The LLM reads these. Make them clear about purpose and criteria.

4. **Keep force_constraint.** This is structural logic (user explicitly said "no constraints"), not semantic evaluation.

5. **Update tests to match.** Remove tests for deleted functionality. Keep structural validation tests.

6. **Don't add new complexity.** The goal is simpler backend, smarter LLM usage.

---

**Document Status:** Ready for Claude Code execution