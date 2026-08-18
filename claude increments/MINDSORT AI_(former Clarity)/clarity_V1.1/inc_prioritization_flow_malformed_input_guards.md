# Increment: start_prioritization_flow — malformed-input guards (fail-closed + self-correcting)

## Status
Ready to implement. Narrow production correctness fix. Single SHARED handler file
(`mcp_server/clarity/tools/start_prioritization_flow.py`) — fixes both the Claude and OpenAI MindSort
connectors at once, since both dispatch into the same shared registry. It is a shared-handler fix (not
platform-specific) even though this briefing file is filed under the MindSort increment folder.

This supersedes any earlier "three-state contract" draft. The earlier draft proposed treating explicit
`priorities: []` as discovery-only (no persist). That was WRONG: explicit `[]` is a currently-tested,
intended clear-all path (see "What must NOT change"). This increment does not touch it.

## The demonstrated defect (confirmed in production logs 2026-08-18)

The handler currently does `arguments.get("priorities", [])`. A malformed invocation — one that omits
the `priorities` field, or sends priority data under keys not in the schema (the production incident
sent top-level `priority_1` / `priority_1_parent_cluster`) — resolves `priorities` to `[]`.

An empty `priorities` list is NOT neutral downstream: `apply_priorities([])` takes a "clear all
priorities" branch, and the handler persists that cleared board. So a malformed call that was MEANT to
SET a priority instead silently CLEARS any priorities already set and persists the erasure, returning a
"no priorities yet" style response — indistinguishable from a legitimate empty call.

Production evidence: two sequential calls, the first logging `priority_count=0` + `auto_persisted` (the
malformed/empty path persisting a cleared board), the second (well-formed) logging `priority_count=1`.

## Design principle for this fix

Do NOT make the mutation API permissive. Make malformed input FAIL CLOSED with a self-correcting error
the model can act on in one retry. The LLM is in the loop and will re-emit a correct call if the error
tells it exactly what to do — so a sharp, actionable rejection is BETTER than silent normalization, and
keeps the published schema honest.

This is consistent with the tool's EXISTING design: the two provenance gates already in
`start_prioritization_flow` (empty `user_priorities_verbatim`, empty
`user_prioritization_criterion_verbatim`) already do exactly this — reject with a "do not call yet, do
X instead" instruction. This increment extends that same safeguard pattern to the `priorities` payload,
which currently lacks it. It is NOT a new architecture.

Explicitly OUT OF SCOPE (do NOT do any of these here):
- No aliases. Do NOT normalize `priority_1` / `priority_1_parent_cluster` into the canonical shape.
- No generic forgiving parser. No lenient interpretation of unknown shapes. (Guard C is a REJECTION of
  a non-list `priorities`, not a normalization of it — it does not try to coerce a string/object into a
  valid array; it fails closed with a corrective error.)
- No `minItems: 1` schema change. No change to `apply_priorities`, `PriorityInput`, `edit_board`,
  `organize_thoughts`.
- Item-level unknown keys are OUT OF SCOPE (see "Deferred / filed follow-ups"). Guard A is top-level
  only.
- Whether to eventually support a specific malformed shape is a FUTURE, evidence-triggered decision:
  only consider an alias if production telemetry shows the SAME malformed shape recurring DESPITE the
  corrective error. Not now.

## The fix: three malformed-input guards (A → B → C)

Deterministic ordering (do NOT deviate):

    existing provenance gates → malformed-payload guards (A → B → C) → board fetch → validation → mutation → persistence

Preserve the existing provenance gates AND their current ordering exactly. Add the three malformed-input
guards IMMEDIATELY AFTER the existing provenance gates and BEFORE any board retrieval, any call to
`apply_priorities`, or any persistence.

Order WITHIN the malformed set is fixed: A → B → C. The production shape (`priority_1` present AND
`priorities` absent) trips BOTH A and B; A-first means it returns `unknown_top_level_fields` with
`invalid_fields: ["priority_1", "priority_1_parent_cluster"]`. A-first is correct because Guard A's
instruction already tells the model to reissue with the canonical cumulative `priorities` array — which
subsumes the missing-`priorities` correction, so the model still self-corrects in one retry. Do not
leave the intra-set order unspecified: it determines which code and which `invalid_fields` a
multi-fault call returns, and the tests assert that.

Why the malformed guards sit AFTER provenance (not before): a call simultaneously missing
`user_priorities_verbatim` AND missing `priorities` hits whichever gate runs first. The existing
provenance gate returns the "ask which cluster fits the criterion" instruction; the new missing-
`priorities` guard returns the "reissue with canonical array" instruction. If a new guard ran first,
that call would receive a DIFFERENT corrective instruction than it does today — a behavioral change to
the existing provenance path, even though no data is mutated. Both guard sets are pre-side-effect, so
there is no safety reason to run the new ones ahead of the established provenance gates. Provenance
first preserves current behavior exactly.

Guard A — unknown top-level argument key:
- If `arguments` contains ANY key not in the set of allowed top-level keys → return the structured
  malformed-input error (see "Error response"). No fetch, no mutation, no persist.
- The allowed-key set MUST be derived from `INPUT_SCHEMA["properties"]` (i.e.
  `{"user_prioritization_criterion_verbatim", "user_priorities_verbatim", "priorities"}`), NOT a
  hand-written list, so it cannot drift if the schema changes.

Guard B — `priorities` key absent:
- If the `priorities` key is NOT PRESENT in `arguments` → return the structured malformed-input error.
  No fetch, no mutation, no persist.
- CRITICAL DISTINCTION: absent ≠ empty. This guard fires ONLY when the key is missing entirely. An
  explicitly-present `priorities: []` does NOT trigger this guard and flows through to the existing
  behavior unchanged (see "What must NOT change"). Enforce presence via `"priorities" in arguments`,
  never via truthiness (`if not arguments.get("priorities")` would wrongly catch `[]`).

Guard C — `priorities` present but not a list:
- If `priorities` is present but is NOT a `list` (e.g. a string `"Work Projects"` or an object `{...}`)
  → return the structured malformed-input error, code `invalid_priorities_type`,
  `invalid_fields: ["priorities"]`. No fetch, no mutation, no persist.
- This closes the THIRD path to the identical destructive silent-clear: the existing handler lines
  `raw_priorities = arguments.get("priorities", []); if not isinstance(raw_priorities, list): raw_priorities = []`
  coerce a non-list to `[]` → `apply_priorities([])` → clear-all → persist. Same bug, same blast radius;
  neither Guard A (key is present and known) nor Guard B (key is present) catches it.
- Guard C fires ONLY on present-and-not-a-list. `[]` IS a list, so it passes Guard C untouched and flows
  to the existing clear-all behavior — the `absent ≠ empty` distinction extends to `wrong-type ≠
  empty-list`.
- The existing coercion lines STAY (copy-and-adjust; do not delete them). Guard C now returns before
  they are reached for the non-list case, so they are unreachable for that case but harmless. Add a
  single one-line comment above them noting Guard C precedes them, so a future reader does not "clean up"
  what looks like dead code.

Everything else is unchanged. Non-empty `priorities` → existing validate/apply/persist. Explicit
`priorities: []` → existing clear-all behavior. The existing provenance gates → unchanged.

## Error response (the error is part of the control mechanism — design it precisely)

All three guards return an `isError=True` `CallToolResult` whose `structuredContent` carries a
machine-readable, self-correcting payload. Extend the existing provenance-error shape (which currently
carries `assistant_guidance: {action, instruction}`) with additional explicit fields. Concretely the
`structuredContent` must include:

- `success: false`
- `error`: the canonical code for the guard that fired — `"unknown_top_level_fields"` (Guard A),
  `"missing_priorities"` (Guard B), or `"invalid_priorities_type"` (Guard C). Use these exact strings,
  not "e.g." placeholders.
- `state_modified: false`  ← explicit, so the model does NOT tell the user their board changed
- `invalid_fields`: the offending unknown keys (Guard A), or `["priorities"]` (Guard B and Guard C)
- `assistant_guidance`: `{ action, instruction }` following the existing pattern, where:
  - `action`: `"retry_with_canonical_priorities"`
  - `instruction`: prose that states, in order — (1) which fields were invalid/missing, (2) that NO
    existing priorities were modified, and (3) exactly how to retry: reissue with the canonical
    `priorities` array, each item `{name, rank, reason}` for a cluster/subcluster or
    `{item_index, parent_name, rank, reason}` for a thought item, AND that the array must contain the
    FULL CUMULATIVE set (any already-set P1/P2/P3 PLUS the new one) — because the array replaces, it
    does not append. This cumulative reminder is REQUIRED: without it, the model may retry with only
    the new priority and overwrite the others (turning a fixed destructive-clear bug into a
    destructive-overwrite bug).

`content[0].text` for these errors: `"Malformed input: {error_code}"` (parallel to the existing
`"Provenance validation failed: {code}"`).

Telemetry (REQUIRED, not cosmetic): emit one structlog line per malformed-guard hit, mirroring the
existing `start_prioritization_flow.provenance_failed` line. Event name `start_prioritization_flow.malformed_input`,
carrying `error=<code>` and `invalid_fields=[...]`. This is what makes the "is this malformed shape
recurring?" question answerable from logs alone — i.e. the evidence that would later justify (or not)
an alias. Without it the future normalization decision has no data.

The existing `_build_provenance_error` helper only emits `{action, instruction}`. Either extend it to
accept the extra fields, or build these malformed-input errors inline. Do NOT change the existing
provenance-gate call sites that use the two-field version.

### Pre-implementation check — result-contract conformance (do this BEFORE adding the richer fields)
MCP says a structured result should conform to a declared `outputSchema` when one exists. Before adding
`state_modified` / `invalid_fields` to `structuredContent`, verify BOTH:
1. Whether `start_prioritization_flow` declares an `outputSchema` (the shared `ToolDefinition` dataclass
   in `base.py` currently has no output-schema field, which suggests none is declared — but confirm for
   this tool, do not assume). If one exists, the new error payload MUST conform to it; do not silently
   violate the published result contract.
2. Whether any existing test asserts an EXACT `structuredContent` shape (e.g. `== {...}`) for this
   handler's error or success results. Adding fields would break such a test even with no formal schema.
   If found, that is a real conflict to resolve deliberately, not to paper over.
If neither exists, proceed — no conformance issue.

## What must NOT change (currently-tested, intended behavior)

- Explicit `priorities: []` with otherwise-valid args → existing clear-all + persist behavior,
  UNCHANGED. `[]` IS a list, so it passes Guard C untouched; it is present, so it passes Guard B; it
  introduces no unknown key, so it passes Guard A. It reaches the existing clear path exactly as today.
  Two existing tests assert this and MUST still pass unchanged: `test_empty_priorities_clears` and
  `test_clearing_item_preserves_object_structure` (in
  `tests/unit/mcp_clarity/test_start_prioritization_flow.py`). If either needs editing, the fix is
  wrong — stop and flag.
- The existing provenance gates (verbatim-empty checks) → unchanged, and remain FIRST in order.
- Non-empty cumulative flow (P1 → P1+P2 → P1+P2+P3) → unchanged.

## Implementation approach — Copy and Adjust, Never Rewrite

Work only in `mcp_server/clarity/tools/start_prioritization_flow.py`. Add the three guards immediately
after the existing provenance gates in `handle`. Do not rewrite, restructure, reorder, or "improve" any
code not listed above.

## Tests
Separate unit tests from integration tests.

### Unit tests (handler logic, board fetch/persist mocked)
- Missing `priorities` (key absent, both verbatim fields present) → structured error, code
  `missing_priorities`, `state_modified: false`, `invalid_fields: ["priorities"]`; `get_cluster` NOT
  called, `apply_priorities` NOT called, `persist_cluster` NOT called.
- Unknown top-level key present, `priorities` also present and valid → structured error, code
  `unknown_top_level_fields`, the unknown key in `invalid_fields`; all three of `get_cluster` /
  `apply_priorities` / `persist_cluster` NOT called. (Isolates Guard A.)
- Production multi-fault shape: `priority_1` + `priority_1_parent_cluster` present AND `priorities`
  absent → A wins: code `unknown_top_level_fields`,
  `invalid_fields: ["priority_1", "priority_1_parent_cluster"]`. Asserts the A→B precedence explicitly.
- Non-list `priorities` — TWO variants: a string (`"Work Projects"`) and an object (`{...}`) →
  structured error, code `invalid_priorities_type`, `invalid_fields: ["priorities"]`; `get_cluster` /
  `apply_priorities` / `persist_cluster` all NOT called. (Guard C.)
- Explicit `priorities: []` → EXISTING clear behavior, unchanged (guard against over-reach; assert it
  still clears + persists as the existing tests expect — i.e. it passes A/B/C and reaches the clear
  path).
- Non-empty P1 → validates, applies, persists (unchanged).
- Non-empty cumulative P1+P2 → applies both, persists (unchanged).
- For each malformed case (Guards A, B, C) assert all three of `get_cluster`, `apply_priorities`,
  `persist_cluster` were not invoked — not merely that the response looks like an error.

### Integration / acceptance gate — harness (a) in CI + (c) live check post-deploy. NOT (b).
There is no DB-backed integration harness for the clarity board in this suite
(`tests/integration/clarity/` mocks `get_cluster` / `persist_cluster`). Do NOT build real-Postgres
infra for this increment.

(a) CI gate — stateful in-memory fake behind `get_cluster` / `persist_cluster` so the round-trip is
genuinely asserted (persisted board survives across the malformed call), repo-consistent, runs in CI:
1. Persist a board with P1 set (well-formed non-empty invocation).
2. Issue the EXACT malformed invocation class from production — `priorities` absent, top-level
   `priority_1` / `priority_1_parent_cluster` present.
3. Assert the invocation returns a structured error (fail-closed) with `state_modified: false` and code
   `unknown_top_level_fields`.
4. Retrieve the board from the in-memory fake.
5. Assert P1 is still present and unchanged.

(c) Post-deploy live check — the acceptance CONFIRMATION (mocked-green ≠ works-in-production): after
deploy, against `mindsort-mcp.priority-guard.com`, set P1 via the tool, issue the malformed shape,
confirm the tool errors AND P1 still shows on the real board. This is the "seen working on prod" step.

Proves both properties that matter: fail-closed, and no destruction of previously-stored priorities —
in CI (a) and confirmed on prod (c).

## Discriminating-test requirement
The missing-key, unknown-key, multi-fault, and non-list (string + object) tests must FAIL against
current code and PASS after the fix. Against current code: the missing-key and non-list cases default/
coerce to `[]` and can persist a cleared board; the unknown-key cases are silently ignored. State this
discrimination explicitly in the report. The explicit-`[]` test and the non-empty tests must pass BOTH
before and after (they are the no-regression guardrails).

## Before deployment
Read `doc/OPERATIONS_PREDEPLOY.md` and check for additional pre-deploy tasks. MindSort-Claude
(`srv-d90din3sq97s7399nbl0`, `mindsort-mcp.priority-guard.com`, scope `clarity.write`) is
`autoDeploy: yes` — a push to `main` ships it. Confirm the deploy landed by reading the service's own
deploy list, not by inferring from the push. Server-side only (no widget bundle change), so the widget
cache-bust / connector re-add step does not apply. NOTE: the OpenAI MindSort service
(`prioritiy-guard-mindsort-mcp`, `autoDeploy: NO`) shares this handler — making the fix live on OpenAI
is a separate manual deploy.

## Report requirements
- End with the commit hash. Reviews verify against `git show <hash>:<path>`, not the working tree.
- State which tests fail against pre-fix code and pass after, and confirm the explicit-`[]` and
  non-empty tests pass both before and after.
- Report the result of the (c) post-deploy live check against `mindsort-mcp.priority-guard.com` — it is
  part of acceptance, not just the commit hash. Undeployed / not-seen-on-prod is not done.
- List anything not verified.

## Deferred (NOT this increment) — the `[]`-contract decision
Whether `start_prioritization_flow` should stop accepting `[]` as a clear command (making it
commit-only, adding `minItems: 1`, routing all clearing through `edit_board` / `organize_thoughts`
which already own it) is a separate, deliberate contract decision gated on usage telemetry. Do not
address it here.

## Filed follow-ups (separate items, NOT this increment, NOT the `[]`-contract decision)
- Item-level unknown keys: `PriorityInput` (pydantic v2, `extra` defaults to ignore) silently drops a
  stray key INSIDE a priorities item despite the schema's item-level `additionalProperties: false`.
  Guard A is top-level only. Candidate fix: `PriorityInput` → `extra="forbid"`, but that model is shared
  with `edit_board`, so it must be evaluated against `edit_board` usage first. This is a robustness nit,
  NOT a destructive path (a dropped item-level key ignores a field; it does not cause a silent clear),
  so it is correctly out of the destructive-bug increment.
