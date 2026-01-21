# SHARPEN V1 — INCREMENT 3.6: Pain-First Elicitation for Step 1

## Claude Code Briefing

---

## Objective

Change the elicitation sequence in Step 1 from outcome-language to pain-language while preserving the same data contract (WHO, WHAT, WHY).

**Current flow:** WHO → WHAT → WHY  
**New flow:** WHO → PAIN (becomes WHY) → (conditional) observable refinement → WHAT-as-hypothesis

This is a **prompt engineering change only**. No schema changes. No new tools. No structural logic changes.

---

## Design Rationale

### Problem with Current Approach

The current example conversation uses outcome/benefit language:
- "Who benefits?"
- "What concrete thing will exist?"
- "So that WHO benefits how?"

This is coaching methodology. Non-coach users think in:
- Problems
- Frustrations  
- Things that are missing
- Things they want built

### Solution: Pain-First Elicitation

Lead with pain, not outcomes. The LLM internally converts pain to outcome-phrased WHY.

| Instead of | Use |
|------------|-----|
| "How should they benefit?" | "What's currently hard or frustrating for them?" |
| "What outcome do you want?" | "What exact problem does this solve?" |

**Pain naturally reveals WHY without coaching jargon.**

### Conditional WHY Refinement

Only probe for observable change when WHY is:
- Abstract ("feel confident")
- Restates WHAT ("so we have a checklist")
- Motivational ("because onboarding matters")

Then ask ONE grounding question:
> "What would you see happening differently if this worked?"

Do NOT always ask this. Only when needed.

### WHAT as Hypothesis

Always phrase WHAT as provisional:
> "What exactly do you think needs to exist/ needs to be created to help with that?"

Never:
- "What should we build?"
- "What's the solution?"

This prevents premature commitment and aligns with Step 2 constraint filtering.

---

## Files to Modify

1. `mcp_server/sharpen/tools/frame_initiative_intent.py`

That's it. One file.

---

## Change 1: Update DESCRIPTION

### Find the current DESCRIPTION (around line 20)

Replace the entire DESCRIPTION string with:

```python
DESCRIPTION = """Records confirmed WHO, WHAT, and WHY of an initiative. This frames the initiative as outcome-focused so that later the amount of work can be minimized based on outcome. Requires confidence="high".

SHARPEN MODE — BINDING RULES (not guidelines)
When user selects Sharpen, your default assistant behavior is SUSPENDED.

SUSPENDED BEHAVIORS:
- Planning
- Offering options
- Suggesting answers
- Batching multiple questions
- Proposing deliverables or tasks
- "Being helpful" by front-loading structure

ACTIVE BEHAVIORS:
- Ask ONE question at a time
- Wait for answer
- Reflect their words back
- Ask for user confirmation
- Then call tool with confidence="high"

These are not suggestions. These are operating constraints.
Violating them means Sharpen is broken.

ELICITATION ORDER — WHO first, WHY second, Optional Observable refinement third, WHAT last. 
Lead with pain to elicit the WHY if the user is not aware of the specific value the user wants to create for the WHO.

1. WHO: "Who is this specifically for?"/ "Who is supposed to benefit from this initiative getting done?".
2. PAIN (becomes WHY): "What's currently hard or frustrating for them?"
3. (CONDITIONAL) Observable refinement — ONLY if WHY is vague/abstract/motivational:
   "What would you see happening differently if this worked?"/ "How would you know that the pain went away?"
4. WHAT (as hypothesis): "What exactly do you think needs to exist to help with that?"/ "What solution do you think will create this outcome/ solve the painpoint?"
5. CONFIRM: Reflect back WHO + WHAT + WHY. Ask "Is this correct?"

CRITICAL: The LLM converts pain-language to outcome-phrased WHY internally.
User says: "They keep asking the same questions" 
WHY becomes: "So they can find answers without interrupting others"

CONDITIONAL WHY REFINEMENT — Only trigger when WHY is:
- Abstract: "feel confident", "be happier", "work better"
- Restates WHAT: "so we have a checklist", "so the API exists"
- Motivational: "because onboarding matters", "because it's important"

If WHY is already concrete and observable, skip refinement and proceed to WHAT.

CONFIDENCE EXAMPLES:
  HIGH: who="New engineering hires" what="A first-week onboarding checklist" why="So they can start contributing without constant interruptions". Pain-derived, observable outcome, user confirmed.
  LOW:  who="users" what="improve the onboarding experience" why="because onboarding matters". Vague WHO, activity-based WHAT, motivational WHY.
  LOW:  who="New hires" what="A checklist" why="So we can have a checklist". WHY restates WHAT — not valid.
  LOW:  who="The team" what="A dashboard" why="So they feel more confident". Abstract WHY — needs refinement.

CRITICAL: Your role is to facilitate and find the answers by asking the user questions. NEVER suggest answers for the user. NEVER tell the user how to frame the initiative correctly. Elicit the input data iteratively in a back-and-forth conversation — ask ONE question at a time and wait for the user's response before asking the next.

EXAMPLE CONVERSATION (pain-first flow):
  User: "I want to improve our onboarding"
  You: "Who specifically is affected by this?"
  User: "New engineering hires"
  You: "What's currently hard or frustrating for them?"
  User: "They keep asking the same basic questions and feel lost"
  You: "What do you think needs to exist to help with that?"
  User: "A checklist they can follow in their first week"
  You: "To confirm: New engineering hires need a first-week checklist so they can find answers without constantly interrupting others. Correct?"
  User: "Yes"
  → Call frame_initiative_intent with who="New engineering hires", what="A first-week onboarding checklist", why="So they can find answers without constantly interrupting others", confidence="high".

EXAMPLE CONVERSATION (with WHY refinement):
  User: "I want to improve our onboarding"
  You: "Who specifically is affected by this?"
  User: "New engineering hires"
  You: "What's currently hard or frustrating for them?"
  User: "They just don't feel confident"
  You: "What would you see them doing differently if they felt confident?"
  User: "They'd take on small projects without needing hand-holding"
  You: "What do you think needs to exist to help with that?"
  User: "Maybe a checklist or guide for their first week"
  You: "To confirm: New engineering hires need a first-week guide so they can take on small projects independently. Correct?"
  User: "Yes"
  → Call frame_initiative_intent with who="New engineering hires", what="A first-week guide", why="So they can take on small projects independently", confidence="high".

EXAMPLE CONVERSATION (WHY restates WHAT — needs refinement):
  User: "I want a better dashboard"
  You: "Who specifically is affected by this?"
  User: "The product team"
  You: "What's currently hard or frustrating for them?"
  User: "They need a dashboard"
  You: "What would change for the product team if they had this dashboard?"
  User: "They could see project status without asking around"
  You: "What do you think the dashboard needs to show to help with that?"
  User: "Project status and blockers"
  You: "To confirm: The product team needs a dashboard showing project status and blockers so they can check progress without asking around. Correct?"
  User: "Yes"
  → Call frame_initiative_intent with who="The product team", what="A dashboard showing project status and blockers", why="So they can check progress without asking around", confidence="high"."""
```

---

## Change 2: Update GUIDANCE_MISSING_FIELDS

### Find current GUIDANCE_MISSING_FIELDS (around line 85)

Replace with:

```python
GUIDANCE_MISSING_FIELDS = (
    "SHARPEN MODE STILL BINDING. "
    "Ask ONE question about the missing field using pain-first language:\n"
    "- Missing WHO: 'Who specifically is affected by this?'\n"
    "- Missing WHY: 'What's currently hard or frustrating for them?'\n"
    "- Missing WHAT: 'What do you think needs to exist to help with that?'\n"
    "Then stop and wait. Do not explain, suggest, or plan."
)
```

---

## Change 3: Update GUIDANCE_CONFIDENCE_REJECTED

### Find current GUIDANCE_CONFIDENCE_REJECTED (around line 80)

Replace with:

```python
GUIDANCE_CONFIDENCE_REJECTED = (
    "SHARPEN MODE STILL BINDING. "
    "Check which field is vague:\n"
    "- Vague WHO: Ask 'Who specifically is affected?'\n"
    "- Vague/abstract WHY: Ask 'What would you see happening differently if this worked?'\n"
    "- Vague WHAT: Ask 'What concrete thing would exist that doesn't exist today?'\n"
    "Ask ONE question. Then stop and wait. Do not explain, suggest, or plan."
)
```

---

## Verification Checklist

After implementation:

### frame_initiative_intent.py
- [ ] DESCRIPTION includes "ELICITATION ORDER — PAIN-FIRST"
- [ ] DESCRIPTION includes "CONDITIONAL WHY REFINEMENT" section
- [ ] Example conversations show pain-first flow (ask about frustration, not benefit)
- [ ] Example conversations show WHAT phrased as "What do you think needs to exist"
- [ ] Example conversation includes WHY refinement case (abstract → observable)
- [ ] Example conversation includes WHY-restates-WHAT case
- [ ] CONFIDENCE EXAMPLES include abstract WHY as LOW confidence case
- [ ] GUIDANCE_MISSING_FIELDS uses pain-first language
- [ ] GUIDANCE_CONFIDENCE_REJECTED includes conditional WHY refinement trigger

### NO changes needed to:
- [ ] INPUT_SCHEMA (still collects who, what, why, confidence)
- [ ] Pydantic models
- [ ] tool_logic.py (structural validation unchanged)
- [ ] Other tools (they consume the same framing contract)

---

## Unit Tests

No new unit tests required. Existing tests verify:
- Structural validation (who, what, why all required)
- Confidence rejection
- Missing field handling

The elicitation order is prompt engineering — tested via MCP Inspector manual testing, not unit tests.

### Manual Testing (MCP Inspector)

Test these scenarios:

1. **Happy path (clear pain):**
   - User gives clear WHO
   - User gives clear pain → becomes WHY
   - User gives WHAT when asked
   - LLM confirms, calls tool with high confidence

2. **Abstract WHY requiring refinement:**
   - User gives vague pain ("they don't feel good about it")
   - LLM asks "What would you see happening differently?"
   - User gives observable behavior
   - LLM proceeds to WHAT

3. **WHY restates WHAT:**
   - User's pain is "they need X" (restates solution)
   - LLM asks "What would change for them if they had X?"
   - User gives actual outcome
   - LLM proceeds

4. **User gives WHAT first (common):**
   - User: "I want to build a dashboard"
   - LLM should still ask WHO first, then pain, then confirm WHAT

---

## Out of Scope

- Schema changes
- New tools
- tool_logic.py changes
- Other tool files
- Database changes
- Widget changes

---

## Risk Assessment

**Low risk.** This is prompt text only. If the new elicitation doesn't work well:
- Rollback is trivial (revert DESCRIPTION string)
- No data contract changes
- No breaking changes to downstream tools

---

**Document Status:** Ready for Claude Code execution
