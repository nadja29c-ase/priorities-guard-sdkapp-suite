# Increment: MindSort-Claude — surface model-needed board data into `content`

**App:** MindSort AI for Claude (`mcp_server/mindsort_claude/`). Anthropic MCP connector.
**Type:** Bug fix — response adapter. Submission-blocking (a headline capability, board editing, is unusable on Claude).
**Touches:** `mcp_server/mindsort_claude/` only. Does NOT touch `mcp_server/clarity/` (OpenAI MindSort, in review) or the backend.

---

## Canonical guidance (read before implementing)
Per project rules, this increment is governed by the Claude-app canonical artifacts:
1. `doc/Claude_Compliance/claude_connectors_compliance_master.md`
2. `doc/Claude_Compliance/structural_guideline_claude_vs_openai.md` (PG — the sibling that already solved this)
3. `doc/Claude_Compliance/structural_guideline_claude_vs_openai_MindSortAI.md` (MindSort — **stale on this exact point; see "Artifact fixes required"**)

Before committing anything: read `OPERATIONS_PREDEPLOY.md` and follow it.

---

## Problem (confirmed in production + source)
On Claude, the model reads **only the `content` channel**; `structuredContent` goes exclusively to the widget. This is the inverse of ChatGPT (which reads `structuredContent`). Documented in the PG structural guideline under "Platform Divergence: Model-Visible Channel" (confirmed 2026-07-05).

MindSort-Claude's response adapter (`mcp_server/mindsort_claude/response_adapter_dupl.py`) moves `assistant_guidance` into `content` but **does not surface any board data into `content`.** The board (`clusters`, `cluster_names`) is returned only in `structuredContent`. Result on Claude: the model receives guidance telling it to acknowledge/act on the board, but cannot see the board.

**Live evidence (2026-07-05):** user asked to add items to their board. `read_board_before_editing` ran, retrieved 4 clusters (backend `clarity.cluster.retrieved`), the data left the server in `structuredContent` — and the model said it could not see cluster names, guessed "Unclustered", and the edit failed twice. A verbatim "quote exactly what the tool returned to you" experiment confirmed the model received **only the guidance text, zero board data**.

This is NOT an auth, persistence, or discovery problem (all verified healthy). It is the adapter dropping the model's data channel.

### Why PG-Claude does NOT have this bug (the reference)
PG-Claude's adapter (`mcp_server/priority_guardian_claude/response_adapter_dupl.py`, Step 4) extracts `structuredContent["data"]` and serialises it into the `content` text block. That is the mechanism MindSort-Claude is missing. **Use PG-Claude's adapter as the pattern reference.**

### Why this is NOT a verbatim copy of PG-Claude (the important nuance)
- PG's handlers put model-facing data under a single `structuredContent["data"]` key; PG's data is small (≤3 priorities) so PG dumps all of it into `content`.
- MindSort's handlers put data under **top-level `structuredContent` keys** (`clusters`, `cluster_names`, `has_history`, `is_empty_snapshot`), NOT under a `"data"` key. A verbatim PG copy (`.get("data")`) would surface nothing.
- MindSort boards can be large (thought text for every item; production widget payloads have been hundreds of KB). Dumping the full `clusters` array into `content` on every call would bloat model context and latency — the exact token risk the PG guideline calls out (PG mitigates with `MAX_LIST_ITEMS = 10`).

**Therefore: surface a COMPACT projection into `content`, not the full board.** This is a per-tool decision based on whether the model must *act* on the data.

---

## Required behaviour (what, not how)

The fix is in the MindSort-Claude adapter and/or dispatcher (`response_adapter_dupl.py`, `handlers/tools_dupl.py`). Shared `clarity/` handlers are NOT modified — the adapter rewrites their output, consistent with the established "import by reference + adapt tail" architecture.

Classify MindSort's board-returning tools by whether the **model** needs the data (vs. only the widget):

**Group A — model MUST see board structure to act. Surface a compact projection into `content`:**
- `read_board_before_editing` — the model targets edits by cluster/subcluster name. It needs the **names and structure**, not full thought text.
- `edit_board` — on the failure/`too_many_additions` paths where the model must choose a valid target; and on success, a brief confirmation of what changed.

**Group B — display-only; widget shows the board, model should NOT re-list it. Do NOT surface full data (guidance already tells the model not to):**
- `load_saved_board` — its own guidance says the widget displays the board; surfacing the full board into `content` would both bloat context and contradict the guidance. (Confirm against the handler's guidance text.)
- `organize_thoughts`, `start_prioritization_flow` — widget-rendering tools; the model narrates, the widget shows. Verify each tool's guidance intent before deciding; default to NOT dumping data for widget-display tools.

**Compact projection definition (Group A):** a minimal, model-actionable representation — at minimum the **cluster names**, and where useful the **subcluster names and per-container item counts**. Explicitly NOT the full thought-item text arrays, tags, or priority metadata. The projection must be bounded regardless of board size (apply an item/character cap consistent with PG's `MAX_LIST_ITEMS` precedent — reuse that constant/approach rather than inventing a new limit).

**Key-name reality:** MindSort handlers already compute exactly what Group A needs. `read_board_before_editing` returns a top-level `cluster_names` list in `structuredContent` (verified in source). The adapter must read MindSort's actual keys (`clusters`, `cluster_names`), NOT PG's `"data"` key. Do not assume a `"data"` envelope.

**Empty/error states:** the empty-board and persistence-error paths return `clusters: []` with guidance that already carries the needed meaning ("no saved board", "backend error — do not tell them they have no board"). These need no data projection — guidance alone is correct. Do not regress the error guidance.

**Must preserve (do not regress):**
- Guidance still moves to `content` (existing behaviour, keep it).
- `openai/*` `_meta` stripping and `_meta` discrimination (keep `saved_board_hash`, strip `openai/*`) — unchanged.
- `structuredContent` still carries the FULL board for the widget — the widget needs it. Only `content` gets the compact projection. Do not strip the widget's data.
- `isError` propagation unchanged.
- Adapter never mutates the original `CallToolResult` (returns new object) — current invariant.

---

## Ordering within `content`
When both guidance and a data projection are surfaced, order for readability: guidance first, then any existing text summary, then the compact board projection. (PG-Claude uses this order; mirror it.) Result is a single `TextContent` block.

---

## Artifact fixes required (living-artifacts rule)
The MindSort canonical doc is **stale on this exact point** and, left unfixed, will cause the next tool/increment to repeat the bug:

1. **`structural_guideline_claude_vs_openai_MindSortAI.md` §4 "Response Adapter Contract"** currently lists only: move guidance→content, strip `openai/*`, discriminate `_meta`, set widget linking, leave `structuredContent` clean. It is **missing the model-visible-data step**. Add a step: *"Surface a compact, model-actionable board projection (cluster/subcluster names + counts, bounded) into `content` for tools where the model must act on board structure (`read_board_before_editing`, `edit_board` decision paths). Do NOT surface full `clusters` (token cost); widget-display tools surface guidance only."* Cross-reference the PG guideline's "Platform Divergence: Model-Visible Channel" section and the 2026-07-05 evidence.
2. Note in that doc that the divergence was **discovered after** the doc's June-2026 authoring, which is why the original §4 omitted it.

If, while implementing, any other mismatch between these docs and the code is found, flag it — do not silently work around it.

---

## Tests

**Unit tests (adapter-level, no network) — `mcp_server/mindsort_claude/` test tree:**
1. Given a `read_board_before_editing`-shaped `CallToolResult` (top-level `clusters` + `cluster_names` in `structuredContent`, guidance present), assert the returned `content` text contains the cluster names. *Bug it catches:* the current bug — data stranded in `structuredContent`, model blind.
2. Assert the returned `content` does NOT contain full thought-item text for a large board (projection is compact, not a full dump). *Bug it catches:* naive PG-style full-`data` dump causing token bloat.
3. Assert `structuredContent` STILL contains the full `clusters` after adaptation (widget must keep its data). *Bug it catches:* over-aggressive stripping that starves the widget.
4. Assert the projection is bounded when the board exceeds the cap (many clusters/items) — output length stays within the PG-precedent limit. *Bug it catches:* unbounded projection on large boards.
5. Group B / display-only tool (e.g. `load_saved_board` success shape): assert `content` does NOT get a full board dump (guidance-only behaviour preserved). *Bug it catches:* surfacing data where the widget is the intended display, contradicting guidance + bloating context.
6. Empty-board and persistence-error shapes: assert guidance reaches `content` and no misleading data is added. *Bug it catches:* regressing the "do not tell them they have no board" error contract.
7. Preserved-behaviour guards: `openai/*` stripped from `_meta`, `saved_board_hash` retained, original object not mutated, `isError` propagated. *Bug it catches:* collateral regressions in the existing adapter contract.

**Integration test (dispatcher-level):**
8. Drive a board-returning tool through the MindSort-Claude dispatcher (`handlers/tools_dupl.py`) end-to-end with a stubbed persistence layer returning a known multi-cluster board; assert the final `CallToolResult` delivered to serialisation has the cluster names in `content` AND the full board in `structuredContent`. *Bug it catches:* adapter correct in isolation but not actually wired into the dispatch path for the relevant tools.

Separate unit from integration as above. For each test, the "bug it catches" line is required.

---

## Out of scope (do not bundle)
- The `organize_thoughts` single-item `Unclustered` cluster repair failure (`reason=unrecognized_format`) — separate, parked.
- Widget rendering / `ui.domain` / display-mode work.
- Any change to `clarity/` (OpenAI, in review) or the backend.
- The persist-proof roundtrip evidence item (separate; edits were failing before any write, which this fix addresses — but the roundtrip is its own verification).

---

## Definition of Done
- [ ] MindSort-Claude adapter surfaces a compact, bounded board projection into `content` for Group A tools; Group B unchanged (guidance-only).
- [ ] Adapter reads MindSort's real keys (`clusters`, `cluster_names`), not PG's `"data"`.
- [ ] `structuredContent` still carries the full board for the widget; existing guidance-move + `_meta` handling preserved.
- [ ] Unit tests 1–7 and integration test 8 pass; each documents the bug it catches. State the known-baseline failure count before/after.
- [ ] `structural_guideline_claude_vs_openai_MindSortAI.md` §4 updated with the model-visible-data step + provenance note.
- [ ] No change outside `mcp_server/mindsort_claude/` and that one doc.
- [ ] `OPERATIONS_PREDEPLOY.md` read before commit.
- [ ] Report ends with the commit hash (review will verify against `git show <hash>:<path>`).

## Post-deploy verification (the real proof)
Deploy MindSort-Claude MCP only. Then, in a Claude MindSort conversation:
1. "Add X to my board" → the model should now state the actual cluster names when asking/placing (not "Unclustered"), and a subsequent `edit_board`/`organize_thoughts` should target a real cluster and persist.
2. Confirm the widget still renders the full board (structuredContent intact).
3. This also unblocks the still-open **persist-proof roundtrip** (a real `organize_thoughts` write → `clarity.persist.success` → `load_saved_board` shows the new board).
