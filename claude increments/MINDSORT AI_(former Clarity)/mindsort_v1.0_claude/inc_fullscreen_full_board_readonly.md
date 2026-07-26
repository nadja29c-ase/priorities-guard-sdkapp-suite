# Increment 2 of 2: MindSort-Claude fullscreen full-board (read-only, host-capability-gated)

**App:** MindSort AI for Claude (`mcp_server/mindsort_claude/`). Anthropic MCP connector, widget.
**Type:** Widget UI — add a fullscreen display mode that renders the FULL board (all clusters, all thoughts, all subclusters, full tag pills), read-only. Wire the existing "Open full board" button to enter fullscreen, offered ONLY when the host advertises fullscreen capability. On hosts that don't (currently: Claude mobile), the inline accordion from increment 1 remains the experience — unchanged.
**Touches:** `mcp_server/mindsort_claude/widget-react/src/` only, PLUS the `WIDGET_VERSION` line in `handlers/resources_dupl.py`. Does NOT touch `clarity/`, `priority_guardian_claude/`, backend, tool handlers, or the response adapter logic.

Increment 1 (inline accordion) is shipped and verified on prod. This is the second and final increment of the MindSort-Claude widget-display work.

## Why this exists
Increment 1 gave users in-place accordion expansion within the 500px inline limit. On hosts that support fullscreen (currently desktop/web), users get a better option: a true fullscreen full-board view showing everything at once. Today "Open full board" calls `load_saved_board`, which just re-renders the same inline card (a visible no-op). This increment makes that button do what it says — switch to fullscreen — on hosts that can honor it.

## Authority hierarchy (read this first — it governs every "which pattern do I follow?" decision)
When guidance conflicts, resolve in THIS order:
1. **Anthropic Apps SDK / MCP protocol** (the installed `@modelcontextprotocol/ext-apps`) and **current Claude host behavior** — normative.
2. **Existing production-tested PG-Claude implementation** — authoritative WHERE the SDK/spec is silent or ambiguous. This project has repeatedly found the written docs lagging or ambiguous while PG-Claude reflects actual host behavior; so when in doubt, reproduce PG.
3. **OpenAI MindSort board** — reference for INFORMATION HIERARCHY and content organization ONLY (it is the only existing full-board layout for this product). NOT a source for implementation, components, APIs, or styling.

Practical rule: **reproduce the proven PG-Claude display-mode implementation, UNLESS inspecting the current SDK reveals a newer, clearly-supported fullscreen pattern — in which case STOP and surface it rather than silently choosing.** Do not treat any single reference as infallible; verify against the actual installed SDK and the real host.

## Canonical guidance (read before implementing)
1. `doc/Claude_Compliance/design guidelines_mcpapps_claude.md` (live: https://claude.com/docs/connectors/building/mcp-apps/design-guidelines) — display modes, fullscreen rules, native close button. Confirmed 2026-07-22: fullscreen is a valid mode; the HOST decides availability; Claude mobile advertises inline-only ("Fullscreen is not yet available on mobile").
2. `doc/Claude_Compliance/structural_guideline_claude_vs_openai_MindSortAI.md`.
Before commit: read `OPERATIONS_PREDEPLOY.md` — especially the "Widget Bundle Changes" section (the version-bump step; increment 1 shipped stale to prod because this was skipped — do not repeat).

## Reference implementation — reproduce PG-Claude's display-mode mechanics
`mcp_server/priority_guardian_claude/widget-react/src/App.tsx` is a SHIPPED, WORKING Claude fullscreen widget. Read it in full first. Facts VERIFIED from that source (2026-07-22) — reproduce them, and re-verify against the file and the installed SDK per the authority hierarchy above:

1. **Capability declaration:** `useApp({ capabilities: { availableDisplayModes: ['inline', 'fullscreen'] } })`. Change MindSort's current `['inline']` to `['inline', 'fullscreen']`. NOTE: declaring fullscreen is not "forcing" it — it advertises app support; the host still decides. This is the forward-compatible pattern: the day Claude enables mobile fullscreen, MindSort inherits it with no code change.
2. **Entering fullscreen is LOCAL state** (`setDisplayMode('fullscreen')`), NOT a `requestDisplayMode` await, in the current PG implementation. Reproduce this UNLESS the installed SDK indicates a newer supported entry pattern (then surface it). Do not invent a `requestDisplayMode`-on-entry handshake on assumption — the shipped code does not do that.
3. **Exiting (minimize) calls `requestDisplayMode({ mode: 'inline' })`,** then sets local state from the returned `result.mode`, in try/catch (silent failure → stays effectively inline). Reproduce `handleMinimizeToInline` in shape.
4. **Initial mode + host sync:** in `onAppCreated`, read `getHostContext()?.displayMode` and set initial state if already fullscreen. Register `onhostcontextchanged` to update `displayMode` and reset `hostFullscreen` when the host returns to inline.
5. **Native close button:** PG renders its own `FullscreenHeader` (minimize) ONLY when `!hostFullscreen` — it does NOT duplicate the host's native fullscreen chrome. **Verify from PG source exactly how `hostFullscreen` is set and how `FullscreenHeader` is gated, and replicate.** Do not duplicate the host's native close control.
6. **Safe-area insets / platform:** copy PG's `safeAreaInsets`/`platform` reads. This code is dormant on hosts without fullscreen and does nothing there — keep it for forward-compatibility (mobile fullscreen, when it ships, will use it). Do not strip it as "not needed for desktop."

## Host-capability gating (NOT "desktop-only") — the mechanism is decided
Offer fullscreen ONLY when the host advertises it. Gate the "Open full board" fullscreen affordance on **`hostContext.availableDisplayModes?.includes('fullscreen')`** (read via `getHostContext()` and kept current via `onhostcontextchanged`). Do NOT gate on `platform !== 'mobile'` — the host, not the platform string, is the authority (research-confirmed 2026-07-22), and capability-detection auto-enables fullscreen wherever/whenever the host offers it.
- When the host advertises fullscreen (currently desktop/web): show "Open full board" → enters fullscreen.
- When it does not (currently Claude mobile): do NOT render the fullscreen affordance. The inline accordion (increment 1) is the intended, standard experience there — this is the endorsed "master-detail-in-inline" mobile pattern, not a degraded fallback. Keep the accordion exactly as shipped.
- A dead/no-op fullscreen button is prohibited (that was the "View remaining cluster content" defect). Hide it when unavailable; never show an affordance the host can't honor.

## Failure & unexpected-state behavior (production paths — define deterministically)
Host context is the SOURCE OF TRUTH; local `displayMode` is an optimistic value that must NEVER permanently diverge from host context. Required behaviors:
- **Fullscreen unavailable** (host doesn't advertise it): affordance not shown (above).
- **Minimize request rejected / errors / times out:** try/catch; remain in whatever mode the host reports; never leave the UI wedged. Reconcile from the returned mode / next `onhostcontextchanged`.
- **Host exits fullscreen unexpectedly** (`onhostcontextchanged` reports `displayMode:'inline'`): widget returns to inline, resets `hostFullscreen`, restores focus (see a11y).
- **Host context changes mid-render** (mode/platform/safeArea): update from the partial context; the host value wins over local state on any conflict.
State (in a code comment) that host context is authoritative and local state only ever reconciles toward it.

## Shared board view-model — ONE model, TWO renderers (architectural requirement)
Inline (accordion) and fullscreen MUST consume the SAME canonical board transformation. Do NOT duplicate sorting, grouping, priority-mapping, or normalization across the two views.
- Extend the existing shared helpers (e.g. the increment-1 `sortClustersForOverview` / priority-sort / normalization in `utils.ts`/App helpers) into one canonical board view-model that both renderers read.
- Inline renderer applies the 500px budget + accordion on top of that model; fullscreen renderer renders the full model expanded. Neither re-sorts or re-derives independently.
- Rationale: two independent transforms WILL drift — a priority-sort fix in one won't reach the other. One model, two thin renderers, prevents that class of bug.

## What fullscreen renders — full board, read-only
Use the OpenAI MindSort board as the reference for INFORMATION HIERARCHY and content organization ONLY (`mcp_server/clarity/widget-react/src/App.tsx` + `components/{ClusterCard,SubclusterCard,ThoughtItem,PriorityBadge,TagPill}.tsx`). Implement with Claude-compatible architecture and design tokens — do NOT import or port OpenAI components, APIs, or styling. The OpenAI board is confirmed READ-ONLY (editing goes through the model); reproduce that read-only hierarchy:
- Cluster header: name, priority badge (P1/P2/P3, text + role color), thought count.
- Summary (full — fullscreen has room, no 1-line clamp).
- All thought items (priority-sorted via the shared view-model), full text.
- All subclusters as nested cards, each with their thoughts (fullscreen has the height budget inline lacked).
- **Full tag PILLS** (built with Claude tokens — surfaces/text/border tokens, not hardcoded colors) — deferred from increment 1 to here.
- Responsive layout (e.g. `auto-fit, minmax(...)`), everything expanded, no accordion, page scrolls naturally (no nested-scroll hacks).

This RESOLVES the increment-1 redundancy: in fullscreen everything is visible, so no overflow action / whole-board reload is needed. The inline accordion's overflow action stays as-is where fullscreen isn't available.

## Performance / supported scale (production target — Claude Code must design to this)
Fullscreen renders the ENTIRE board, so it must have an explicit scale target, not "render everything and hope":
- **Must remain responsive (no visible jank on interaction/scroll, reasonable initial render) for boards up to a stated target — propose and record the target** (e.g. ~30 clusters / ~500 thoughts / ~100 subclusters as a starting point; adjust to realistic MindSort board sizes).
- Beyond that target, degrade gracefully: virtualize long lists, or cap rendered depth with a clear "large board" affordance — do NOT silently render an unbounded DOM that janks.
- State the chosen target and the degradation strategy in the report. Include one large-board manual test (below).

## Tokens / typography / compliance
- Host tokens only; match the existing `var(--token, #hex)` fallback pattern (same as increment 1 — no fallback-free/fallback-ful mix, no repo-wide changes).
- fontWeight 400/500 only. Monochrome outlined SVG icons only — NO emoji, NO unicode glyphs (this bug appeared 3× in increment 1; do not reintroduce).
- **Read-only — hardened.** Prohibit ALL of: mutation/CRUD tool calls; optimistic local mutations; hidden or latent edit handlers; keyboard shortcuts that perform edits; any accidental mutation tool call. Fullscreen is strictly display. Editing goes through the model, never the widget.

## Accessibility (WCAG AA)
- Keyboard-operable expand and minimize (Enter/Space); visible focus ring (`--color-ring-primary`).
- **Focus restoration:** on exiting fullscreen (minimize OR host-initiated exit), return focus to the control that opened fullscreen (the "Open full board" button) or a sensible inline anchor — do not drop focus to document body.
- Priority conveyed by badge TEXT, not color alone. Tag pills have accessible text. Respect `prefers-reduced-motion` on any transition. Keyboard-only users can traverse the entire fullscreen board.

## Mandatory: WIDGET_VERSION bump — and VERIFY the URI actually changed
Any widget-bundle change REQUIRES bumping `WIDGET_VERSION` in `handlers/resources_dupl.py` so the widget URI changes and Claude re-fetches instead of serving the cached bundle (this is why increment 1 rendered stale). It flows through the single `WIDGET_URI` definition to both the resource handler and `tools_list_dupl.py` injection atomically.
- State the current value first (it is NOT "1" anymore — increment 1's cache fix already bumped it; read the current value), then bump per `OPERATIONS_PREDEPLOY.md`.
- **VERIFY the resulting `WIDGET_URI` string actually differs** from the previous one (people bump the constant but accidentally produce the same URI). State old URI and new URI in the report — not just the version number.

## Explicitly OUT of scope
- Any CRUD / mutation / new tool / backend contract (read-only; no new server tools).
- Any bet on mobile fullscreen working today (host-gated; mobile stays on the inline accordion until the host advertises fullscreen).
- Changes to inline accordion behavior (frozen except for the shared view-model extraction and shared display-mode plumbing).
- Changes to response adapter / injection logic (only the `WIDGET_VERSION` line in `resources_dupl.py`).
- Backend/`clarity/` changes; importing/porting OpenAI components or styling.

## Tests

**Component/render (jsdom — logic/DOM/a11y):**
1. Capability: app declares `availableDisplayModes: ['inline','fullscreen']`. *Catches:* missing capability → host never offers fullscreen.
2. Enter: clicking "Open full board" switches to fullscreen via local state; assert it does NOT call `requestDisplayMode` on entry (matches current PG). *Catches:* wrong entry mechanism.
3. Minimize: calls `requestDisplayMode({mode:'inline'})`, updates from returned mode, try/catch present; on rejection, mode reconciles from host (no wedge). *Catches:* broken exit, unhandled rejection, wedged UI.
4. Host sync: `onhostcontextchanged` with `displayMode:'inline'` returns to inline, resets `hostFullscreen`, restores focus. *Catches:* desync + focus loss on host-initiated exit.
5. Capability gating: with host `availableDisplayModes` LACKING `'fullscreen'`, the fullscreen affordance is NOT rendered; WITH it, it is. (Gate on capability, not platform string.) *Catches:* dead button where host can't honor fullscreen.
6. Shared view-model: inline and fullscreen render from the same transform — assert both reflect the same sort/grouping given one fixture (e.g. change fixture order, both views reorder identically). *Catches:* duplicated/divergent transform logic.
7. Content: fullscreen renders all clusters, all thoughts, subclusters as nested cards, tag PILLS; inline still shows the accordion with NO pills. *Catches:* content regressions, pills leaking inline.
8. Read-only: no mutation controls, no CRUD calls, no edit keyboard handlers in fullscreen. *Catches:* CRUD creep / hidden mutations.
9. Native close: `hostFullscreen` true → app renders no own close/minimize header; false → it does. *Catches:* duplicated native close.
10. No `@openai/apps-sdk-ui`, no `window.openai`, no emoji/glyph icons, no new hardcoded colors. *Catches:* dep leak, icon-compliance regression.

**Manual, real-host (the acceptance gate — jsdom can't verify display-mode switching, layout, or performance):**
11. Claude host that advertises fullscreen (desktop/web): board → "Open full board" → enters fullscreen; full board renders (all clusters/thoughts/subclusters/tag pills); read-only; scrolls naturally; native close works and is not duplicated; minimize returns to inline and focus returns to the opener.
12. Claude host WITHOUT fullscreen (mobile): "Open full board" affordance absent; inline accordion unchanged.
13. **Large board:** load a board at/above the stated scale target; confirm responsiveness (no jank on scroll/interaction) or the graceful-degradation affordance; record observed behavior.
14. **Zoom/viewport/keyboard:** browser zoom 200%; a very narrow desktop window; keyboard-only traversal through the entire fullscreen board; dark mode legibility; screen reader announces priority + tag text.
State observed behavior for 11–14 in the report.

## Definition of Done
- [ ] `availableDisplayModes: ['inline','fullscreen']` declared (advertises support; host decides).
- [ ] Fullscreen entry reproduces current PG (local state), OR a newer SDK pattern was found and SURFACED (not silently chosen).
- [ ] Minimize via `requestDisplayMode({mode:'inline'})` with try/catch; reconciles from returned mode / host context; never wedges.
- [ ] Fullscreen affordance gated on `hostContext.availableDisplayModes.includes('fullscreen')` (capability, NOT platform); absent where unavailable; no dead button.
- [ ] All failure/unexpected-state paths handled (unavailable, rejected, host-exit, mid-render context change); host context is authoritative, local state only reconciles toward it.
- [ ] ONE shared board view-model; inline + fullscreen both consume it; no duplicated sort/group/normalize.
- [ ] Fullscreen renders full read-only board (clusters, priority-sorted thoughts, nested subcluster cards, tag PILLS) reproducing the OpenAI INFORMATION HIERARCHY in Claude tokens (no OpenAI components/styling imported).
- [ ] Explicit performance/scale target stated; graceful degradation beyond it; large-board test run.
- [ ] Native fullscreen close not duplicated (gated on `!hostFullscreen`, verified from PG source).
- [ ] Inline accordion unchanged; no tag pills inline; its tests still pass.
- [ ] Tokens-only with existing fallback pattern; fontWeight 400/500; monochrome SVG icons only.
- [ ] Read-only hardened: no CRUD, no optimistic mutations, no hidden edit handlers, no edit keyboard shortcuts.
- [ ] A11y: keyboard expand/minimize, focus ring, FOCUS RESTORATION on exit, textual priority, accessible tag text, reduced-motion, full keyboard traversal.
- [ ] `WIDGET_VERSION` bumped; old + new URI STRINGS stated and verified different.
- [ ] Tests 1–10 pass (each with its bug-caught line); manual 11–14 run and recorded.
- [ ] `OPERATIONS_PREDEPLOY.md` read before commit (esp. Widget Bundle Changes).
- [ ] No change outside `widget-react/` and the `WIDGET_VERSION` line in `resources_dupl.py`.
- [ ] Report ends with commit hash (review verifies against `git show <hash>:<path>`).

## Post-deploy (part of this increment — "committed ≠ live", per increment 1)
1. Bump version, commit, DEPLOY MindSort-Claude on Render (Manual Deploy); confirm the deploy is live for the new commit hash.
2. FRESH Claude conversation (new URI busts cache; no reconnect needed): on a fullscreen-capable host → "Open full board" → fullscreen renders and minimizes correctly, focus returns.
3. Mobile → confirm no fullscreen affordance, accordion intact.
4. Not done until seen working on prod. Record the prod observation (including large-board behavior if testable) in the report.

## Note
This closes the MindSort-Claude widget-display work (inline accordion + host-gated fullscreen). After it ships and is verified on prod, the remaining MindSort submission gate is the privacy-policy / legal pages in Framer — not engineering.
