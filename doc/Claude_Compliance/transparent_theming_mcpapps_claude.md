# Blend your MCP App with Claude's theme — transparent theming

**Source:** `https://claude.com/docs/connectors/building/mcp-apps/transparent-theming`
**Fetched:** 2026-08-04 — direct fetch.
**Feeds:** compliance master §4N. The master is **not** yet rewritten against this.

---

## Part 1 — Requirements (4)

This page is **mechanism, not obligation**. It is a how-to for blending, and nothing on it is
independently gating. Obligation-shaped items:

| # | Requirement | Language |
|---|---|---|
| T1 | `html, body { margin: 0; background: transparent; }` — any opaque background on either hides the chat surface | imperative: "Explicitly set both" |
| T2 | `<meta name="color-scheme" content="light dark" />` in the document head, and **keep it** even though `applyDocumentTheme` sets it at runtime — the tag covers first paint | imperative + "Keep the tag" |
| T3 | CSP `resourceDomains` **must** include `https://assets.claude.ai` for `applyHostFonts` to load the `@font-face` files | the page's only literal "must" — conditional on wanting host fonts |
| T4 | **Register the `hostcontextchanged` listener before you connect**, so an early update isn't missed | imperative |

`prefersBorder: false` is **recommended for portability**, not required — "Claude web's default is
already borderless, but other hosts differ, so being explicit keeps your app portable."

**Why this page matters despite being non-gating:** it is the mechanism for discharging design
guidelines **M1** — *"All views must support both light and dark themes… Never hardcode
colors."* That is a genuine MUST, recorded in master §4K. §4N should say so rather than read as
optional polish.

### `hostContext` fields relevant to theming

| Field | Contents |
|---|---|
| `theme` | `"light"` or `"dark"` |
| `styles.variables` | `--color-background-*`, `--color-text-*`, `--color-border-*`, `--color-ring-*`, `--font-*`, `--border-radius-*`, `--border-width-*` |
| `styles.css.fonts` | `@font-face` rules for Anthropic Sans, served from `https://assets.claude.ai` |

**That is the complete list.** The master currently writes it as
"(`--color-background-*`, `--color-text-*`, etc.)" — the `etc.` hides four categories.

### The three SDK helpers, plus the React wrappers

- `applyDocumentTheme(theme)` — sets `<html data-theme>` and root `color-scheme`, so
  `[data-theme="dark"]` selectors and `light-dark()` values resolve.
- `applyHostStyleVariables(variables)` — writes every `styles.variables` entry onto `:root`.
- `applyHostFonts(fontCss)` — injects the host's `@font-face` rules once.
- `useApp(options)` — creates and connects the `App` instance in React.
- `useHostStyles(app, hostContext)` — applies all of the above and re-applies on
  `hostcontextchanged`.

### Security caveat, verbatim

> `resourceDomains` also adds the listed origins to `script-src` and `style-src`, so keep it to
> origins you trust to serve executable code; prefer bundling third-party fonts into your
> widget rather than allowlisting public CDNs.

### On `light-dark()`

> Claude's token values use CSS `light-dark()`, so once `applyDocumentTheme` has set the root
> `color-scheme`, every `--color-*` variable resolves to the right variant without any
> `[data-theme]` selectors on your side.

The page's own fallback example is
`color: var(--color-text-primary, light-dark(#141413, #faf9f5))` — the **fallback** carries
`light-dark()` too, not only the token.

---

## Part 2 — PG-Claude conformance, verified 2026-08-04 from source

| # | Requirement | PG-Claude | Evidence |
|---|---|---|---|
| T1 | Transparent html/body | ✅ | `widget-react/src/main.css:9-15` — `html, body { width:100%; margin:0; padding:0; background: transparent }`; `body` again at :28 |
| T2 | `color-scheme` meta tag | ✅ | `widget-react/pg-dashboard-claude.html:6`. **Durable** — that file is the Vite build *input* (`vite.config.ts:18`), so the tag survives rebuilds. Also present in the built, actually-served `widgets/pg-dashboard-claude.html:6` |
| T3 | `assets.claude.ai` in `resourceDomains` | ✅ **but hollow** | `handlers/resources_dupl.py:94` and `:118`, commented "Host font loading". The allowance is granted and the fonts inject — **nothing consumes them.** See below |
| T4 | Listener registered before connect | ⚠️ **unverified** | `onhostcontextchanged` is assigned at `App.tsx:144`, inside the `onAppCreated` callback (`:85`). Whether `onAppCreated` fires before `connect()` is SDK internals and was not read. PG also uses `useHostStyles`, which the page says re-applies on the event — so the React path likely covers it regardless |
| — | `prefersBorder` | set `false` | `resources_dupl.py:91, 115, 149` — all three `_meta.ui` blocks. **See the trade-off below.** |

### T3 is satisfied and hollow — PG pays for host fonts and never uses them

`resourceDomains: ["https://assets.claude.ai"]` exists specifically so `applyHostFonts` can load
Anthropic Sans, and `useHostStyles` does inject the `@font-face` rules. They are never referenced:

| Line | Declaration |
|---|---|
| `main.css:25` | `font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;` — hardcoded |
| `main.css:40` | `font-family: inherit;` — inherits the hardcoded stack |

**Verified total, not partial.** `grep -rn "font-sans\|--font-"` across the whole of
`widget-react/src/` returns nothing, and those two lines are the widget's *only* `font-family`
declarations. No component overrides it.

**What this costs.** The page's own security caveat is that `resourceDomains` also adds the origin
to `script-src` and `style-src`. PG has widened its CSP for a capability it does not exercise, and
renders in `system-ui` in every host regardless.

**Two valid closures, one wrong answer.** Either adopt the page's canonical form —
`font-family: var(--font-sans, system-ui, sans-serif)` — or drop `assets.claude.ai` from
`resourceDomains` and narrow the CSP back. The second is cheaper to ship. Keeping both the
allowance and the hardcoded stack is the only combination with cost and no benefit.

**Code fix not applied** — widget change, needs a rebuild and deploy; the decision is Nadja's.

### CSS fallbacks — single-value, not `light-dark()`

`main.css:29` is `color: var(--color-text-primary, #141413)`. The page's canonical form is
`var(--color-text-primary, light-dark(#141413, #faf9f5))`.

**Scope of the gap, stated precisely:** a fallback only applies when the custom property is
**absent** — i.e. when the widget renders outside a Claude host. Inside Claude,
`applyHostStyleVariables` sets the variables and the fallback is never used, so light/dark
correctness inside the host is unaffected. The gap is that PG's out-of-host rendering shows the
**light** value in dark mode.

The master currently calls this "acceptable but suboptimal". That understates it slightly —
the page now makes `light-dark()` the canonical fallback form — but "suboptimal" is the right
severity given it cannot affect in-host rendering.

---

## Part 3 — The `prefersBorder` trade-off, recorded once

This has been carried as two independent recommendations in two master sections. It is **one
decision with two consequences**, and PG sits in the gap.

**It is not a contradiction between the two pages.** This page recommends `false` *for
portability* and does not mention the mobile consequence. Design guidelines states the
consequence. The pages are consistent; this one is simply incomplete on its own.

| Source | What it says |
|---|---|
| **transparent-theming** (this page) | Set `prefersBorder: false` so the host doesn't wrap you in a bordered card. Claude web already defaults borderless; being explicit keeps you portable. |
| **design-guidelines** | If unspecified: borderless on web, **bordered on mobile**. In borderless mode content runs edge-to-edge with **no host padding**, so *"honoring `safeAreaInsets` becomes essential; the bordered card's built-in padding otherwise absorbs most of them."* |

**The decision:** setting `false` buys portability and costs you the mobile card padding. Having
taken it, honoring `safeAreaInsets` is no longer optional.

**Where PG stands** (verified, and the reason this needs recording rather than repeating):

- `prefersBorder: False` on all three `_meta.ui` blocks → borderless on **mobile too**
- `safeAreaInsets` applied **only** under `platform === 'mobile' && hostFullscreen`
  (`App.tsx:709`); the inline branch returns earlier and applies none
- `.left` / `.right` never read anywhere; horizontal padding hardcoded `16px`

**Impact unverified and plausibly nil.** 16px on all sides is not "flush against any edge", and
inline cards scroll with the conversation rather than sitting beneath a fixed composer, so
occlusion is transient where it exists at all. **The measurement that settles it** is logging
the `safeAreaInsets` the host actually reports for web inline, desktop inline and mobile
inline — if web reports zeros, there is nothing to fix. That is a diagnostic, not an increment.

---

## Part 4 — Diff against master §4N

| Master §4N claim | Status |
|---|---|
| Transparency CSS | ✅ correct, no drift |
| `color-scheme` meta tag + first-paint rationale | ✅ correct, no drift |
| `resourceDomains` also adds to `script-src` security caveat | ✅ correct, no drift |
| The three SDK helpers | ✅ correct, no drift |
| "Updates carry only changed fields" | ✅ correct, no drift |
| *"`styles.variables` (`--color-background-*`, `--color-text-*`, etc.)"* | ⚠️ **incomplete** — the `etc.` hides `--color-border-*`, `--color-ring-*`, `--font-*`, `--border-radius-*`, `--border-width-*` |
| *"PG status: uses `useHostStyles(app)` — correct ✅"* | ❌ **evidence is false.** `App.tsx:166` is `useHostStyles(app, app?.getHostContext())` — **two** args, with the comment *"must pass hostContext for dark mode"*. The verdict ✅ is right; the evidence cited describes the one-arg form the same section warns against |
| *"PG fallbacks single-value (not `light-dark()`) — acceptable but suboptimal"* | ⚠️ **accurate but under-scoped** — see Part 2. Confirmed true at `main.css:29`; add that it cannot affect in-host rendering |
| T4 (listener before connect) | ➕ **absent from §4N entirely** |
| `prefersBorder` trade-off | ➕ **split across §4K and §4N with the trade-off named in neither** |

**§4N should also state that it is the mechanism for design-guidelines M1**, a genuine MUST in
§4K, rather than reading as optional polish.
