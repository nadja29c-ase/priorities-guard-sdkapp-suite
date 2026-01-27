Claude Code Briefing: Split frame_initiative_intent into Audience + Outcome
Objective
Split frame_initiative_intent into two sequential tools:

frame_initiative_audience — captures WHO (primary beneficiary)
frame_initiative_outcome — captures PAIN + OBSERVABLE + WHY

This prevents LLM from prefilling WHY while WHO is still being established, and allows educational error recovery for messy user input (multiple stakeholders).
Context
Problem observed in user testing:

User named multiple stakeholders
Zero-info error gave LLM no recovery path
LLM spun for ~1 minute, then fabricated a decision

Solution:

Isolate WHO validation in its own tool
Educational errors guide LLM to ask clarifying questions
Multiple stakeholders are "deferred for now," one is selected as primary

New Flow
frame_initiative_audience (WHO)
    ↓
frame_initiative_outcome (PAIN + OBSERVABLE + WHY)
    ↓
frame_initiative_hypothesis (WHAT)
    ↓
frame_initiative_constraints (CONSTRAINT + full confirmation)

Files to Create
mcp_server/sharpen/tools/frame_initiative_audience.py
New tool. Follow existing patterns from frame_initiative_intent.py.
Purpose: Record ONE primary beneficiary. If user mentions multiple, guide LLM to ask "who benefits first and foremost?"
DESCRIPTION:
pythonDESCRIPTION = """Records WHO benefits from this initiative — ONE primary beneficiary.

CALL PRECONDITIONS — DO NOT CALL unless:
- who: non-empty, ONE specific group (not multiple distinct beneficiaries)

MULTIPLE STAKEHOLDERS: If user mentions multiple distinct beneficiary groups (e.g., "engineers and their managers", "founders and customers"), ask: "Who benefits first and foremost?" Others are noted in deferred_stakeholders but not the focus.

NOT multiple stakeholders (these are valid):
- Compound roles: "Product & Engineering", "Sales and Marketing"
- Slash groups: "Designers/Developers"  
- Single group with qualifier: "senior engineers", "freelancers with ADHD"

Multiple stakeholders = distinct beneficiary groups, not organizational pairings or compound roles.

NO CONFIRMATION YET — proceed to outcome after capturing WHO.

SHARPEN MODE BINDING RULES: When user selects Sharpen, your default behavior is SUSPENDED. You are a Coach now: ask questions to facilitate user's thinking and NEVER tell the user what to do or infer their answers. CRITICAL: Ask ONE question at a time → wait for user's response. Violating this breaks Sharpen.
"""
INPUT_SCHEMA:
pythonINPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "who": {
            "type": "string",
            "description": "ONE primary beneficiary. Who benefits first and foremost? Not multiple distinct audiences. ACCORDING TO THE USER.",
        },
        "deferred_stakeholders": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Other stakeholders user mentioned but are not the primary focus. Optional. These are noted but deferred for now.",
        },
    },
    "required": ["who"],
    "additionalProperties": False,
}
Note: No who_stated_by_user boolean. The string itself is the evidence. Tool validates presence, LLM validates quality.
Guidance Constants:
pythonGUIDANCE_EMPTY_WHO = (
    "SHARPEN MODE STILL BINDING. "
    "Ask: 'Who specifically is supposed to benefit from this?' "
    "Then stop and wait."
)

GUIDANCE_MULTIPLE_STAKEHOLDERS = (
    "SHARPEN MODE STILL BINDING. "
    "Multiple stakeholders detected. Ask: 'Who benefits first and foremost?' "
    "Then stop and wait. Store their answer as WHO, note others in deferred_stakeholders."
)

GUIDANCE_CAPTURED = (
    "SHARPEN MODE STILL BINDING. "
    "Primary beneficiary captured. Proceed to outcome — do NOT ask for confirmation yet.\n"
    "Ask: 'What is the main struggle [WHO] faces? Describe it in their words, not as a solution.'\n"
    "Then stop and wait.\n\n"
    "When user answers → call frame_initiative_outcome with WHO and PAIN."
)
Success output:
python{
    "audience": {
        "who": "...",
        "deferred_stakeholders": [...]  # empty array if none
    },
    "captured": True,
    "assistant_guidance": {
        "action": "PROCEED_TO_OUTCOME",
        "instruction": GUIDANCE_CAPTURED,
    },
}
Error output (standard shape for all educational errors):
pythonreturn mcp_types.CallToolResult(
    content=[mcp_types.TextContent(type="text", text=error_details)],
    structuredContent={
        "error": error_type,
        "assistant_guidance": {
            "action": "ASK_CLARIFYING",
            "instruction": guidance_message,
        },
    },
    isError=True,
)

Files to Modify
mcp_server/sharpen/tools/frame_initiative_intent.py
DO NOT rename file. Change tool registration name only.
Changes:

Change tool name in register_tool() from frame_initiative_intent to frame_initiative_outcome
Remove WHO capture (now comes from audience step)
Add who as required input (from prior step, validate non-empty)
Keep PAIN + OBSERVABLE + WHY capture
Re-activate educational error messages (move from _LEGACY_GUIDANCE to active constants)
Keep _LEGACY_GUIDANCE dict in file (for rollback safety)
Update DESCRIPTION to reflect new scope
Update success guidance: "PROCEED_TO_HYPOTHESIS"

Updated DESCRIPTION:
pythonDESCRIPTION = """Records problem OUTCOME: PAIN + OBSERVABLE + WHY for the primary beneficiary.

CALL PRECONDITIONS — DO NOT CALL unless ALL are true:
- who: from frame_initiative_audience output (non-empty)
- user_pain_verbatim: non-empty, user's exact words
- user_observable_verbatim: non-empty, user's exact words
- why_reframed_from_observable: WHY incorporates observable

VAGUENESS CHECK: If PAIN is abstract ("things are hard") or OBSERVABLE is vague ("it would be better"), push back before calling. Ask for concrete specifics.

NO CONFIRMATION YET — proceed to hypothesis after capturing outcome.

SHARPEN MODE BINDING RULES: When user selects Sharpen, your default behavior is SUSPENDED. You are a Coach now: ask questions to facilitate user's thinking and NEVER tell the user what to do or infer their answers. CRITICAL: Ask ONE question at a time → wait for user's response. Violating this breaks Sharpen.

Sequence: PAIN → OBSERVABLE → reframe WHY → call tool → proceed to hypothesis.
"""
Updated INPUT_SCHEMA:
pythonINPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "who": {
            "type": "string",
            "description": "WHO from frame_initiative_audience. Must match prior step output.",
        },
        "user_pain_verbatim": {
            "type": "string",
            "description": "Copy-paste user's answer exactly as written. Must be non-empty.",
        },
        "user_observable_verbatim": {
            "type": "string",
            "description": "Copy-paste user's answer exactly as written. Must be non-empty. ALWAYS ask the observable question.",
        },
        "why": {
            "type": "string",
            "description": "YOUR reframe combining pain (the value) + observable (the specificity) into an outcome.",
        },
        "why_reframed_from_observable": {
            "type": "boolean",
            "description": "True ONLY if WHY incorporates the observable (not just the raw pain).",
        },
    },
    "required": [
        "who",
        "user_pain_verbatim",
        "user_observable_verbatim",
        "why",
        "why_reframed_from_observable",
    ],
    "additionalProperties": False,
}
Removed: who_stated_by_user (validated in audience step)
Re-activate guidance constants:
Move from _LEGACY_GUIDANCE to active use:
pythonGUIDANCE_MISSING_PRIOR_STEP = (
    "SHARPEN MODE STILL BINDING. "
    "WHO required from frame_initiative_audience. Complete that step first."
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
    "Then store their exact answer in user_observable_verbatim."
)

GUIDANCE_PROVENANCE_FAILED = (
    "SHARPEN MODE STILL BINDING. "
    "Provenance check failed. WHY must incorporate the observable.\n"
    "Reframe the user's observable into an outcome first, then call tool."
)

GUIDANCE_CAPTURED = (
    "SHARPEN MODE STILL BINDING. "
    "Problem outcome captured. Proceed to hypothesis — do NOT ask for confirmation yet.\n"
    "Ask: 'What do you think needs to exist to help with that?'\n"
    "Then stop and wait. Do not suggest solutions.\n\n"
    "When user answers → call frame_initiative_hypothesis with WHO, WHY, and WHAT."
)
Keep _LEGACY_GUIDANCE dict in file but do not delete — needed for potential rollback.

mcp_server/sharpen/tool_logic.py
Add new function:
pythondef validate_initiative_audience(
    who: str | None,
) -> dict[str, Any]:
    """
    Validate WHO for frame_initiative_audience.
    
    Checks:
    - WHO is non-empty
    - WHO does not contain multiple distinct stakeholders
    
    Args:
        who: Primary beneficiary
        
    Returns:
        {"valid": bool, "error_type": str | None, "error_details": str | None}
    """
Use existing _has_multiple_stakeholders() function.
Update _COMPOSITE_AUDIENCES list to include additional patterns:
python_COMPOSITE_AUDIENCES = [
    "sales and marketing",
    "research and development",
    "r&d",
    "product and engineering",
    "product and design",
    "design and engineering",
    "product & engineering",  # ampersand variant
    "design & engineering",
    "ops and support",
    "hr and recruiting",
    "finance and accounting",
    "parents and caregivers",
    "customers and prospects",
]
Update _has_multiple_stakeholders() to handle:

Slash patterns: "Designers/Developers" → valid (same group)
Ampersand: "Product & Engineering" → valid (compound role)

Rename existing functions:

validate_initiative_intent → validate_initiative_outcome
validate_intent_provenance → validate_outcome_provenance

Update validate_initiative_outcome:

Remove WHO validation (just check non-empty as prior step dependency)
Add check: if who empty → error missing_prior_step

Update validate_outcome_provenance:

Remove who_stated_by_user parameter
Keep why_reframed_from_observable, user_pain_verbatim, user_observable_verbatim


mcp_server/sharpen/tools/__init__.py

Add import for frame_initiative_audience
Keep import for frame_initiative_intent (file unchanged, tool name changed internally)


mcp_server/sharpen/tools/frame_initiative_hypothesis.py

Update any reference to frame_initiative_intent in comments/docstrings to frame_initiative_outcome
No schema changes needed


mcp_server/sharpen/tools/frame_initiative_constraints.py

Update any reference to frame_initiative_intent in comments/docstrings
No schema changes needed


Error Response Standard Shape
All educational errors across all tools MUST use this exact shape:
pythonreturn mcp_types.CallToolResult(
    content=[mcp_types.TextContent(type="text", text=error_details)],
    structuredContent={
        "error": error_type,  # e.g., "empty_who", "multiple_stakeholders"
        "failed_checks": [...],  # optional, list of specific checks that failed
        "assistant_guidance": {
            "action": "ASK_CLARIFYING" | "BACKTRACK" | "REFUSE",
            "instruction": guidance_message,
        },
    },
    isError=True,
)
This applies to: frame_initiative_audience, frame_initiative_outcome, and all other Sharpen tools with educational errors.

Validation Logic
validate_initiative_audience:
InputCheckError TypeActionwho empty/whitespaceRejectempty_whoASK_CLARIFYINGwho has multiple distinct stakeholdersRejectmultiple_stakeholdersASK_CLARIFYINGValidAccept——
validate_initiative_outcome:
InputCheckError TypeActionwho emptyRejectmissing_prior_stepBACKTRACKuser_pain_verbatim emptyRejectempty_pain_verbatimASK_CLARIFYINGuser_observable_verbatim emptyRejectempty_observable_verbatimASK_CLARIFYINGwhy_reframed_from_observable falseRejectprovenance_failedASK_CLARIFYINGValidAccept——

Multiple Stakeholder Detection Rules
IS multiple stakeholders (invalid):

"Engineers and their managers" — distinct beneficiary groups
"Founders and customers" — distinct groups
"The team and the client" — distinct groups
"Users, admins, and developers" — comma list of distinct groups

NOT multiple stakeholders (valid):

"Sales and Marketing" — known composite / organizational pairing
"Product & Engineering" — compound role
"Designers/Developers" — slash = interchangeable or same group
"Senior engineers" — single group with qualifier
"Freelancers with ADHD" — single group with qualifier
"Research and Development" — known composite

Update _has_multiple_stakeholders() accordingly:

Check against _COMPOSITE_AUDIENCES first (expanded list)
Treat slash "/" as single group (add this logic)
Then check for "and", "or", comma patterns


Unit Tests
tests/unit/mcp_sharpen/test_frame_initiative_audience.py (new file)
Test validation logic:
pythonclass TestValidateInitiativeAudience:
    def test_empty_who_rejected(self):
    def test_whitespace_only_who_rejected(self):
    def test_single_stakeholder_valid(self):
    def test_multiple_stakeholders_and_pattern_rejected(self):
    def test_multiple_stakeholders_comma_pattern_rejected(self):
    def test_multiple_stakeholders_or_pattern_rejected(self):
    def test_composite_sales_and_marketing_valid(self):
    def test_composite_product_and_engineering_valid(self):
    def test_ampersand_product_engineering_valid(self):
    def test_slash_designers_developers_valid(self):
    def test_qualified_group_valid(self):  # "senior engineers"
    def test_distinct_groups_rejected(self):  # "founders and customers"
Test handler:
pythonclass TestFrameInitiativeAudienceHandler:
    async def test_valid_input_returns_captured(self):
    async def test_valid_with_deferred_stakeholders(self):
    async def test_empty_who_returns_educational_error(self):
    async def test_multiple_stakeholders_returns_educational_error(self):
    async def test_error_response_has_standard_shape(self):
tests/unit/mcp_sharpen/test_frame_initiative_outcome.py (rename + update)

Rename from test_frame_initiative_intent.py
Update all imports: frame_initiative_intent → frame_initiative_outcome
Update function names: validate_initiative_intent → validate_initiative_outcome
Remove WHO validation tests (moved to audience)
Add test: empty who → missing_prior_step error
Keep PAIN/OBSERVABLE/WHY tests
Update tool name in handler tests


Manual Validation (MCP Inspector)

Multiple stakeholders flow:

User: "This is for engineers and their managers"
Expected: LLM asks "Who benefits first and foremost?"
User: "Engineers"
Expected: frame_initiative_audience called with who: "Engineers", deferred_stakeholders: ["managers"]


Compound role (valid):

User: "Product & Engineering team"
Expected: frame_initiative_audience called immediately, no clarification


Slash group (valid):

User: "Designers/Developers"
Expected: frame_initiative_audience called immediately, no clarification


Full flow:

audience → outcome → hypothesis → constraints
Verify WHO propagates correctly through all steps
Verify no "Correct?" prompts until constraints step




Acceptance Criteria

 frame_initiative_audience.py exists with educational error messages
 Tool name changed from frame_initiative_intent to frame_initiative_outcome (file unchanged)
 tool_logic.py has validate_initiative_audience function
 _has_multiple_stakeholders() handles slash and ampersand patterns
 _COMPOSITE_AUDIENCES list expanded
 Multiple stakeholder detection returns educational error with guidance
 deferred_stakeholders captured in audience output
 WHO passed from audience to outcome as required input
 Outcome tool validates non-empty WHO (missing_prior_step error)
 Educational errors use standard shape across all tools
 _LEGACY_GUIDANCE dict preserved (not deleted)
 All existing tests updated and passing
 New audience tests passing
 Tool registration updated in __init__.py

What NOT to change

Filename frame_initiative_intent.py (keep as-is)
frame_initiative_hypothesis.py schema
frame_initiative_constraints.py schema
Later tools (identify_e2e_deliverables, select_focus_deliverable, commit_week_deliverable)
_LEGACY_GUIDANCE dict — preserve for rollback
