BRIEFING — inc_92: Fix malformed ToolAnnotations serialization in Clarity (MindSort-OpenAI) list_tools
Scope: MindSort/Clarity ONLY (mcp_server/clarity/). This is a ChatGPT-SDK app. Do NOT touch mcp_server/priority_guardian/ (PG) or mcp_server/mindsort_claude/ (Claude platform). This is a correctness fix on an on-hold dev-mode app — NOT a PG/production emergency.
Problem (verified in production logs 2026-07-05 + source): Clarity's list_tools builds tool annotations as a raw dict and assigns it to the typed tool.annotations field, and also embeds it in _meta["annotations"]. This triggers a Pydantic serialization warning on every tools/list: PydanticSerializationUnexpectedValue(Expected 'ToolAnnotations' ... input_type=dict). Malformed tools/list output affects the whole connector before any rendering begins. PG's list_tools does NOT have this bug — it uses a typed mcp_types.ToolAnnotations(...) object and does not embed annotations in _meta. PG is the correct reference pattern.
This is a correctness fix, NOT a claimed root-cause fix. Do not assume this resolves MindSort's tool-invocation/render intermittency. Frame it as: confirmed malformed descriptor output → possible contributor to ChatGPT instability → mandatory correctness fix. Whether it changes observed behavior is to be observed after, not asserted.
Reference (correct source): mcp_server/priority_guardian/tools/__init__.py list_tools() — the typed-ToolAnnotations block is the pattern to mirror.
CRITICAL divergence — do NOT blind-copy PG: Clarity's ToolDefinition (mcp_server/clarity/tools/base.py) does NOT have a title field; PG's does. PG passes title=tool_def.title — copying that verbatim into Clarity will raise AttributeError. The Clarity fix must construct ToolAnnotations without title (using only the fields Clarity's ToolDefinition actually has: read_only_hint, destructive_hint, open_world_hint). Do not add a title field to Clarity's ToolDefinition in this increment — that's out of scope; omit title from the annotations.
Canonical guidance — READ FRESH before implementing (ChatGPT SDK app):

ADR_MCP Server implementation standard.md — descriptor/annotation construction standard.
Openai_uiux.md — must confirm the correct LOCATION for annotations: typed Tool.annotations field vs _meta["annotations"]. PG (approved, published) uses the typed field only and does NOT put annotations in _meta — strong prior that typed-field-only is correct. Confirm against the doc; if the doc contradicts PG's approved pattern, STOP and flag the mismatch (living-artifact rule).
Compliance_Master.md — annotations are a documented submission/rejection surface; confirm the fix aligns.
"Priority Guard App Suite: Shared Backend — Architecture…" — confirm no shared-infra impact (there is none expected; list_tools is per-app).
ALL OPERATIONS...md; read OPERATIONS_PREDEPLOY.md before committing/deploying.
If any doc is unreachable, unreadable, or mismatches the code, flag and suggest a fix.

Required fix (requirements, not implementation):

Replace the raw-dict annotations assigned to tool.annotations with a typed mcp_types.ToolAnnotations(...) object, constructed from Clarity's available ToolDefinition fields (no title).
Remove annotations from _meta unless Openai_uiux.md/Compliance_Master.md explicitly require it there. Default expectation, per PG's approved pattern: annotations live on the typed field only, not in _meta. If canon says otherwise, follow canon and note it.
Preserve everything else in list_tools exactly — the securitySchemes logic (oauth2/empty-scopes/noauth), ui visibility, outputTemplate, invocation messages. Copy-and-adjust: change only the annotations construction, nothing else.

Must NOT regress (verify preserved):

The noauth→oauth2 descriptor fix from inc_91: empty required_scopes list must still map to {"type": "oauth2", "scopes": []}, and only required_scopes is None maps to noauth. The diagnostic tool must still emit oauth2 with empty scopes.
The diagnostic tool (_diagnostic_tiny_widget) must still run with an authenticated token (its TOOL_SCOPES entry [] + fail-closed enforcement unchanged).

Unit tests:

list_tools for Clarity emits tool.annotations as a typed mcp_types.ToolAnnotations instance (not a dict) for every tool.
Annotations carry correct readOnlyHint/destructiveHint/openWorldHint values from each ToolDefinition.
_meta does NOT contain an annotations key (unless canon required it — assert whichever is correct).
The diagnostic tool's descriptor still shows oauth2 with empty scopes.
State, per test, what bug would still pass it.

Integration tests (separate from unit):

Run Clarity tools/list against a running dev server; assert no Pydantic serialization warning is emitted (this is the production symptom — the integration test must actually catch it, e.g. capture warnings).
Confirm the diagnostic tool still executes with a valid authenticated token (auth path unregressed).

Production-readiness (context: small correctness increment on an on-hold dev SDK app):

Scalability: none affected — list_tools construction only, no new per-request cost.
GDPR/data-retention: none — no user data touched, no logging change.
Under load/latency: negligible; typed-object construction is not costlier than dict.

Deployment discipline: ChatGPT-SDK MCP server change. Read OPERATIONS_PREDEPLOY.md before committing; git stash before any working-tree overwrite. Reviewed round ends with a commit hash; review verifies against git show <hash>:<path>.
What NOT to do: No changes to PG or mindsort_claude. No adding title to Clarity's ToolDefinition. No restructuring list_tools beyond the annotations construction. No claiming this fixes the invocation/render intermittency — observe after, don't assert.
Deliverable: commit hash; confirmation the Pydantic warning is gone from tools/list; confirmation diagnostic tool still authenticates and emits oauth2/empty-scopes; explicit "what I did NOT verify" list.

Flags per your rules:

Living-artifact / divergence flag: Clarity and PG list_tools have diverged — PG was fixed to typed ToolAnnotations (+ title), Clarity was not. Earlier this thread these were reported "structurally identical copy-paste." They are not, on the annotations path. This is exactly the undeclared-duplication risk flagged before: two hand-maintained copies drifting silently. Worth deciding, separately, whether these list_tools implementations should be consolidated or explicitly _dupl-marked — but not in this increment.
What I verified this session (working tree): Clarity list_tools uses raw-dict annotations on the typed field + in _meta (the warning source); PG uses typed ToolAnnotations(...) with title, no _meta.annotations (correct); Clarity's ToolDefinition has NO title field (so PG's block cannot be copied verbatim).
What I did NOT verify: Openai_uiux.md/Compliance_Master.md on the correct annotations location (typed field vs _meta) — inferring from PG's approved pattern, NOT confirmed against canon this session; the briefing requires Claude Code to confirm. The inc_91 Bug-3 test file (still unread). Whether removing _meta["annotations"] has any downstream consumer in Clarity's own code (Claude Code should grep for _meta["annotations"]/annotations readers before removing). None of this is confirmed against a commit hash — working-tree state only.

One strategic line, per your rules, kept short: this is a clean, correct, low-risk fix and worth doing — but it's on MindSort, which is on hold. It does not touch your published revenue apps. Fix it because malformed output is malformed output, then return the bulk of your hours to what actually monetizes. Don't let "we found a real bug at last" reframe an on-hold-app correctness fix as the main event.you agree? if so adjust the briefing:Yes, I agree with the direction.
Verdict: briefing is correct, production-ready for this small MindSort-only fix, and aligned with OpenAI hard requirements in intent.
One important adjustment before handing it to Claude Code:Do not say "remove _meta.annotations" as default.
Say: "Match PG's approved descriptor shape unless OpenAI docs explicitly require _meta.annotations."You already mostly say that, but make it stricter. The safe reference is PG’s approved pattern:typed ToolAnnotations on tool.annotations
no _meta.annotationsAlso add one required grep:grep Clarity code/tests for _meta["annotations"] or metadata annotations consumers before removing it.If no consumer exists, remove it. If a consumer exists, stop and report.
Everything else is strong:verified Clarity has no titleavoids blind PG copypreserves oauth2 empty-scope descriptor fixkeeps PG and Claude untouchedframes this as correctness fix, not root-cause claimrequires warning disappearance as acceptance 
Proceed with those two wording tweaks.Show moreAgreed on both tweaks — they tighten a genuinely soft spot. "Remove _meta.annotations as default" put the burden on Claude Code to justify keeping the correct thing, when it should be the reverse: PG's approved shape is the reference, and any deviation (including removal) must be affirmatively justified against canon + a consumer check. And the grep is exactly the "verify before deleting" your rules require — removing a field without confirming nothing reads it is the kind of silent breakage that passes tests and fails in production. Both accepted.
Two changed sections of the briefing:
Replace the "Required fix" bullet on _meta with:


Annotations location: match PG's approved descriptor shape — typed mcp_types.ToolAnnotations on tool.annotations, and no annotations key in _meta. PG is published/approved, so this shape is empirically validated. Do NOT remove _meta["annotations"] merely because PG omits it — remove it only after BOTH conditions hold: (a) Openai_uiux.md/Compliance_Master.md do not require annotations in _meta, AND (b) the consumer grep below finds no reader. If either fails, keep it and report.


Add to "Required fix" as a new prerequisite step:


Consumer check before removal (required): grep Clarity's code AND tests for any reader of _meta["annotations"] / metadata.*annotations (e.g. handlers/, server.py, tool_logic.py, tests/). If NO consumer exists AND canon doesn't require it → remove _meta["annotations"]. If ANY consumer exists → STOP, do not remove, report the consumer and its purpose. Do not delete a field that something reads.


Everything else in the briefing stands as written — the title omission (verified Clarity's ToolDefinition lacks it), the no-blind-PG-copy instruction, preserving the oauth2/empty-scopes descriptor fix, PG and mindsort_claude untouched, correctness-not-root-cause framing, warning-disappearance as acceptance, canon reads up front, OPERATIONS_PREDEPLOY before commit, commit hash for review.
The briefing is ready to hand to Claude Code with those two edits folded in.
One closing note per your rules, and I'll keep it to the point: this is a correct, low-risk, well-scoped fix — but it's on MindSort, which is on hold. The value it delivers is a clean manifest on a parked app and possibly some improvement to MindSort's intermittency, unproven until observed. It does not advance Unpack v2.0 or Priority Guardian V1.0 — your published, revenue products. Fix it because malformed output shouldn't ship, then be deliberate: the thread has spent four sessions largely inside MindSort's dev-mode problems. The manifest fix is a fine stopping point to close the MindSort thread and redirect hours to what monetizes. When inc_92 comes back with a hash, I'll review it adversarially against git show — and that's a good moment to consciously decide whether the next increment serves a shipped product or the on-hold one.