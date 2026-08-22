Increment Briefing — Case-insensitive container-name matching (MindSort, shared) — v4
Objective & nature of change

Unchanged from v3: align container resolution with established strip().lower() semantics; not a production bug but a semantics change; current priority-path correctness is coupled to current case-sensitivity (canonical-name invariant), which the fix must preserve. Both handlers have this coupling, via different internal structures — do not assume start_prioritization_flow mirrors edit_board's resolver shape (it doesn't; see below).

Fixed requirements
Normalize with existing strip().lower(). No casefold().
Operation-aware, fail-closed resolution: normalize, resolve within the operation's candidate domain, 0→not found / 1→resolve / >1→ambiguity, never first-match-wins.
Carry canonical names forward: after resolution, use the resolved container's stored name for anything flowing into priority application; matchers downstream stay exact. Applies in both handlers (mechanism differs per handler — see each).
edit_board.py (v3 stands — this half was correct)
Sites: _find_cluster, _find_subcluster (+parent guard), _op_delete_cluster loop, _op_delete_subcluster guard+loop, _find_thought_item_by_text parent resolution, _check_ambiguous_name, rename collision checks (both, incl. existing is not cluster identity guard).
Requirement 3: _op_set_priority builds PriorityInput from resolved container's stored name — both container branch (~:451-456) and item branch (~:435-444, reuse resolved_parent from _find_thought_item_by_text). apply_priorities unchanged.
Ambiguity extension (Q3): _check_ambiguous_name extended to _op_set_priority and _op_clear_priority on the target_name (both-types) branch only. _op_clear_priority needs the ambiguity check but NOT canonicalization (mutates via _find_container directly).
start_prioritization_flow.py (REBUILT — v3's site list was structurally wrong)

v3 error: it listed _find_container_by_name (:200/:206) as the fix site. Measured: normalizing only that leaves the screenshot case producing the identical error. _find_container_by_name has one call site (:255, item-target parent lookup) and is NOT on the container-target path that raises the reported error.

The screenshot error raises at :274 (_validate_priorities, container-target branch), via raw set membership against sets built by _find_all_names (:158-182) from raw stored names. That's the real path.

Corrected sites (all normalized together):

_find_all_names :158-182 — build normalized → stored[] maps (not raw name sets). Root of the fix; see Requirement 3 shape (i) below.
:236 ambiguity intersection, :238/:252 ambiguity membership — compute over normalized keys so "X"/"x" are detected.
:269/:271 container-target membership (the screenshot), :270/:272 accumulation — resolve/accumulate via normalized keys, store canonical.
:200/:206 _find_container_by_name — still normalize (live for item-target parents), but know it is not the reported path.

Q5 — parent+child conflict guard (:280-282) FAILS OPEN — separate call-out. This guard forbids prioritizing a cluster and its own subcluster together; it reads the raw names accumulated at :270/:272. Unlike every other failure mode here (fail-closed: ambiguity→error, zero mutation), leaving this un-normalized fails open — a case-variant input silently stops detecting the conflict and the board accepts a forbidden state with no error. Normalize in lockstep with :270/:272. Required test: parent+child conflict is still caught under case-variant input (assert error + zero mutation). This is the one site where the risk is a silent weakening of a safety guard, not a visible error — treat with corresponding care.

Q6 — canonicalization shape (i): _find_all_names returns normalized → stored[] maps. _validate_priorities resolves each p.name/p.parent_name against them, enforcing 0→not found / 1→canonicalize / >1→ambiguity error, and writes the single stored name back onto each PriorityInput before :542 _apply_priorities. Canonicalization and ambiguity detection are the same operation over the normalized→stored map. This keeps "resolve once, canonicalize at the boundary" as one invariant across both handlers; do NOT add a second canonicalization pass (shape (ii) — rejected: second traversal, second place to drift). _apply_priorities/apply_priorities stay exact-matchers, unchanged.

Approach — one shared normalizer

Single shared helper imported by both handlers (fallback: duplicate + parity test). The normalized→stored map-build in start_prioritization_flow and the resolver normalization in edit_board both call it.

Candidate-domain rule, ongoing-condition (Q2), do-not-include

Unchanged from v3: domain-scoped ambiguity (clusters-only / subclusters-under-parent / both-types), not global. Case-variant duplicates are ongoing (organize_thoughts has no dedupe), not legacy; organize_thoughts creation semantics out of scope (recorded choice). No raw-name logging; no meta changes; no casefold; no global resolver; not the P2/P1 bug.

Tests

edit_board (v3 tests stand): resolution, domain-scoped ambiguity, three rename mechanisms (+zero-mutation), Q3 behavior change, canonical-name regression (Test 3 inverted), zero-mutation/no-persist on all ambiguity+collision.

start_prioritization_flow (NEW — the gap that would ship untested):

Canonical-name regression (sibling of edit_board's): case-variant container input → reaches _apply_priorities with canonical name → priority actually set and persisted (fails-before/passes-after; this is the screenshot path).
container-target :274 path: case-variant name resolves (no longer errors), correct priority set.
ambiguity: cluster "X" + subcluster "x", both-types name → ambiguity error, zero mutation.
Q5 fail-open guard: parent + own-subcluster with case-variant input → conflict still caught, error, zero mutation.
item-target parent (:200/:206 path): case-variant parent resolves.

Shared-helper parity (if duplicated): identical normalization across handlers.
Integration: screenshot repro on both MindSort-Claude and MindSort-OpenAI → priority applied and persisted.

Blast radius / deploy

Shared mcp_server/clarity/tools/ + board_utils.py → both MindSort surfaces, one shared path (no _dupl). Test both. Read OPERATIONS_PREDEPLOY.md. Live-product care.

Report back

Commit hash; both handlers' corrected site lists routed through the one normalizer; start_prioritization_flow fix verified against the :274 path (not just :200/:206); Q5 guard normalized + still-caught test; Q6 shape-(i) canonical-forward at _validate_priorities; both canonical-name regression tests (edit_board + start_prioritization_flow) fail-before/pass-after; domain-scoped >1; zero-mutation assertions; what was NOT verified.

That's v4. The substantive corrections over v3: the entire start_prioritization_flow site list rebuilt on the measured error path (:274/_validate_priorities/_find_all_names, not :200/:206), Q5 pulled out as a fail-open safety-guard inversion with its own still-caught test, Q6 resolved to shape (i) (unified normalized→stored map doing both canonicalization and ambiguity), and the sibling regression test that pins the screenshot path.

The lesson I'll carry, stated plainly because it's now happened twice in this fix: I keep building the start_prioritization_flow half by analogy to edit_board instead of reading start_prioritization_flow's actual structure. Q4 is that error caught by measurement — v3 would have shipped a "fix" that doesn't touch the reported path, with a green test suite that never exercised it. The discipline that caught it is the one that should have written it: don't infer the second handler's structure from the first; read it, and measure that the fix hits the line that actually raises the error. Claude Code ran BEFORE/AFTER on the real input and got identical errors — that's the artifact that proves v3 incomplete, the same way Test 3 proved the raw-PriorityInput no-op. Ready for Claude Code, and this time the report-back explicitly requires verifying against the :274 path, so the structural assumption can't hide again.
---

# AMENDMENT — Q7 folded in (v4 + Q7). Nadja's text, transcribed by Claude Code 2026-08-22.

## Requirement 2 (amended) — the >1 rule fires on exact duplicates too, and is coupled to Requirement 3

The `>1`-eligible-matches→ambiguity rule applies identically to **case variants** ("X"/"x") and
**exact duplicates** ("Tasks"/"Tasks") — both are >1 entries under one normalized key in the
`normalized → stored[]` map. This is why the map value must be a collection; a scalar map would
have hidden the exact-duplicate case just as it would have hidden the case-variant one.
Case-insensitivity and duplicate-detection are the same operation over the same map, and
Requirement 3's canonicalization rides on top of it.

## STATED INVARIANT — do not decouple

Requirement 3's canonicalization is sound **only because** the >1 rule guarantees exactly one
eligible match. The resolved stored name is a unique handle only under that guarantee.

`apply_priorities` matches **board-wide and fans out to every match**:
  - `board_utils.py:177`  every matching cluster
  - `board_utils.py:219`  every matching subcluster
  - `board_utils.py:237`  items, keyed `(parent_name, idx)`

If the >1 rule is ever relaxed to first-match-wins, canonical names silently resume fanning out.
**The >1 rule and canonical-forward move together; neither is safe alone.** State this at both
handlers, in comments at the code sites — this is the same hidden-coupling class as Q1 (a
correctness property silently depending on another property a future edit could remove without
realising what it breaks), and the fix is to name it so it cannot hide.

## Deliberate behaviour change — the THIRD (with Q3's ambiguity extension and normalization itself)

Exact-duplicate container names now → **ambiguity error**, where today one `PriorityInput`
silently sets the priority on ALL matches. Intended: it is the same silent-mispick class the
increment exists to close, and arguably worse than the case-variant case — one stated priority
landing on two containers is a more surprising violation of user intent than a case mismatch.

It also removes the precondition for a Q5 guard failure for free: `subcluster_to_parent[sub_name]
= name` (`start_prioritization_flow.py:180`) is last-wins, so on duplicate-subcluster-name boards
the parent+child guard today checks only the LAST parent. The >1 rule makes that broken state
unresolvable rather than mis-guarded.

Same discipline as Q3: it rejects calls that currently succeed, on boards with **no case variance
whatsoever**, so it must be named as a deliberate behaviour change and tested as one.

## Required test

Two subclusters named "Tasks" (no case variance) under different parents +
`PriorityInput(name="Tasks")` → **ambiguity error, zero mutation**. Docstring must note that this
previously set P1 on BOTH.

## Scope of the >1 rule, now fully stated

Fires on: case variants ("X"/"x") AND exact duplicates ("Tasks"/"Tasks"). Both are "more than one
eligible match after normalization" — the normalized key maps to two stored entries either way.
