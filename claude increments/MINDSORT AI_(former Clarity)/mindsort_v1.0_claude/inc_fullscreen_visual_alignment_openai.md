# Increment 3: MindSort-Claude fullscreen — visual alignment with the OpenAI MindSort board

**App:** MindSort AI for Claude (`mcp_server/mindsort_claude/`). Anthropic MCP connector, fullscreen widget view.
**Type:** PURELY PRESENTATIONAL. Align the fullscreen board's visual design and structure with the OpenAI MindSort board, so the two read as the same product. NO logic, data, display-mode, or behavioral changes.
**Touches:** `mcp_server/mindsort_claude/widget-react/src/App.tsx` (fullscreen components only), PLUS the `WIDGET_VERSION` line in `handlers/resources_dupl.py`. Nothing else.

**Status: QUEUED — not urgent.** Increments 1 (inline accordion) and 2 (fullscreen full board) are shipped and verified working on prod. This increment fixes a cosmetic mismatch only.

## Why this exists (and why the mismatch happened)
The increment-2 briefing instructed: use the OpenAI board as reference for "information hierarchy and content organization ONLY... NOT a source for implementation, components, APIs, or styling." That was intended to prevent *code* coupling to OpenAI's Tailwind/SDK components — but it was too broad, and it licensed inventing a different visual design. The result: the Claude fullscreen board works correctly but doesn't look like the OpenAI MindSort board.

**Corrected instruction for this increment: reproduce the OpenAI board's VISUAL DESIGN and STRUCTURE. Deviate ONLY where Anthropic compliance requires it, and state each deviation with its reason.** Implement with Claude tokens and inline styles (no OpenAI SDK, no Tailwind) — the *implementation* stays Claude-native, the *visual result* should match.

## Reference source (read before implementing)
`mcp_server/clarity/widget-react/src/components/{ClusterCard,SubclusterCard,ThoughtItem,PriorityBadge,TagPill}.tsx` — READ ONLY, do not modify, do not import.
Target file: the fullscreen components in `mcp_server/mindsort_claude/widget-react/src/App.tsx`: `FullscreenClusterCard`, `FullscreenSubclusterCard`, `FullscreenThoughtItem`, `TagPill`.
Before commit: read `OPERATIONS_PREDEPLOY.md` ("Widget Bundle Changes").

---

## THE SPEC — required visual changes

### 1. Section order: TAGS MOVE TO THE BOTTOM (most visible mismatch)
OpenAI `ClusterCard` order is: header → **summary → thought items → subclusters → tags LAST** (`mt-auto pt-4`).
Claude currently renders tags immediately after the header. **Move tag pills to the END of the cluster card**, after subclusters. Same for `FullscreenSubclusterCard`: thoughts first, tags last (OpenAI: `mt-auto pt-2`).

### 2. Thought item: LEFT PRIORITY BAR, no bullet, badge AFTER text
OpenAI `ThoughtItem` is a bare `<li>` with a left border and no card background:
- Prioritized: `border-l-4` with the strong border color. Unprioritized: `border-l-2` with the default border color.
- Padding: `pl-3 py-1` (normal) / `pl-2 py-0.5` (small, used inside subclusters).
- Text first, then priority badge AFTER the text.
- No background fill, no border radius, no bullet glyph/icon.

Claude currently renders: white card with border-radius, a circle SVG bullet, badge BEFORE text. **Change to match:** remove the bullet entirely, remove the card background/radius, add the left priority bar, move the badge after the text, match the padding. Use `size="small"` equivalent (smaller text/padding) for thoughts inside subclusters, as OpenAI does.

### 3. Count display: outlined pill with the NUMBER only
OpenAI uses the `Badge` component (`color="secondary" variant="outline" size="sm"`) containing **just the number** (e.g. `5`), with an `sr-only` span carrying "5 items" for screen readers.
Claude currently renders plain text `"5 thoughts"`. **Change to:** a small outlined pill (token border + secondary text) containing only the number, plus visually-hidden full text for screen readers. Applies to both cluster and subcluster headers.

### 4. Cluster card container
Match OpenAI `ClusterCard`: `rounded-2xl` (≈16px radius), `p-5` (20px padding), `shadow-lg`, `min-h-[120px]`, `flex flex-col`.
Prioritized clusters: `border-l-4` + extra left padding (OpenAI uses `pl-6` when prioritized). Unprioritized: normal border, no left accent.
Claude currently: 12px radius, 16px padding, no shadow, no min-height. **Match the OpenAI values** using Claude tokens (`--border-radius-*`, `--shadow-*` if available; otherwise an equivalent token-based shadow).

### 5. Subcluster card container
Match OpenAI `SubclusterCard`: `rounded-lg` (≈8px), `p-3` (12px), surface background, and **`border-l-4` ONLY when prioritized** — otherwise a normal subtle border with NO left accent.
Claude currently always renders a 3px left border regardless of priority. **Make the left accent conditional on priority.**

### 6. Header layout
Match OpenAI: `flex items-start justify-between gap-2`, name + priority badge on the left (name first, badge after), count pill on the right. Cluster name `text-sm` with `break-words min-w-0`; subcluster name `text-sm font-medium`.

### 7. Summary — KEEP Claude's full text (deliberate deviation)
OpenAI clamps to 100 chars (`truncateText(summary, 100)`) because its card is tight. Claude fullscreen has room. **Keep full summary text, no clamp.** Record this as an intentional product deviation (not a compliance one) in the report.

---

## COMPLIANCE DEVIATIONS — keep these, do NOT copy OpenAI here
State each in a code comment where it applies:
1. **fontWeight:** OpenAI uses `font-semibold` (600). Anthropic widgets permit **400/500 only**. Keep 500. (Guideline: typography.)
2. **Collapse indicators:** OpenAI uses Unicode `▲`/`▼`. Anthropic requires **monochrome outlined SVG icons** — keep SVG chevrons. No Unicode glyphs anywhere. (This bug has appeared 5× in this workstream; do not reintroduce.)
3. **Styling implementation:** OpenAI uses Tailwind + `@openai/apps-sdk-ui` components (`Badge`). Claude widgets must use **Anthropic tokens + inline styles**; no OpenAI SDK, no Tailwind, no `window.openai`. Reproduce the visual result, not the implementation.
4. **Focus ring:** OpenAI `--color-ring`; Claude uses `--color-ring-primary` via boxShadow. Keep Claude's.
5. **Collapsible cards:** OpenAI cards are collapsible on mobile (`isCollapsible`/`defaultCollapsed`). Claude fullscreen renders everything expanded by design (inline accordion covers progressive disclosure). **Do NOT add collapsibility to Claude fullscreen.**
6. **Color values:** use Claude tokens with the existing `var(--token, #hex)` fallback pattern. Do not port OpenAI's Tailwind color classes.

## Explicitly OUT of scope
- Any change to the INLINE accordion (increments 1–2 are frozen; inline stays exactly as shipped).
- Any logic, data, sorting, capability-gating, display-mode, focus, or virtualization change.
- Any CRUD/mutation; read-only stands.
- Importing or porting OpenAI components, Tailwind, or the OpenAI SDK.
- Adding collapsibility to fullscreen cards.
- Changes to `clarity/` (reference only — READ ONLY), backend, adapters, or tool handlers.

## Mandatory: WIDGET_VERSION bump + verify the URI changed
The bundle changes, so bump `WIDGET_VERSION` in `handlers/resources_dupl.py` (currently **"3"** → **"4"**). **Verify the emitted `WIDGET_URI` string actually differs** (`ui://mindsort-claude/dashboard-v3.html` → `...v4.html`) — state OLD and NEW URI strings in the report, not just the version number. Skipping this makes the change render stale on prod (this happened in increment 1).

## Tests
Purely visual changes still need behavioral guards where the DOM structure changes:
1. **Tags render LAST** in the fullscreen cluster card — assert tag pill text appears after subcluster content in DOM order. *Catches:* section-order regression (the main fix).
2. **Thought item has no bullet icon and badge follows text** — assert no bullet `<svg>` inside the thought `<li>`, and that the priority badge element follows the text node. *Catches:* reverting to bullet/badge-first.
3. **Count is a pill containing only the number**, with accessible full text available. *Catches:* reverting to `"N thoughts"` plain text.
4. **Subcluster left accent only when prioritized** — render one prioritized and one unprioritized subcluster; assert the accent style differs. *Catches:* the always-on border.
5. **No Unicode glyphs / no OpenAI imports** — assert no `▲▼·→›•` characters in rendered output; module imports cleanly. *Catches:* the recurring glyph regression.
6. **All existing increment 1–2 tests still pass UNCHANGED.** If any needs its expected values altered, the change was NOT purely visual — STOP and surface it. *Catches:* accidental behavioral change.

**Manual (acceptance):** deploy, fresh conversation, open fullscreen on a real board and **compare side by side with the OpenAI MindSort board**. Confirm: same card shape/spacing/shadow, tags at the bottom, thoughts as left-bar rows with badge after text, count pills, subcluster accent only when prioritized. Record the comparison.

## Definition of Done
- [ ] Tags render LAST in both cluster and subcluster cards.
- [ ] Thought items: left priority bar (4px prioritized / 2px not), no bullet, no card background, badge AFTER text, OpenAI padding; small variant inside subclusters.
- [ ] Count shown as outlined pill with number only + screen-reader full text.
- [ ] Cluster card: OpenAI radius/padding/shadow/min-height; left accent + extra left padding when prioritized.
- [ ] Subcluster card: OpenAI radius/padding; left accent ONLY when prioritized.
- [ ] Header layout matches (name + badge left, count pill right).
- [ ] Summary stays full-text (documented deviation).
- [ ] All 6 compliance deviations preserved and commented (400/500 weights, SVG icons, Claude tokens/inline styles, ring token, no collapsibility, token fallbacks).
- [ ] NO Unicode glyphs anywhere; no OpenAI SDK/Tailwind imports.
- [ ] Inline accordion untouched; increments 1–2 tests pass unchanged.
- [ ] `WIDGET_VERSION` 3→4; OLD and NEW URI strings stated and verified different.
- [ ] Tests 1–6 pass, each with its bug-caught line.
- [ ] `OPERATIONS_PREDEPLOY.md` read before commit.
- [ ] No change outside `widget-react/src/App.tsx` and the `WIDGET_VERSION` line.
- [ ] Report ends with commit hash (review verifies against `git show <hash>:<path>`).

## Post-deploy
Deploy MindSort-Claude; fresh conversation (new v4 URI busts cache); open fullscreen; compare side-by-side with the OpenAI board and record the result. Not done until seen on prod.

## Note
This is cosmetic polish on a working feature. MindSort's submission gate is the privacy-policy / legal pages in Framer — not this increment, and not any engineering.
