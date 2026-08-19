# Increment: MindSort-Claude tool-advertisement allowlist (fix R7a diagnostic-tool leak)

**Product:** MindSort — **Claude connector only.** Claude/Anthropic SDK app.
**Type:** Server-side tool-listing logic. **No widget change** → no `WIDGET_VERSION` bump, no cache-bust (see §6). Do not add one.
**Blast radius:** **MindSort-Claude only.** Do NOT modify shared `mcp_server/clarity/` code, the shared `TOOL_REGISTRY`, `TOOL_SCOPES` for OpenAI, or anything on the OpenAI surface. The whole point of this fix location is that it touches nothing OpenAI.
**Scope discipline:** Copy and Adjust, Never Rewrite. One new constant + one filter in one file, plus tests.

---

## 1. Problem (verified against source; git-confirmed provenance)

`list_tools_for_claude()` in `mcp_server/mindsort_claude/tools_list_dupl.py` iterates the entire shared `TOOL_REGISTRY` with **no visibility filter** (its own docstring says "No visibility filter"). The shared registry contains 7 tools, one of which — `_diagnostic_tiny_widget` — is an **OpenAI-only** diagnostic (inc_91, commit 1bbd16c, 2026-07-05; `_meta` is pure `openai/*`; built for OpenAI widget-render isolation). It self-registers into the shared registry at import time (`clarity/tools/__init__.py` → `from . import diagnostic_widget`), so MindSort-Claude advertises it even though MindSort-Claude never opted in.

Result: Claude is shown a 7th tool whose description opens *"INTERNAL DIAGNOSTIC TOOL - DO NOT USE IN NORMAL CONVERSATION"* and which **cannot succeed** — it is absent from Claude's `TOOL_SCOPES`, and `enforce_tool_scope()` fails closed on unknown tools (raises `InsufficientScopeError` → 403) before the handler runs.

**Compliance impact:** breaks **R7a** (a tool that returns only a generic error fails review) and makes **S12** (portal attestation that every advertised tool was exercised) untrue as written — one advertised tool cannot be exercised successfully.

**Root cause (the real defect, bigger than the one tool):** there is **no contract defining what MindSort-Claude advertises.** Advertisement is currently derived implicitly from "whatever is in the shared registry." Adding a tool to shared code for *either* platform silently advertises it on the *other*. This increment establishes the missing contract.

---

## 2. The fix — an explicit advertisement allowlist

Introduce, in `mcp_server/mindsort_claude/tools_list_dupl.py`, an explicit constant naming exactly the tools MindSort-Claude advertises:

- `CLAUDE_ADVERTISED_TOOLS` = the **6 real MindSort tools**: `organize_thoughts`, `load_saved_board`, `read_board_before_editing`, `start_prioritization_flow`, `edit_board`, `delete_my_data`.
- `list_tools_for_claude()` advertises **only** tools whose name is in `CLAUDE_ADVERTISED_TOOLS`. Everything else in the shared registry is ignored for Claude advertisement.

**Why an explicit allowlist and not an exclusion set or a `registry ∩ TOOL_SCOPES` intersection** (record this reasoning; it is the point of the increment):
- **Failure asymmetry.** With an allowlist, the failure mode of a mistake is *omission* — an intended tool doesn't appear. Loud, immediate, caught in the first test conversation. With an intersection/exclusion, the failure mode is *over-exposure* — a tool appears that shouldn't. That is the failure that already happened here and stayed invisible for six weeks until a compliance audit found it. The allowlist makes the dangerous direction structurally impossible and the harmless direction obvious.
- **Advertisement and authorization are distinct concerns.** `TOOL_SCOPES` answers "may this authenticated caller invoke it?"; `CLAUDE_ADVERTISED_TOOLS` answers "should Claude know this tool exists?" They must not be conflated merely to avoid maintaining a set. The missing contract is exactly this list; give it a name rather than deriving it indirectly.
- **Honest cost, stated:** adding a future Claude tool now requires two edits — `TOOL_SCOPES` (authorize) and `CLAUDE_ADVERTISED_TOOLS` (advertise). That price is paid by the person adding the tool, who is already in that file — not by a future auditor.

Do NOT use a naming convention (e.g. exclude `_`-prefixed names). Prefix filtering is brittle and semantic-by-accident.

---

## 3. Test invariant (CI test, NOT a startup assert)

Add a test asserting:
- `CLAUDE_ADVERTISED_TOOLS ⊆ TOOL_REGISTRY` — nothing advertised that doesn't exist.
- `CLAUDE_ADVERTISED_TOOLS ⊆ TOOL_SCOPES` — nothing advertised that isn't authorized.

**Deliberately one-directional — do NOT assert equality or the reverse subset.** OpenAI-only tools (e.g. `_diagnostic_tiny_widget`) legitimately sit in the shared registry unadvertised on Claude; that is exactly the state being encoded. Add a comment saying so, so nobody later "fixes" it into a two-way assert.

**Not a startup assert.** A scope-map/registry drift is inert (the dispatcher rejects unknown tools before scope enforcement is reached), so a startup fail-fast would convert harmless metadata drift into a production outage — a guard stricter than the safety requirement. Phase 0 surfaced no unsafe-to-run mismatch; the CI test is the correct instrument.

---

## 4. Tests (separate unit from integration)

**Discriminating test (the load-bearing one — must fail before, pass after):**
- Assert `_diagnostic_tiny_widget` is **NOT** in `list_tools_for_claude()`'s output. This test **must fail against current code** (the tool leaks today) and **pass after** the allowlist lands. That fail-before/pass-after property is the proof the fix works — no need to annotate hypothetical evasions.

**Unit:**
- `CLAUDE_ADVERTISED_TOOLS` contains exactly the 6 named tools (assert exact membership, not just count).
- The two subset invariants in §3 hold.

**Integration:**
- `list_tools_for_claude()` returns exactly the 6 real tools and does not include `_diagnostic_tiny_widget`.
- **The OpenAI `list_tools` test passes UNCHANGED** — regression evidence that the OpenAI advertisement surface remains unchanged. (This is a regression property, not a proof of zero blast radius; the stronger evidence for that is §7.5 — no shared/OpenAI file was modified.) If this test needs editing, the change touched OpenAI and is out of scope; stop.

Do not weaken coverage to make the fix pass. **One existing test must be rewritten, not preserved as-is:** `tests/unit/mcp_claude_mindsort/test_scaffold.py::test_list_tools_returns_all_registered` currently asserts `{t.name for t in tools} == set(TOOL_REGISTRY.keys())` — i.e. it *encodes the present defect* ("advertise everything shared") as intended behaviour, docstring included. It cannot coexist with §2. **Rewrite it** to assert `{t.name for t in tools} == CLAUDE_ADVERTISED_TOOLS`, and correct its docstring (the phrase "no visibility filter" becomes false and is how someone later reverts this fix). This is a *strengthening*: equality against a named 6-element constant is a tighter invariant than equality against whatever shared code happens to contain, and it is the one assertion that catches the allowlist's own failure mode (a real tool silently dropped from advertisement) which the §3 subset invariants do not. Do **not** delete it (deletion loses the set-equality guard). Do not weaken or delete any *other* existing test; do not require per-test "what bug would still pass it" annotations — demonstrate discrimination via fail-before/pass-after and regression coverage instead.

---

## 5. Out of scope — log, do not fix here
- **`save_board` scope-map keys** (`clarity/config.py`, `mindsort_claude/config.py`): the keys appear to be obsolete tombstones from the auto-persist migration (`save_board.py` deleted in f7134ec) and are **not required to resolve this defect**. Under this allowlist fix, advertisement no longer derives from the scope map, so these keys have no bearing on it. Cleanup is **separate** — it touches `clarity/config.py` (**OpenAI blast radius**), so it belongs in its own commit, not this one.
- **`_diagnostic_tiny_widget` has `[]` required-scopes on OpenAI** (`clarity/config.py:300`): mechanically this means "no scope gate; any authenticated user may call it" (`check_scopes` returns True vacuously for `[]`). It is `read_only_hint=True` and side-effect-free. **This is a deliberate, reviewed, test-pinned exemption, not an open question** — `tests/unit/mcp_clarity/test_auth.py` carries `ALLOWED_EMPTY_SCOPES = {"_diagnostic_tiny_widget"}`. Nothing to decide and nothing to fix here; do not re-litigate it and do not touch it.

---

## 6. Build / deploy / verify
- **No widget bytes change.** This is server-side tool-listing logic only. Do **NOT** bump `WIDGET_VERSION` or do any cache-bust — those are for widget-HTML changes. Adding one here would be cargo-cult.
- Read `doc/OPERATIONS_PREDEPLOY.md` before deploying and check for additional pre-deploy tasks.
- **`committed ≠ live`.** After deploy, verify on the real Claude host (`mindsort-mcp.priority-guard.com`):
  - live `tools/list` contains exactly the intended six tools;
  - `_diagnostic_tiny_widget` is absent;
  - one representative safe/read-only tool call succeeds (e.g. `read_board_before_editing`) — this exercises the changed advertisement→dispatch path without creating unnecessary production writes;
  - rely on the automated regression tests for the remaining handlers (a single successful call does not, and need not, confirm all six handlers function).

---

## 7. Report requirements
1. **Commit hash** for the reviewed round (reviews verify against `git show <hash>:<path>`).
2. The **diff** of `tools_list_dupl.py` (the new constant + the filter).
3. Confirmation the discriminating test **failed before** and **passes after**.
4. Unit + integration results, including the unchanged OpenAI `list_tools` test.
5. Explicit confirmation **no `clarity/` file and no OpenAI-surface file was modified**.
6. An explicit **"what I did NOT verify"** list (e.g. live prod check if not yet deployed).
