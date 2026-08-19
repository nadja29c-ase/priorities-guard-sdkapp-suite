# Increment: Inline loading skeleton (fix M20)

**Product:** MindSort — **Claude connector only.** Widget: `mcp_server/mindsort_claude/widget-react/`.
**Type:** Widget (React + CSS) change. **Widget-bytes change → rebuild + `WIDGET_VERSION` bump + cache-bust.**
**Blast radius:** **MindSort-Claude only.** No shared `clarity/` code, no OpenAI surface, no server/handler changes.
**Reference implementation:** PG-Claude already solved this (`priority_guardian_claude/widget-react/src/App.tsx` `!isInitialized` branch + `main.css` `.pg-skeleton-bar`). **Copy and Adjust, Never Rewrite** — but the two widgets have different inline layouts, so the *structure* being mirrored differs. See §3.

---

## 1. Problem (verified against source)

The inline loading state (`App.tsx`, the `!isInitialized` early return) is a single centred `<div>` with `padding: '24px'` and the literal text **`Loading...`**. It is correctly **not** a spinner, but M20 requires more: *"Loading states: skeleton screens, not spinners for inline content. **Match the layout structure of the final content** so the transition feels seamless."* A centred text block does not match the final layout — so M20 is only partly met. Requirement ID: **M20** (`DOC-CONSTRAINT`, binding via Policy §3H).

---

## 2. Desired outcome

Replace the `Loading...` text block with a **skeleton that mirrors the inline card's real layout**: the header row, a small number of cluster-row placeholders, and the footer. The skeleton must read as a loading affordance, not a broken/empty card, and must degrade correctly under reduced-motion and for screen readers.

---

## 3. What to mirror — MindSort's inline layout, NOT PG's

⚠️ **Do not copy PG's skeleton markup verbatim.** PG mirrors *its* inline layout (priority cards with badge circle + name + content bar). MindSort's inline `<main>` is structurally different, and a skeleton that mirrors the wrong layout fails M20's "match the final content" clause just as surely as the text block does. Mirror **MindSort's** inline structure, which is (verified against the inline `<main>` in `App.tsx`):

- **Header row:** title (`Your MindSort AI Board`) on the left, count summary on the right.
- **Cluster list:** a vertical stack of `ClusterRowToggle` rows. Each real row is: a left accent bar, an optional priority badge, the cluster name, an optional tag icon, and an item count — inside a bordered/rounded button at `minHeight: LAYOUT.collapsedRowH` (48px), separated by `LAYOUT.collapsedRowGap` (6px).
- **Footer row:** overflow indicator on the left, "Open full board" button on the right.

**Skeleton shape to render (the COMMON SUBSET — forgiving direction):**
- A header placeholder: one short bar (title) + one shorter bar (count), matching the header's space-between layout.
- **3 cluster-row placeholders** (a middle-ground count; real inline caps at `MAX_INLINE_ROWS`=5 collapsed, but showing 3 avoids implying a specific board size). Each placeholder mirrors the *minimal* row: the rounded/bordered shell at `collapsedRowH` height with a left accent stripe, containing one name bar and one short count bar. **Do NOT** render badge or tag placeholders — those are optional on real rows, so omitting them is the forgiving direction (a real row *gains* a badge/tag rather than a skeleton showing one that then vanishes). Apply the reasoning PG documented for its Deadline/Flexible subset.
- A footer placeholder: **one** short bar where the "Open full board" button sits. This is the common-subset choice, consistent with the badge/tag reasoning above: the footer's left slot (the `+N more clusters` overflow indicator) is **conditional** — it renders only when `boardOverflow > 0` — while the "Open full board" button is the always-present element. Skeleton the always-present element and let the optional indicator appear on load (forgiving direction). Do not render a left-side placeholder for a slot that is frequently empty.

Match the real inline card's container: `width: 100%`, `background: var(--color-background-secondary, #F5F4ED)`, `borderRadius: var(--border-radius-xl, 12px)`, the `touchAction`/`overscrollBehavior` siblings, and the collapsed-row gap between placeholders.

---

## 4. Hard constraints (these are where it goes wrong)

1. **Platform-agnostic — do NOT read `hostContext.safeAreaInsets` or `platform` in the skeleton.** The `!isInitialized` branch renders **before** `connect()` resolves, so host context is not yet known. The M3 inset fix (77eb332) applies to the inline `<main>` that renders *after* connect; the skeleton must use flat padding (mirror the real card's `16px` base) and must not attempt inset-awareness. Copying the M3 padding expression into the skeleton would read undefined-derived state. (PG documents this exact decision.)
2. **Pulse the BARS, never the container.** The animation goes on the placeholder bars only. A pulsing shell reads as a rendering fault, not loading. (PG's `.pg-skeleton-bar` comment states this.)
3. **Honour `prefers-reduced-motion: reduce`** — animation `none` under that query. Non-negotiable for M2 (accessibility) and it's in the reference.
4. **Accessibility — announced status where it can announce.** The skeleton `<main>` carries `aria-busy="true"`. Put the loading message in a `role="status"` region (implicit polite live region) wrapping an `sr-only` "Loading" string, with the **visual** placeholder tree `aria-hidden="true"` so the bars are not traversed. important nuance, do NOT overclaim this: a live region announces when its contents **change while it is already in the accessibility tree**. At FIRST MOUNT the skeleton is the app's very first render (`isInitialized` starts false), so the region mounts with its text already present and then unmounts when the board arrives — it never changes while mounted, and NVDA/JAWS/VoiceOver commonly do **not** announce that. `role="status"` IS correct and load-bearing for the RE-ENTRY case (e.g. `handleViewRemainingContent` sets loading again while the widget is already mounted — a genuine content change a live region announces), and it costs nothing, so implement it. But **first-mount announcement is not guaranteed by this mechanism** and can only be settled with a real screen reader — the report must record that rather than claim the skeleton announces on first load. (A plain "Loading" string is fine — no new i18n system required; MindSort already has `.sr-only` in `main.css`.)
5. **Use host tokens for all colours** (M1/M18) — placeholder fill via `var(--color-border-tertiary, …)` or an equivalent host token with fallback, exactly as the real rows do. The requirement is that the skeleton **adapts to dark mode automatically** because it references host tokens — that behaviour is what §6/§7 verify, not the textual presence or absence of a `#`.
6. **No new dependency, no shared file, no OpenAI file, no server file.** Only `App.tsx` (the `!isInitialized` branch) and `main.css` (the new skeleton class) change.

---

## 5. CSS (new class in `main.css`)

Add a MindSort-named skeleton class mirroring PG's proven one — an **opacity pulse**, not a translate/shimmer (PG's is `pg-skeleton-pulse`, 1.6s ease-in-out infinite, opacity 1 → 0.45 → 1), applied to bars, with the reduced-motion override. Name it distinctly for this widget (e.g. `ms-skeleton-bar` / `ms-skeleton-pulse`) — do not reuse the `pg-` prefix. Keep the existing `main.css` content untouched; append the animation + class + reduced-motion block.

---

## 6. Tests (separate unit from integration)

The skeleton is presentational, so tests assert structure/attributes, not pixels.

**Discriminating (fails before, passes after):**
- Render `App` in its pre-initialised state (no tool result delivered) and assert the loading output is a **skeleton**, not the `Loading...` text — e.g. assert the placeholder container exists and the literal string `Loading...` is **absent** from the visible tree. This fails against current code (which renders `Loading...`) and passes after.

**Unit / DOM:**
- The skeleton root has `aria-busy="true"`, and the loading message is inside a `role="status"` region (assert the status region exists and carries the loading string).
- The visual placeholder subtree is `aria-hidden="true"`.
- Exactly the intended number of cluster-row placeholders render (3), so a regression that renders 0 or an unbounded count is caught.
- **Token binding (behavioural, not syntactic):** assert the placeholder fill resolves to the intended host token (e.g. the style/class references `--color-border-tertiary` or the agreed token), NOT a regex over the style string for `#`. The point is that the colour is host-token-driven so it adapts to theme — test that binding, not the presence of a hash character. A hex-string regex is brittle, tests syntax rather than behaviour, and would pass a *wrong* token while failing a correct reformat.

**Do not** assert the animation itself (jsdom won't run it); the reduced-motion behaviour is CSS and is covered by keeping it identical to the proven PG rule.

---

## 7. Build / deploy / verify
- Widget-bytes change → **rebuild** (Vite), **verify the built artifact changed**, **bump `WIDGET_VERSION`** in `handlers/resources_dupl.py` (confirm live value first — it was `"10"`, and the M3 increment 77eb332 may bump it to `"11"`; **sequence-check so this doesn't collide** — read the current committed value and bump from there). Report old→new.
- Read `doc/OPERATIONS_PREDEPLOY.md` before deploying.
- **`committed ≠ live`.** Post-deploy: trigger a tool call that shows the widget and confirm the skeleton renders (mirrors the card layout, pulses on bars, no `Loading...` text) and transitions cleanly to the real board. A brief throttle may be needed to observe it; if it's too fast to see, confirm via the pre-init render path rather than claiming it.
- **Dark-mode acceptance (M1 — required, not optional).** This is a NEW rendering surface, so verify the skeleton in **both** light and dark themes: the placeholder bars must be visible and correctly tinted in dark mode via the host tokens (not washed out or invisible). "Uses tokens" is the mechanism; "renders correctly in dark" is the requirement — confirm the latter, don't infer it from the former.

---

## 8. Report requirements
1. **Commit hash** for the reviewed round.
2. Diff of the `App.tsx` `!isInitialized` branch and the `main.css` addition.
3. Confirmation the discriminating test failed-before / passes-after; other test results.
4. Confirmation of the §4 constraints: **no `safeAreaInsets`/`platform` read in the skeleton**, pulse-on-bars-not-container, reduced-motion honoured, `aria-busy` + `sr-only` + `aria-hidden` present, tokens-only colours.
5. `WIDGET_VERSION` old→new and confirmation it sequences correctly after the M3 bump (no collision).
6. Explicit confirmation **no `clarity/`, OpenAI, or server file changed**.
7. Explicit **"what I did NOT verify"** (e.g. live in-client skeleton render if not yet deployed; the animation visually, since jsdom can't run it).
