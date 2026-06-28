# Increment MindSort-Claude-Widget-A: Scaffold + Bridge + Theming + Inline Priority Summary

**Goal:** Build the Claude MindSort widget foundation and its **inline display only**: Vite+React scaffold, `@modelcontextprotocol/ext-apps` bridge, host theming, and a **priority-centric inline summary card**. At the end of this increment the widget renders a correct, compliant, truthful inline summary of the user's board. No fullscreen. No nested board. No CRUD. No half-wired controls.

Independently testable and reviewable at increment scope. The server-side delivery surface already exists (Widget-0 registered the resource; Widget-0b made tool results point at the Claude URI). This increment fills that surface with a real bundle.

---

## Context — what already exists (do not rebuild)

Server-side Claude work is complete and verified:
- **Claude-01/02/02b** — scaffold, tool wiring, response adapter, discovery fix.
- **Widget-0** — registered the widget **resource**: `WIDGET_URI = "ui://mindsort-claude/dashboard-v1.html"`, MIME `text/html;profile=mcp-app`, `_meta.ui` carries `domain` (sha256 hash) + `csp` + `prefersBorder:false`. It serves a **placeholder** HTML at `mcp_server/mindsort_claude/widgets/mindsort-dashboard-claude.html` (contains the marker text "MindSort Widget (placeholder)").
- **Widget-0b** — result-path translation: successful widget-producing tool results now carry `_meta.ui.resourceUri = <Claude WIDGET_URI>` (the OpenAI URI is stripped upstream). **Widget-A does not need to handle the OpenAI-URI leak — it is already solved.**

**This increment replaces the placeholder HTML with the built React bundle.** The build must output to exactly `mcp_server/mindsort_claude/widgets/mindsort-dashboard-claude.html` (the file Widget-0 serves) so the registered resource serves the real widget. If the build lands anywhere else, the resource keeps serving the placeholder and nothing renders.

### Architectural reference — MIRROR, don't copy business logic

The reference is **PG's Claude widget**: `mcp_server/priority_guardian_claude/widget-react/`. It already implements the ext-apps bridge, host theming, stale-bridge handling, and ErrorBoundary. **Mirror that architecture. Do NOT copy PG's business logic, CRUD, or UI** (PG is a priorities-CRUD dashboard; MindSort-A is a read-only summary).

The OpenAI MindSort widget (`clarity/widget-react/`) is **NOT** the architectural reference — it is built on `window.openai.*`, is single-view, and renders the entire nested board. Do not mirror its bridge. **However**, its `src/types.ts` (data contract) and a few **pure** helpers in its `src/utils.ts` are reusable — see "Reuse vs. forbid" below.

---

## Canonical guidance (READ FIRST)

This is a **Claude/Anthropic** widget increment. Read before implementing:
1. `doc/Claude_Compliance/claude_connectors_compliance_master.md` — §4K (widget/MCP-Apps constraints, CSP, `ui.domain`), §4N (theming/transparency), §4O (technical requirements).
2. `doc/Claude_Compliance/structural_guideline_claude_vs_openai_MindSortAI.md` — §3 (platform-specific components), §7 (obligatory vs recommended), §8.6 (widget requirements).

Both verified June 2026.

### Pre-implementation
Read `doc/OPERATIONS_PREDEPLOY.md` — specifically **"Widget Bundle Changes"** (the single-source-of-truth `WIDGET_URI` discipline and the silent stale-cache failure mode: widget bundle bytes are NOT frozen at approval, only the URI is; bytes update on every deploy and require aggressive cache invalidation — delete + re-add the app). No migrations. No DB work.

---

## Stack (verified from PG widget-react)

Mirror PG's exact toolchain:
- `@modelcontextprotocol/ext-apps@^1.2.2`, `react@^18.3.1`, `react-dom@^18.3.1`
- Vite 6, `@vitejs/plugin-react`, **`vite-plugin-singlefile`** (builds one self-contained HTML)
- `vite.config.ts`: `plugins: [react(), viteSingleFile()]`, `build.outDir: '../widgets'`, `emptyOutDir: false`, `rollupOptions.input: 'mindsort-dashboard-claude.html'`. **outDir + input filename must resolve to `mcp_server/mindsort_claude/widgets/mindsort-dashboard-claude.html`** (the Widget-0 served file).

---

## Scope

### IN
1. **Scaffold** at `mcp_server/mindsort_claude/widget-react/` — Vite + React + ext-apps, mirroring PG's directory shape (`src/App.tsx`, `src/main.tsx`, `src/types.ts`, `src/utils.ts`, `src/i18n.ts` if used, `src/main.css`, `vite.config.ts`, `package.json`, `tsconfig.json`).
2. **Bridge** — `useApp()` from `@modelcontextprotocol/ext-apps/react`; receive tool results via `ontoolresult`; consume `structuredContent.clusters`.
3. **Host theming** — `useHostStyles`, transparency, Claude `var(--color-*)` tokens, light + dark.
4. **Inline priority summary** — the data design below.
5. **States** — loading, ErrorBoundary, stale-bridge (3s).

### OUT (later increments)
- fullscreen, nested board, `requestDisplayMode`, expand button, "view board" CTA, any CRUD, any dead controls.

---

## CRITICAL: `availableDisplayModes` must be `['inline']` — do NOT mirror PG here

PG declares `capabilities: { availableDisplayModes: ['inline', 'fullscreen'] }` because PG **has** a fullscreen CRUD mode. **Widget-A is inline-only.** Declare:
```ts
useApp({
  appInfo: { name: 'MindSort', version: '1.0.0' },
  capabilities: { availableDisplayModes: ['inline'] },   // NOT ['inline','fullscreen']
  onAppCreated: ...
})
```
This is the one place "mirror PG" is wrong. Advertising fullscreen you don't implement is a half-wired control. (`McpUiDisplayMode = 'inline'|'fullscreen'|'pip'` per the ext-apps spec types; declare only `inline`.)

---

## Bridge requirements (verified from PG `App.tsx` — exact API)

- Import: `import { useApp, useHostStyles, App as McpApp, McpUiToolResultNotification } from '@modelcontextprotocol/ext-apps/react'`
- `const { app } = useApp({ appInfo, capabilities, onAppCreated })`.
- In `onAppCreated(appInstance)`: store `appRef.current = appInstance`; read `appInstance.getHostContext()` for `displayMode`/`platform` if needed; register `appInstance.ontoolresult = (result) => {...}`.
- **Tool result shape (MindSort-specific):** read `result.structuredContent?.clusters`. PG reads `structuredContent.data`; **MindSort uses `clusters`** — verify the path, do not copy PG's `.data`.
- `useHostStyles(app, app?.getHostContext())` — must pass hostContext so dark mode applies.
- **Stale bridge:** `useEffect` with a 3s `setTimeout`; if `appRef.current` is still null, `setIsBridgeStale(true)` and render the stale overlay. Mirror PG exactly.
- **No `callServerTool`, no CRUD, no `lastCrudAtRef`, no backfill/refresh.** Widget-A is read-only display. All of PG's CRUD handlers are OUT.

---

## Data contract (verified from `clarity/widget-react/src/types.ts` — reuse this)

```ts
type Rank = 'P1' | 'P2' | 'P3'
interface ThoughtItem { text: string; priority?: { rank: Rank } }
type ThoughtItemInput = string | ThoughtItem       // <-- a thought item can be a BARE STRING
interface Subcluster { subcluster_name: string; thought_items?: ThoughtItemInput[]; sum_thought_items: number; priority?: { rank: Rank }; ... }
interface Cluster { cluster_name: string; thought_items?: ThoughtItemInput[]; subclusters?: Subcluster[]; sum_thought_items: number; priority?: { rank: Rank }; ... }
```
The widget receives `structuredContent.clusters: Cluster[]` — the full nested tree. The `Cluster`/`Subcluster`/`ThoughtItem` types are reusable as-is. **Do NOT reuse the `window.openai` global interface block** from that file — that is the OpenAI bridge.

---

## Reuse vs. forbid (verified from `clarity/widget-react/src/utils.ts`)

**Reuse (pure, platform-agnostic):**
- `normalizeThoughtItem(item: ThoughtItemInput): ThoughtItem` — **mandatory** (see Data Rule 2).
- `truncateText(text, maxLength=80)` — for Data Rule 6.
- `rankToNumber(rank)` — for sort order.

**FORBID (wrong semantic or platform-coupled):**
- `getEffectiveRank(cluster)` and `getEffectiveSubclusterRank(subcluster)` — these live in `clarity/widget-react/src/utils.ts` and roll child priorities UP to parents. **That is the wrong semantic for the inline summary.** Do not import or use them. (See Data Rule 2; a unit test must fail if either name appears in Widget-A source.)
- `getToolOutput()` — reads `window.openai.toolOutput`. Platform-coupled to OpenAI. Use the ext-apps `ontoolresult` path instead.

---

## Inline Priority Summary — the display

**Priority-CENTRIC, not cluster-centric.** Show the user's explicitly prioritized entities, whether each is a cluster, subcluster, or thought item.

Example:
```
Priorities
P1 · Email investor deck     Work › Fundraising
P2 · Pricing page            Marketing › Landing page
P3 · Product narrative       Strategy
7 clusters · 42 thoughts
```
Empty state:
```
7 clusters · 42 thoughts · none prioritized yet
```

### Data Rules (REQUIREMENTS, not implementation)

**1. Own-level priorities only.** Walk the tree; collect entities whose **own** `priority.rank` is set. Priorities can sit on `cluster.priority.rank`, `subcluster.priority.rank`, or `thought_item.priority.rank` (object-form items only).

**2. Normalize thought items — they can be bare strings.** `ThoughtItemInput = string | ThoughtItem`. A bare string has no priority and cannot carry one. Before reading `.priority` on any thought item, normalize via `normalizeThoughtItem` (or equivalent `typeof item === 'string'` guard). **Skipping this either crashes (TS) or silently misreads (JS).** Only object-form items contribute priorities.

**3. DO NOT use effective rank.** Do not use `getEffectiveRank`/`getEffectiveSubclusterRank`. If a cluster has no own rank but contains a P1 thought item, the summary shows `P1 · <thought item text>` (the item), **NOT** `P1 · <cluster name>`. Show the entity that actually holds the rank.

**4. Do NOT assume unique ranks or ≤3 — render defensively.** *(CORRECTED from the prior draft — verified against `clarity/tools/board_utils.py`.)* `MAX_PRIORITIES = 3` and rank-uniqueness are enforced only inside `start_prioritization_flow._validate_priorities` and within a single `apply_priorities` reassignment's conflict logic — **they are NOT a guaranteed invariant of the persisted board.** `edit_board`'s `set_priority` path calls `apply_priorities` directly; there is no board-load-time validation that ranks are unique or count ≤3. Therefore the widget must:
   - collect ALL own-level priorities, then sort by rank (`rankToNumber`), then render;
   - tolerate duplicate ranks (e.g. two P1s) without crashing or silently dropping — render both, or render deterministically and don't assume `priorities['P1']` is a single entity;
   - tolerate >3 priorities (render what's there; optionally cap display, but do not assume ≤3).
   Do NOT index priorities by rank as if rank is a unique key.

**5. Breadcrumbs — derive from tree position (no backend change).** Each row: `rank · entity-name/text · breadcrumb`.
   - cluster → no breadcrumb (it's top level): `P1 · Strategy`
   - subcluster → `P2 · Fundraising     Work`
   - thought item → `P3 · Email investor deck     Work › Fundraising`
   The full nested tree is in `structuredContent.clusters`; breadcrumb is the path to the entity.

**6. Count line — there is NO board-level total; SUM it.** *(ANSWERED from source — `types.ts` has no top-level total; `Cluster`/`Subcluster` carry `sum_thought_items`.)* `total clusters = clusters.length`. `total thoughts = sum of each cluster.sum_thought_items` (precomputed by `enrich_clusters`, present on the data the widget receives). Do not re-walk to count if `sum_thought_items` is present; do not invent a board-level field.

**7. Truncation.** Long entity text: single line, ellipsis, no wrap explosion. Use `truncateText`.

---

## Theming (compliance §4N)

- **Forbidden (OpenAI tokens):** `bg-surface-secondary`, `text-default`, `border-strong`, `@openai/apps-sdk-ui`, any `window.openai` style.
- **Use Claude host tokens:** `var(--color-background-*)`, `var(--color-text-*)`, `var(--color-border-*)`, applied via `useHostStyles`. Mirror PG's inline-style usage with `var(--color-...)` + hex fallbacks (e.g. `color: 'var(--color-text-secondary, #3D3D3A)'`).
- **Transparency (required):** `html, body { margin: 0; background: transparent; }` and `<meta name="color-scheme" content="light dark" />` in the HTML entry. (The Widget-0 placeholder already has these — preserve them in the real bundle's HTML.)
- The resource already declares `_meta.ui.prefersBorder=false` (Widget-0). Do not add server changes. If you find the resource registration missing or changed, STOP and report — do not silently edit server files.

---

## States (mirror PG)

- **Loading** — until `ontoolresult` populates data / `isInitialized`. Themed, centered, `t('loading')`-style.
- **Stale bridge** — `appRef` never set within 3s → overlay ("session expired" style). Mirror PG.
- **ErrorBoundary** — class component in `main.tsx` with `getDerivedStateFromError` + `componentDidCatch` (log `error` + `componentStack`; the project's mobile-error-exposure requirement means the boundary must surface `error.name + message + stack` to the console, not swallow it). Themed fallback using `var(--color-*)`. Mirror PG's `main.tsx`.

---

## What NOT to touch
- `mcp_server/clarity/**` (read-only reference — you READ its `types.ts`/`utils.ts`, never edit).
- `mcp_server/priority_guardian_claude/**` (architectural reference — read, never edit).
- `backend/`, MindSort Claude **server** files (`server_dupl.py`, `tools_dupl.py`, `tools_list_dupl.py`, `response_adapter_dupl.py`, `handlers/resources_dupl.py`, `discovery_dupl.py`, `config.py`). Widget-A is **widget-only**. If the widget needs a server change, STOP and report — it likely means a Widget-0/0b gap.

---

## Tests

### Unit tests (no host, no network — pure functions)
1. **Own-level extraction** — a board with a cluster P1, a subcluster P2, and a thought-item P3 yields exactly those three entities with the correct rank attached to the correct entity. *Must FAIL if `getEffectiveRank`/`getEffectiveSubclusterRank` is used* (assert the extracted P-holder is the item/subcluster, not the parent cluster). State the bug each test would still pass.
2. **String thought-item safety** — a cluster whose `thought_items` contains bare strings AND objects: extraction does not crash and collects priority only from object-form items.
3. **Defensive rank handling** — a board with TWO P1 entities (duplicate rank) and with 4 priorities (>3): extraction does not crash, does not silently drop to a single-per-rank map; renders deterministically. *(This is the corrected Data Rule 4 — the test that the prior draft would have missed.)*
4. **Sort order** — mixed input order yields P1 → P2 → P3.
5. **Breadcrumb derivation** — thought item → `cluster › subcluster`; subcluster → `cluster`; cluster → none.
6. **Empty state** — no priorities → count-only summary, "none prioritized yet".
7. **Counts** — `clusters.length` and summed `sum_thought_items` correct; no board-level-total assumption.
8. **Truncation** — long text truncated, single line.

For each test: document "what bug would still pass this test?"

### Integration tests (separate; mock host / ext-apps bridge)
9. **Mount + bridge** — widget mounts, `useApp` connects, an `ontoolresult` with `structuredContent.clusters` populates the summary.
10. **Theming** — light and dark host context both apply (`useHostStyles` reapplies on context change).
11. **Stale bridge** — no `onAppCreated` within 3s → stale overlay.
12. **Inline-only** — `capabilities.availableDisplayModes === ['inline']`; fullscreen is NOT advertised; no `requestDisplayMode` call exists.

---

## Production readiness (increment scope)
- **Scalability:** static single-file bundle; tree walk over a small in-memory board. None.
- **GDPR/retention:** no new data; widget renders backend-governed data already covered. No increment-level GDPR work. *(Product-level gap — Data Retention Strategy / ROPA written in OpenAI terms, missing Claude-runtime/Anthropic-processor disclosure — remains a **product submission blocker**, tracked, OUT of scope here.)*
- **Latency:** trivial.
- **Deploy note:** widget bundle bytes update on every deploy and require cache invalidation (delete + re-add app) — OPERATIONS_PREDEPLOY "Widget Bundle Changes". The `WIDGET_VERSION` in the URI is the cache-busting lever; if you change served bytes meaningfully, consider whether the version must bump.

---

## Definition of Done
- [ ] Scaffold builds via `vite build` → single self-contained HTML at `mcp_server/mindsort_claude/widgets/mindsort-dashboard-claude.html` (the Widget-0 served path; replaces the placeholder).
- [ ] ext-apps bridge connects; `ontoolresult` reads `structuredContent.clusters`.
- [ ] `capabilities.availableDisplayModes === ['inline']` (NOT PG's `['inline','fullscreen']`); no fullscreen, no `requestDisplayMode`, no CTA, no dead controls.
- [ ] Inline priority summary renders own-level priorities (P1→P2→P3), correct entity per rank, breadcrumbs, count line (summed `sum_thought_items`).
- [ ] `getEffectiveRank`/`getEffectiveSubclusterRank` NOT used (test-enforced).
- [ ] Thought-item string|object normalization handled.
- [ ] Duplicate-rank / >3 handled defensively (no crash, no silent single-per-rank assumption).
- [ ] Empty state correct.
- [ ] Claude `var(--color-*)` tokens only; transparency + `color-scheme` meta preserved in the bundle HTML; light + dark correct.
- [ ] Loading, stale-bridge (3s), ErrorBoundary all present (mirror PG).
- [ ] Zero changes to `clarity/**`, `priority_guardian_claude/**`, `backend/`, MindSort Claude server files.
- [ ] Unit + integration tests pass.
- [ ] Full `pytest tests/unit/ --ignore=tests/unit/mcp_focused -q` run: same known-5 pre-existing failures, no new ones. (The widget is JS/TS, but run the Python suite to confirm no server regression; run the widget's own JS test runner for the React tests.)
- [ ] Before committing: re-read `doc/OPERATIONS_PREDEPLOY.md`; confirm no additional pre-deploy task applies to a widget-bundle change.

**Scope honesty:** This produces a renderable, reviewable inline summary widget — the first visually verifiable increment (host rendering for third-party connectors is confirmed working). It is inline-only and read-only. Fullscreen, nested board, and any interaction are later increments.

---

## Notes for the implementer (flag, don't fix)
- **MIME / `domain` smoke-test:** at first real render, confirm the served MIME (`text/html;profile=mcp-app`) actually renders, and observe whether the host needs tool-level `domain` on `_meta` for prefetch (MindSort omits it; PG includes it — parked question). If the widget fails to render and PG's renders, compare these two. Report findings; do not change server files without confirming root cause.
- If `useApp`/`useHostStyles`/`ontoolresult` signatures differ from PG's (ext-apps version skew), STOP and report — do not guess the API.
- If the build outputs anywhere other than the Widget-0 served path, the resource will keep serving the placeholder — verify the served bytes contain your bundle, not "MindSort Widget (placeholder)".
- Verify every file write persisted (re-read after writing).
