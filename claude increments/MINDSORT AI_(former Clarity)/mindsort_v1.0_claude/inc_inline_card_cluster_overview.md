# Increment: MindSort-Claude inline card redesign — cluster overview

**App:** MindSort AI for Claude (`mcp_server/mindsort_claude/`). Anthropic MCP connector, inline widget.
**Type:** Widget UI change (inline card only). No backend, no tool-logic, no data-contract change.
**Touches:** `mcp_server/mindsort_claude/widget-react/src/` only (App.tsx, utils.ts, and the widget build). Does NOT touch `clarity/` (OpenAI), the backend, or any tool handler.

This briefing implements the approved design shown in the 2026-07-14 mockup (Option A, tag-indicator): header "Your MindSort AI Board" + count summary; one row per cluster with P1/P2/P3 badge + left-accent border when prioritized, cluster name, muted tag icon when tagged, thought count; priorities-first ordering; "+N more clusters" truncation; "Open full board →" action.

---

## Canonical guidance — CONFIRMED against `doc/Claude_Compliance/design guidelines_mcpapps_claude.md`
Read and confirmed against the Anthropic MCP Apps design guidelines (authoritative source). Constraints:
- **Max height: 500px — ABSOLUTE, NON-NEGOTIABLE. Auto-fit content, NO nested scrolling.** The card must NEVER exceed 500px in ANY state (max header length, tallest rows, footer present, largest board). This is upheld by the row cap below, which is derived from measured height — not a fixed guess. If in doubt, show FEWER rows. This is the hard limit; every other design choice yields to it.
- **Max actions: 2, at the bottom of the card.** This design uses ONE action ("Open full board"). Compliant. Expansion to fullscreen is explicitly endorsed by the guideline ("inline card might show a summary; fullscreen mode can offer the detailed view"; "provide a clear visual affordance for expansion").
- **Max data points: 4-5.** This design DEVIATES from this guidance — see "Data-point deviation" below.
- No drill-ins/breadcrumbs/multiple views; no menus/popovers; visible controls only. This design complies (single list, one button, no menus).
- Mobile: full-width, tap targets >=44pt, no horizontal scroll, `_meta.ui.prefersBorder:false`, honor `hostContext.safeAreaInsets`.

Also read `structural_guideline_claude_vs_openai_MindSortAI.md` for MindSort-specific widget rules before implementing.
Before commit: read `OPERATIONS_PREDEPLOY.md` and follow it.

## Data-point deviation (documented, intentional — Nadja's decision 2026-07-14)
The guideline states "Max data points: 4-5" for inline cards. A per-cluster list (name + count + optional badge + optional tag icon, up to MAX_INLINE_ROWS rows) exceeds a literal 4-5 count. This deviation is a **deliberate product choice**, made with the tradeoff understood:
- Rationale: a compliant "4-5 data point" summary (aggregate counts + top priority only) was mocked up and rejected as too thin — it doesn't give the user a content overview of their board. The per-cluster list is materially more useful.
- Risk (recorded): per prior compliance analysis, the design-guideline numbers are NOT auto-reject gates, but Anthropic reviewers test widgets and MAY flag violations. This is an accepted, known risk, not an oversight.
- Mitigation: the design honors the *spirit* (don't overwhelm) via a clean one-line-per-cluster layout, priorities-first ordering, and truncation to MAX_INLINE_ROWS — so density stays low and the 500px / no-scroll HARD limits are always met. The "4-5" deviation is aesthetic-density only; it does not break rendering.
- Fallback on record: if a reviewer flags it, the compliant summary-card design (aggregate stats + top priority) is the documented fallback.
Do NOT "fix" this deviation by silently reverting to a summary card — it is an intentional decision. If the compliance MASTER (not the design guideline) lists data-point count as an explicit gating/rejection criterion, STOP and flag that specifically — that would change the risk from "may be flagged" to "will be rejected."
NOTE: the data-point deviation does NOT extend to the height limit. 500px is absolute and is NOT part of the accepted deviation. The row cap exists precisely to keep the deviation from ever violating 500px.

---

## Problem
The current inline card (`widget-react/src/App.tsx`) renders ONLY own-level priorities plus a count line. When the board has no priorities set (a common state), it collapses to a near-empty card showing just "N clusters · M thoughts" — no cluster names, no content overview, no value. It also hardcodes the header "Priorities", which is Priority Guardian's vocabulary, not MindSort's.

## Goal
Replace the priority-only card with a **cluster-overview card** that is valuable in every state (including zero priorities), matches the OpenAI MindSort visual language, respects the HARD Anthropic inline constraints (500px, no nested scroll, <=2 actions), and provides an expand affordance to the (future) fullscreen full board.

This increment is the INLINE CARD ONLY. The fullscreen full-board view is a separate, later increment.

---

## Design spec (decided — per-cluster overview, Option A tag-indicator; matches the approved mockup)

### Header
- Title: **"Your MindSort AI Board"** (replaces the current "Priorities"). Sentence case.
- Right-aligned muted summary: `{N} clusters · {M} thoughts` where M = sum of `sum_thought_items` across clusters (reuse existing `getTotalThoughtCount`).

### Rows — one per cluster
Each cluster renders as a single-line row, left to right:
- **Priority badge** (P1/P2/P3) — ONLY if the cluster has own-level `priority.rank`. Rank→color mapping already in current `App.tsx` `PriorityRow`: P1 → danger, P2 → warning, P3 → info/accent. Prioritized clusters also get a left-accent border in the matching role color (mirrors OpenAI `ClusterCard` `border-l-4`).
- **Cluster name** — flex-fill, single line, ellipsis-truncated (`white-space:nowrap; overflow:hidden; text-overflow:ellipsis`). Never wraps. (Single-line names are also part of what keeps row height bounded for the 500px limit.)
- **Tag indicator** — a single muted tag icon (NOT tag text) ONLY if `cluster.tags?.length > 0`. Signals "this cluster has action hints"; full tag pills live in fullscreen (mirrors OpenAI `ClusterCard`, which renders pills only when expanded). Accessible label required (e.g. `aria-label="has action tags"`). Do NOT render tag text inline.
- **Thought count** — right-aligned muted `{sum_thought_items} thoughts`.

Row data source: `cluster.cluster_name`, `cluster.priority?.rank`, `cluster.tags`, `cluster.sum_thought_items` — all present on the `Cluster` type and confirmed live (utils.ts reads them today).

### Ordering
Prioritized clusters first, P1 → P2 → P3, then unprioritized by `sum_thought_items` descending (largest first). Pure, unit-testable sort helper. Do NOT assume unique or <=3 ranks (mirror `extractOwnLevelPriorities` Data Rule 4: handle duplicates and >3).

### Truncation / overflow — THE 500px SAFETY MECHANISM (must guarantee the hard limit)
The card MUST NEVER exceed 500px. The row cap is how that guarantee is enforced:
- Determine MAX_INLINE_ROWS by MEASURING, not guessing. Compute the worst-case height budget: 500px minus header height minus footer height ("+N more" line + "Open full board" button) minus card padding, divided by the tallest possible row height (row with a badge + tag icon at the largest host font size). Floor the result. That floor is MAX_INLINE_ROWS.
- Starting estimate is ~5 rows, but the FINAL value is whatever the measured 500px budget allows — and if the measurement is borderline, round DOWN. Never round up into a possible overflow. State the final value and how it was measured in the report.
- When `clusters.length > MAX_INLINE_ROWS`, render a muted `+{N} more clusters` line (left) on the footer row. `N = clusters.length - MAX_INLINE_ROWS`.
- Priorities-first ordering means truncation only ever hides unprioritized overflow. Hidden clusters are never lost — all present in the fullscreen board.
- Because ordering + truncation cap the row count, and rows are fixed single-line height, total card height is bounded and 500px is structurally guaranteed regardless of board size. The card must AUTO-FIT this content height (no fixed height, no internal scroll). Verify the rendered height at MAX_INLINE_ROWS is <=500px on the real host before shipping.

### Host tokens (from the confirmed design guidelines — use these exact names)
- Surfaces: `--color-background-secondary` (card), `--color-background-primary`/`--color-background-tertiary` (rows). Border: `--color-border-primary`/`--color-border-tertiary`. Text: `--color-text-primary` (names), `--color-text-tertiary` (muted counts/summary).
- Priority roles: P1 `--color-background-danger` + `--color-text-danger` + `--color-border-danger`; P2 `--color-background-warning` + `--color-text-warning` + `--color-border-warning`; P3 `--color-background-info` + `--color-text-info` + `--color-border-info`.
- Radius: `--border-radius-xl` (12px) card, `--border-radius-md` (8px) rows. Border width: `--border-width-regular` (0.5px).
- NO hardcoded hex. NO OpenAI `@openai/apps-sdk-ui` tokens. Light + dark both handled by these tokens — verify nothing hardcoded sneaks in.
- Mobile: set `_meta.ui.prefersBorder:false` (confirm current `resources_dupl.py` already does); honor `hostContext.safeAreaInsets`; tap targets (the button) >=44pt; rows stay single-line, no horizontal scroll.

### Open full board action
- Single button, bottom-right: **"Open full board →"** (this is the 1 of max-2 actions; endorsed expansion affordance).
- The fullscreen view does NOT exist yet (`availableDisplayModes` is `['inline']`). Do NOT wire this to a `requestDisplayMode('fullscreen')` that fails silently. Choose the honest option:
  - Preferred interim: the button triggers a chat action loading the full board in conversation (via the MCP Apps bridge — a `callServerTool('load_saved_board', ...)` full-render intent, or the bridge's sendPrompt-equivalent). A working action, not a dead fullscreen call.
  - If NO working target exists yet, OMIT the button this increment; add it with the fullscreen increment. Do NOT ship a button that does nothing.
- Report which option was chosen and why.

### Empty / error states (do not regress)
- No board / empty snapshot: keep the existing friendly empty-state path. Overview card renders only when clusters exist.
- Loading and stale-bridge overlays in current `App.tsx`: preserved unchanged.

### Layout
- One-line-per-cluster, uniform row height (this is WHY tags are an icon, not chips — uniform rows keep the card short and within the 500px limit).

---

## Explicitly OUT of scope
- Fullscreen full-board view (separate increment).
- Full tag pills inline (rejected — Option A chosen; pills belong in fullscreen).
- Any change to `clarity/` (OpenAI widget), backend, tool handlers, or the response adapter.
- CRUD from the inline card.
- Subcluster detail inline (counts roll up via `sum_thought_items`; subcluster breakdown is a fullscreen concern).

---

## Tests

**Unit tests (pure helpers — no bridge, no render):**
1. Sort helper: prioritized-first (P1→P2→P3), then unprioritized by `sum_thought_items` desc. *Catches:* wrong order (unprioritized above P1, or size-sort applied to the whole list instead of only the unprioritized tail).
2. Sort helper edge cases: no priorities (pure size-desc), all prioritized, duplicate ranks, >3 priorities. *Catches:* assuming unique/<=3 ranks.
3. Truncation helper: `<= MAX_INLINE_ROWS` → no "+N more"; `> MAX_INLINE_ROWS` → exactly MAX_INLINE_ROWS rows + correct `N = length - MAX_INLINE_ROWS`. *Catches:* off-by-one in overflow count; also catches a cap set higher than the measured 500px budget (the test asserts row count never exceeds MAX_INLINE_ROWS).
4. Row-model builder uses REAL keys: `tags:[]` → no tag indicator; `tags:['decide']` → indicator true; no `priority` → no badge; `priority.rank='P2'` → P2 badge. *Catches:* wrong keys, or tag text leaking inline.

**Component/render tests (if harness supports — repo has `widget-react/src/test/`):**
5. 6 clusters (3 prioritized, 3 not): priorities first, header text EXACTLY "Your MindSort AI Board", "+1 more clusters" when MAX_INLINE_ROWS=5. *Catches:* header regression to "Priorities", ordering regression, truncation not firing.
6. Zero-priority board renders cluster names + counts (NOT an empty count-only card). *Catches:* the core bug this increment fixes.
7. Loading and stale-bridge overlays still render as before. *Catches:* collateral regression.
8. Height guard: rendered card at MAX_INLINE_ROWS (with badges + tag icons + footer) has offsetHeight <= 500px in the test viewport. *Catches:* a row cap that overflows the hard limit. (If the harness can't measure layout height reliably, do this as the manual pre-ship check in Post-deploy verification instead, and say so.)

Each test states the bug it catches.

---

## Definition of Done
- [ ] Inline card renders per-cluster overview matching the approved mockup: one row per cluster, priorities-first, name + count always, priority badge + left-accent when prioritized, tag icon when tagged.
- [ ] Header reads "Your MindSort AI Board".
- [ ] **Card height <= 500px in every state, verified on the real host. Row cap derived from the measured 500px budget (rounded DOWN if borderline), not a fixed guess. State the final MAX_INLINE_ROWS and the measured height at that cap.**
- [ ] Truncation to MAX_INLINE_ROWS with "+N more clusters".
- [ ] "Open full board" action does something real, or is omitted (state which + why).
- [ ] Exact host tokens used (list above); light + dark verified; no OpenAI tokens, no hardcoded hex; `prefersBorder:false` + safeAreaInsets confirmed.
- [ ] Empty/loading/stale states preserved.
- [ ] Unit tests 1–4 pass; component tests 5–8 pass if harness supports; each documents its bug. State known-baseline before/after.
- [ ] Data-point deviation acknowledged as intentional (do not revert to summary card); compliance-MASTER checked for whether data-point count is an explicit gating criterion — if so, flag.
- [ ] No change outside `mcp_server/mindsort_claude/widget-react/`.
- [ ] `OPERATIONS_PREDEPLOY.md` read before commit.
- [ ] Report ends with commit hash (review verifies against `git show <hash>:<path>`).

## Post-deploy verification
Deploy MindSort-Claude MCP only, then in Claude:
1. "show me my mindsort board" on a board with NO priorities → card shows cluster names + counts (was: count line only). Header reads "Your MindSort AI Board".
2. Board with priorities → prioritized clusters first, badges + left accent.
3. Board with >5 clusters (or >MAX_INLINE_ROWS) → "+N more clusters"; **card height stays within 500px, no nested scroll, nothing clipped** — measure it.
4. Dark mode → all text/borders legible.
5. Mobile width → rows single-line (names ellipsis-truncate; tag icon + count still visible); card not overflowing; button tap target >=44pt.

## Fullscreen follow-on (do NOT build here)
The fullscreen full-board view (all clusters, subclusters, thought items, full tag pills — the "big picture") is the necessary next increment. The design guidelines CONFIRM fullscreen exists as a display mode and that inline→fullscreen expansion is the intended pattern — BUT note the guideline states fullscreen is "not yet available on mobile — apps render inline only" (mobile fullscreen "coming soon"). So: desktop gets the full board in fullscreen; mobile stays inline-summary-only until Anthropic ships mobile fullscreen. Confirm current third-party-connector fullscreen support at build time. Requires: add `'fullscreen'` to `availableDisplayModes`, a full-board renderer, the inline↔fullscreen transition (close returns to same scroll position). Spec separately after this ships.