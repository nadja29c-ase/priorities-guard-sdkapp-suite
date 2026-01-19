# SHARPEN V1 — INCREMENT 3.2: Action Reframing + Scope Check

## Claude Code Briefing

---

## Objective

Update `identify_e2e_deliverables` tool to:
1. Guide LLM to reframe user actions → deliverables during conversation
2. Add scope check (T-shirt sizing) after deliverables confirmed, before cutoff selection

No new tools. No schema changes. Only DESCRIPTION and guidance updates.

---

## Why These Changes

**Action reframing:** Users naturally think in actions ("build API", "write docs"). Forcing deliverable-speak upfront feels coachy. Let them speak naturally, LLM converts.

**Scope check:** Users underestimate scope. Seeing "this feels XL" creates the pause that triggers subtraction BEFORE they commit.

Both support "maximize work not done" without adding friction or theory.

---

## File to Modify

`/mcp_server/sharpen/tools/identify_e2e_deliverables.py`

---

## Change 1: Add Action Handling Section to DESCRIPTION

**Insert after "ACTIVE BEHAVIORS" block, before "CONFIDENCE EXAMPLES":**

```
HANDLING ACTIONS (users naturally think this way):
Users often state actions ("build API", "write docs") instead of deliverables.
This is normal. Do NOT reject or lecture.

When user states an action, ask ONE question:
"When [action] is done, what will exist that didn't exist before?"

No theory. No explanation of why deliverables matter. Just reframe.

Example:
  User: "I need to build the API and write documentation"
  You: "When 'build the API' is done, what will exist? A deployed service? A spec?"
  User: "A deployed REST API"
  You: "And 'write documentation' — what artifact exists? README? OpenAPI spec?"
  User: "OpenAPI spec"
  You: "So we have: Deployed REST API, OpenAPI spec. Anything else?"

CRITICAL BOUNDARY:
- Actions allowed in conversation (user's natural language)
- Actions forbidden in candidate_deliverables (tool input = concrete outputs only)
```

---

## Change 2: Update EXAMPLE CONVERSATION in DESCRIPTION

**Replace existing example with:**

```
EXAMPLE CONVERSATION:
  User: [Step 1 framing confirmed]
  You: "What needs to exist for this initiative to be done? Don't filter — just name everything that comes to mind."
  User: "I need to build an API, write docs, and set up authentication"
  You: "I'm hearing three things. Let me check I understand the results. When 'build an API' is done, what exists?"
  User: "A deployed REST API that clients can call"
  You: "And 'write docs' — what artifact?"
  User: "OpenAPI spec"
  You: "And 'set up authentication' — what exists when that's done?"
  User: "Auth system where users can log in"
  You: "So we have: Deployed REST API, OpenAPI spec, Auth system. Anything else?"
  User: "No, that's the core"
  You: "To confirm: these three deliverables must exist for the initiative to be done. Correct?"
  User: "Yes"
  → Now call identify_e2e_deliverables with candidate_deliverables=[...], confidence="high"
```

---

## Change 3: Update GUIDANCE_CONFIRMED

**Replace existing GUIDANCE_CONFIRMED with:**

```python
GUIDANCE_CONFIRMED = (
    "Deliverables confirmed. Present them back to the user as an unordered list — "
    "no numbering, no priority implied. "
    "\n\n"
    "SCOPE CHECK (do this before cutoff selection):\n"
    "Ask: 'Quick check: looking at this set of deliverables as a whole, "
    "how big does this initiative feel right now? XS / S / M / L / XL — gut feel only, no estimating.'\n"
    "Wait for answer.\n"
    "- If XS, S, or M → proceed to cutoff selection\n"
    "- If L or XL → nudge ONCE: 'That size sometimes means there's room to subtract. "
    "If this had to be M or smaller, what could be removed or merged?'\n"
    "Then wait. Do not suggest what to remove. Do not loop.\n"
    "If user removes or merges items → reflect the updated list back and proceed to cutoff selection.\n"
    "If user says 'it's fine as is' → proceed to cutoff selection.\n"
    "\n"
    "CUTOFF SELECTION:\n"
    "Ask: 'If you could only complete one of these right now, which would it be? "
    "Everything else is explicitly deferred.'\n"
    "Do not suggest which to select. "
    "Call select_cutoff_deliverable with the user's choice."
)
```

---

## Change 4: Update GUIDANCE_EMPTY_DELIVERABLES

**Replace with:**

```python
GUIDANCE_EMPTY_DELIVERABLES = (
    "No deliverables provided. Ask: 'What needs to exist for this initiative "
    "to be done? Don't filter — just name everything that comes to mind.' "
    "If user states actions, reframe: 'When [action] is done, what will exist?' "
    "Wait for their answer. Do not suggest deliverables."
)
```

---

## No Other Changes Required

- Input schema: unchanged
- Validation logic: unchanged  
- Handler logic: unchanged
- Tests: unchanged (behavior is in guidance, not structure)

---

## Verification

After changes, confirm:

1. DESCRIPTION contains "HANDLING ACTIONS" section
2. DESCRIPTION example shows action → deliverable conversion
3. GUIDANCE_CONFIRMED includes scope check before cutoff
4. GUIDANCE_EMPTY_DELIVERABLES includes reframe hint
5. Tool still passes all existing tests

---

## Success Criteria

1. ✅ LLM guided to accept actions in conversation
2. ✅ LLM guided to reframe actions → deliverables via single question
3. ✅ Scope check happens after confirmation, before cutoff
4. ✅ L/XL triggers one subtraction nudge (non-blocking)
5. ✅ No recursion — scope check is conversational, not a re-run of the tool
6. ✅ No theory or explanation in user-facing guidance
7. ✅ All existing tests still pass

---

**Document Status:** Ready for Claude Code execution
