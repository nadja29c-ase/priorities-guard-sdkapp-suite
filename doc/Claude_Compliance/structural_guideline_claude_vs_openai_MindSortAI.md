# Structural Guideline: MindSort AI for Claude vs. ChatGPT

**Created:** June 2026
**Status:** Decision record — pre-implementation. No code written yet.
**Last updated:** June 2026 — Added obligatory vs recommended classification per compliance master §4K/§4M/§4N.

---

## TL;DR — Obligatory vs Recommended

Classification based on fresh read of `claude_connectors_compliance_master.md`. The master explicitly labels items "(mandatory)" or uses softer verbs like "strongly recommended."

**CONSTRAINTS (per official design-guidelines):** Inline-card limits (auto-fit height with host clipping, ≤2 actions, ≤4-5 data points, no nested scroll), host CSS tokens, light+dark themes, WCAG AA, CSP, `ui.domain`, `availableDisplayModes`, SDK `App`/`useApp()` class, `app.connect()`, non-zero height, fullscreen constraints (if used).

**EXPLICITLY DEFERRABLE:** Instance supersession (§4M explicitly "not a submission blocker — defer to post-submission").

**STRONGLY RECOMMENDED (but not explicitly mandatory):** Transparency/theming (§4N "strongly recommended"), skeleton loading, type scale, `light-dark()` fallbacks, host font loading.

**Platform status (verified June 2026):**
- **Height:** Auto-fits to content, no published px limit (host caps and clips overflow)
- **4-5 data points:** Stated constraint — no "recommended" qualifier
- **Mobile fullscreen:** IS supported — app fills screen with chat input/nav overlaid
- **#61 widget rendering:** RESOLVED per owner confirmation

**Struck as phantom requirement:** §6 hash-parity test — not in compliance master, was invented by inference.

**Scope impact:** Obligatory-only saves ~20-25% of widget effort. The obligatory core (inline redesign + token theming) is ~75% and cannot be scoped out.

---

**Sibling document:** `structural_guideline_claude_vs_openai.md` (Priority Guardian).
**Relationship:** SIBLING, not parent. The PG doc is PG-specific and Increment-Claude-scoped. Its *strategy* (same repo, separate service, separate `resource` claim, widget bridge swap, response adapter) transfers; its *specifics* do not. MindSort has a different internal architecture (see Seam Map). Do not use the PG doc as a generic Claude-porting template.

**Decision in one line:** MindSort needs a *platform adapter*. OpenAI (`clarity/`) remains the leading source of truth; Claude imports by reference. It does **not** need a rewrite, a fork, or a core extraction.

---

## 0. Canonical Product Rule (anti-drift)

MindSort is **ONE product** delivered to two hosts.

**May differ by platform** (presentation/transport only):
- widget bridge (`window.openai.*` vs MCP Apps `ui/*`)
- response serialization / envelope
- `_meta` keys
- UI implementation and host-specific layout

**Must NOT diverge** (product behavior):
- clustering behavior
- prioritization logic and flow
- persistence semantics
- board semantics (clusters, subclusters, tags, priorities, ranks)
- `compute_content_hash`

Any platform-specific *behavioral* divergence (e.g. "Claude users get a different prioritization flow") is a **product fork** and requires an **explicit, recorded architecture decision** — not an incremental implementation choice. This rule exists to prevent `mindsort_openai != mindsort_claude` from happening silently over time. The default is parity; divergence is the exception that must be argued for.

---

## Evidence basis

This record is grounded in a full read (not skim) of MindSort's `clarity/` module: all 7 tools, the 3 core-logic files, server, both handlers, registry, base, widget `App.tsx`, `types.ts`, `config.py`, `resources.py`. Nothing below is inferred from a sample.

The OpenAI coupling is **shallow, uniform, and located in response serialization** across all seven tools. Core logic is platform-neutral. This is what makes "adapter + import-by-reference" the correct strategy — the Claude module adapts the response envelope; it doesn't duplicate the logic.

---

## Strategy (settled)

```
mcp_server/mindsort_claude/        # new, isolated
  server.py                        # own ASGI app, own middleware
  config.py                        # Claude callback URIs, CORS, resource URL
  handlers/
    tools.py                       # dispatcher = response-adapter chokepoint
    resources.py                   # Claude ui.domain (hashed), widget serving
  registry.py / tools_list.py      # Claude _meta (no openai/* keys)
  widget-react/src/                # new React impl, MCP Apps ui/* bridge
  # imports PURE logic by reference from clarity/ — see §2

mcp_server/clarity/                # OpenAI MindSort — LEADING source of truth
                                   # UNTOUCHED during review; Claude imports from here
```

There is no `mindsort_core/` extraction. Business logic stays in `clarity/` (OpenAI leading), and the Claude module imports it by reference. The `_dupl` suffix marks files that must diverge due to platform coupling (see §8.9).

Rejected alternatives: full copy-paste fork (permanent dual maintenance, tool drift — a known failure mode); Claude-first rewrite (re-deriving a working, in-review app for no logic gain). Both add cost without buying anything the adapter doesn't.

---

## 1. Seam Map

Every tool has the identical shape: **pure body** (validate → fetch board → transform → persist) followed by a **coupled tail** (build `_meta`, place `assistant_guidance` in `structuredContent`). The seam runs under the response envelope, in the same place in all seven tools.

| File | Pure | Coupled tail |
|---|---|---|
| `persistence.py` | 100% | — |
| `tools/board_utils.py` | 100% | — |
| `tool_logic.py::enrich_clusters` | 100% | — |
| `tool_logic.py::organize_thoughts` | logic pure | returns `{content, structuredContent}` envelope; guidance in `structuredContent` |
| `tools/organize_thoughts.py` | validation/repair/persist | tail `_meta`; guidance in `structuredContent` (incl. error paths) |
| `tools/edit_board.py` | all `_op_*` + dispatch | tail `_meta`; guidance in `structuredContent` |
| `tools/start_prioritization_flow.py` | validation/apply | tail `_meta`; guidance in `structuredContent` |
| `tools/load_saved_board.py` | fetch/enrich | tail `_meta`; guidance in `structuredContent` |
| `tools/read_board_before_editing.py` | fetch/enrich | tail; **mixed `_meta`** (`saved_board_hash` + `openai/toolInvocation/*`) |
| `tools/delete_my_data.py` | delete call | tail `_meta`; guidance in `structuredContent` |

**Consequence:** one transformation contract, applied once at the dispatcher, covers all tools. Not seven bespoke adapters.

---

## 2. Imported By Reference (zero duplication, zero drift)

The Claude module imports these **as-is** — they are platform-neutral:

- `clarity.persistence` — `persist_cluster`, `get_cluster`, `delete_cluster`
- `clarity.tools.board_utils` — `apply_priorities`, `clear_all_priorities`, `compute_content_hash`, `PriorityInput`, normalization helpers
- `clarity.tool_logic.enrich_clusters`

Tool `handle()` functions: imported by reference from `clarity/`. Their coupled tails (OpenAI-specific `_meta`, `structuredContent` envelope) are neutralized by the response adapter (see §4). This import-and-adapt approach is established by the full read of all seven handlers; the precise import boundary (which symbols, whether any handler needs a thin shim) is **validated at the first increment** (server bootstrap + dispatcher).

---

## 3. Platform-Specific (rebuilt for Claude, never shared)

- `server.py` — own ASGI app. ChatGPT-only middleware (`MCPContentTypeAndAcceptFixMiddleware` octet-stream/Accept fixes, `openai-apps-challenge` route, OpenAI CORS origins) does **not** carry over.
- `handlers/resources.py` — `ui.domain` derivation differs (see §5). Current MindSort uses `_extract_origin` (origin only) = OpenAI format = **wrong for Claude**.
- `registry` / `list_tools()` — current registry bakes `openai/outputTemplate`, `openai/toolInvocation/*`, `ui.visibility` into every tool's `_meta`. Claude registry emits MCP-Apps-standard `_meta` only.
- `widget-react/` — new React impl on `@modelcontextprotocol/ext-apps` (`ui/*` postMessage). Current `App.tsx` is pure `window.openai.*` (`toolOutput`, `setWidgetState`, `notifyIntrinsicHeight`, `openai:set_globals`) — not patchable, rewritten.
- `config.py` — Claude callback URIs, CORS origins, `resource` URL.

OAuth is shared and unchanged: same `/oauth/pg/*` provider, `clarity.write` scope, same backend. Adding Claude callback URIs is additive and is the only backend touch — deferred to after OpenAI review (Phase 2), exactly as PG sequenced it.

---

## 4. Response Adapter Contract

Single transformation at the dispatcher chokepoint (`mindsort_claude/handlers/tools.py`), applied to every `CallToolResult` before serialization:

1. **Guidance → `content`.** Move `assistant_guidance` out of `structuredContent` into a `content` text block.
   - Two input shapes exist: flat string (success paths) and nested `{"action","instruction"}` (some error paths).
   - **Normalization (decided):** render `instruction` only. **Drop `action`** — `ASK_CLARIFYING` etc. is internal control metadata, not model-facing prose.
2. **Strip `openai/*` from `_meta`:** `openai/outputTemplate`, `openai/toolInvocation/*`, `openai/widgetAccessible`, `openai/resultCanProduceWidget`.
3. **Discriminate, don't blanket-strip `_meta`.** Preserve non-OpenAI data keys. Canonical example: `read_board_before_editing` returns `_meta={saved_board_hash, openai/toolInvocation/*}` — keep `saved_board_hash`, strip the rest.
4. **Set top-level widget linking:** `_meta.ui.resourceUri` + `_meta.ui.domain` (see §5).
5. **Leave `structuredContent` as clean widget-only data.**

The shared `handle()` bodies are not modified. The adapter rewrites their output. This is the "import by reference + adapt tail" approach — the Claude module depends on `clarity/` as its source of truth for all business logic.

---

## 5. `ui.domain` (host policy — verify at deploy, do not treat as fixed)

Claude requires `_meta.ui.domain` as a widget↔server binding. **No final domain is baked into this doc** — both the value (deploy-dependent) and the *derivation rule itself* (host policy) are filled/confirmed at implementation time.

**Current formula (verified against Claude.ai docs, June 2026):**
```
MCP_RESOURCE_URL = <final deployed Claude MCP URL, INCLUDING /mcp path>
ui.domain        = sha256(MCP_RESOURCE_URL)[:32] + ".claudemcpcontent.com"
```

**Provenance / stability:** Anthropic's docs state the `ui.domain` format and validation rules are *determined by each host platform* and may change (hash-based subdomains, URL-derived patterns, or other formats). This formula is therefore a **verified-but-mutable host policy, not a spec guarantee.** It must be **re-verified against the live Claude MCP Apps docs at implementation time** before being committed to config. Do not treat this doc as the source of truth for the formula — the live docs are.

Verify at deploy:
```bash
node -e 'console.log(require("crypto").createHash("sha256").update(process.argv[1]).digest("hex").slice(0,32)+".claudemcpcontent.com")' "<MCP_RESOURCE_URL>"
```

Known failure (current rule): hashing origin-only (no `/mcp`) → "ui.domain mismatch", widget fails to render. MindSort's current `_extract_origin` is origin-only and must not be reused for Claude.

---

## 6. ~~Hash Parity Test~~ — STRUCK (phantom requirement)

**Status:** REMOVED. This requirement was originally stated as a "named gating requirement" but has **no basis in the Claude compliance master**. The compliance master (`claude_connectors_compliance_master.md`) contains no hash-parity requirement. The widget doesn't even compute a content hash — verified by reading `clarity/widget-react/src/utils.ts`. This was an invented requirement based on inference, not documentation.

**Why struck:** Per the living-artifacts rule, requirements must be grounded in canonical compliance sources. This one wasn't.

**Note:** The `compute_content_hash` invariant (Python ↔ TS parity) remains a *product quality concern* for saved-state detection accuracy, but it is **not a Claude directory submission requirement**. It can be addressed post-submission if needed.

---

## 7. Hard Constraints — Obligatory vs Recommended Classification

**Source:** Classification derived from fresh read of `claude_connectors_compliance_master.md` (June 2026). §4K explicitly labels inline-card constraints "(mandatory)". Items below are marked **[OBLIGATORY]** or **[RECOMMENDED]** based on whether the compliance master labels them mandatory/required vs. "strongly recommended" or softer verbs.

### Process constraints (project-specific)

- **Zero touches to `clarity/` during OpenAI review.** Everything in §3 is built in `mindsort_claude/`. The only backend change (Claude callback URIs) is additive and deferred to Phase 2 (post-approval).
- **GDPR / deletion:** `delete_my_data` ports cleanly (pure `delete_cluster` + tail). Anthropic directory submission also requires a data-deletion path — this satisfies it. Verify wording/contact (`mindsort@priority-guard.com`) at submission.

### Widget UI constraints (Claude directory — §4K)

**CONSTRAINTS** — per official design-guidelines (treat as submission requirements):

| Constraint | Source | Note |
|------------|--------|------|
| Inline height: auto-fits, no nested scrolling | Official docs | Host caps and clips overflow; no published px limit; escalate to fullscreen if scroll needed |
| Max 2 actions, at bottom | Official docs | |
| Max 4–5 data points | Official docs | Stated constraint — no "recommended" qualifier |
| No drill-ins/breadcrumbs/multiple views | Official docs | Single-screen only |
| No menus/popovers — visible controls only | Official docs | |
| 44×44pt touch targets (mobile) | Official docs | |
| Host CSS tokens for ALL structural elements | Official docs | `var(--color-*)` not hardcoded |
| Light + dark themes, tested | Official docs | |
| Icons need text alternatives (`aria-label`) | Official docs | |
| WCAG AA contrast, keyboard nav, assistive-tech | Official docs | |
| CSP declaration (`_meta.ui.csp`) | §4K | |
| `ui.domain` binding | §4K | Widget won't render without it |
| `appCapabilities.availableDisplayModes` | §4K | Required protocol |
| SDK `App`/`useApp()` class | §4M | Not hand-rolled bridge |
| `app.connect()`/`useApp()` mandatory | §4O | Technical must-have |
| Non-zero height required | §4O | Technical must-have |
| Fullscreen constraints (if implemented) | Official docs | No floating panels; own fullscreen button; composer visible |

**EXPLICITLY DEFERRABLE:**

| Constraint | Source | Note |
|------------|--------|------|
| Instance supersession (BroadcastChannel) | §4M | Explicitly "not a submission blocker" — defer to post-submission |

**STRONGLY RECOMMENDED** (not explicitly mandatory):

| Constraint | Source | Note |
|------------|--------|------|
| Transparent bg / `useHostStyles` / `prefersBorder:false` | §4N "strongly recommended" | Practically important for visual integration |
| Skeleton loading over spinners | design guidelines | Polish |
| Three-level type scale / two weights | design guidelines | Guidance |
| `light-dark()` CSS fallbacks | master | "acceptable but suboptimal" to use single-value fallbacks |
| Host font loading (`assets.claude.ai` in CSP) | master | "optional but expected" |

**Platform status (verified June 2026):**
- **Mobile fullscreen:** IS SUPPORTED — app fills screen with chat input/nav overlaid; keep critical UI in safe area
- **Widget rendering #61:** RESOLVED — widgets render for third-party connectors

**Strategic note:** Scoping to obligatory-only saves ~20-25% of widget effort (supersession + polish items). The obligatory core (inline redesign + token theming + a11y + CSP + ui.domain + display modes) is ~75% of the work and cannot be scoped out.

---

## 8. Compliance Gap Closure (Claude Directory)

Architecture-level compliance review against `claude_connectors_compliance_master.md`
surfaced gaps the earlier sections did not address. Each is solved in PG's Claude
module (`mcp_server/priority_guardian_claude/`) — MindSort mirrors those solutions.
None of these touch `clarity/` (all live in the new `mindsort_claude/` module), so
none risk the OpenAI review.

**Reference convention:** all gap fixes follow the `_dupl` marking convention (§8.9 below).

### 8.1 `title` annotation — REQUIRED, currently missing (rejection blocker)

`title` is mandatory on every tool (policy §5E; ~30% of rejections cite missing
annotations). **MindSort's `clarity/tools/base.py::ToolDefinition` has no `title`
field** — unlike PG's, which does. So MindSort cannot copy PG's
`tools_list_dupl.py` pattern (`title=tool_def.title`) verbatim.

**Decision required — title source.** Two options, pick one:
- **(a) Derive in the Claude registry** from the tool's snake_case name
  (`organize_thoughts` → "Organize Thoughts"). Zero touch to `clarity/`. This is
  what PG's Claude server originally did via a `_derive_title()` helper before PG
  later added a real `title` field to its shared `ToolDefinition`.
- **(b) Add a `title` field to `clarity/tools/base.py::ToolDefinition`** and set it
  per tool. **Blocked during OpenAI review** (touches `clarity/`). Defer to post-review.

**Chosen for now: (a)** — derive in `mindsort_claude`'s Claude registry, because it
is zero-touch to the in-review app. Mirror PG's `list_tools_for_claude()` in
`tools_list_dupl.py`: build `mcp_types.ToolAnnotations(title=..., readOnlyHint=...,
destructiveHint=..., openWorldHint=...)`. The derived title is the only deviation
from PG's pattern (PG reads `tool_def.title`; MindSort derives it until post-review
when a real `title` field can be added to the shared `ToolDefinition`).

Human-readable titles (derive or hardcode in the Claude registry map):
`organize_thoughts`→"Organize Thoughts", `edit_board`→"Edit Board",
`load_saved_board`→"Load Saved Board",
`read_board_before_editing`→"Read Board", `start_prioritization_flow`→"Set Priorities",
`delete_my_data`→"Delete My Data".

### 8.2 `destructiveHint` correctness — audit + Claude override

Policy §5E: any tool that writes/modifies data MUST have `destructiveHint: true`.
"Reversible" is irrelevant. **MindSort gap:** `start_prioritization_flow` has
`destructive_hint=False` (comment: "priorities are reversible") — it auto-persists
to DB, so under Anthropic's rule this is **wrong** and must be `true` for Claude.

**Pattern (from PG `tools_list_dupl.py`):** PG keeps the shared `ToolDefinition`
hint as-is (to preserve ChatGPT UX) and applies a Claude-only override map:
`_CLAUDE_DESTRUCTIVE_HINT_OVERRIDES = {"create_priority": True}`. MindSort does the
same — Claude registry override, shared definition untouched:

```
_CLAUDE_DESTRUCTIVE_HINT_OVERRIDES = {
    "start_prioritization_flow": True,   # writes/overwrites DB priorities
}
```

Verify the full set at implementation: every MindSort tool with
`read_only_hint=False` (`organize_thoughts`, `edit_board`,
`start_prioritization_flow`, `delete_my_data`) must surface
`destructiveHint: true` to Claude. `organize_thoughts`/`edit_board`/`delete_my_data`
already have `destructive_hint=True` in the shared def; only
`start_prioritization_flow` needs the override.

### 8.3 Origin-header validation — REQUIRED, currently absent (security-review blocker)

Hard requirement (master §4E, submission checklist): server must validate the
`Origin` header on `/mcp`. **MindSort's `clarity/server.py` has no Origin
validation.** The Claude `server.py` is rebuilt anyway (§3), so add it there.

**Pattern: copy PG's `OriginValidationMiddleware`** verbatim from
`priority_guardian_claude/server_dupl.py`. Behavior: on GET/POST/DELETE `/mcp`,
no Origin header = allowed (Claude's server-to-server httpx sends none); unknown
Origin = 403. Applied only to `/mcp` (discovery/OAuth routes unaffected). Insert in
the middleware stack at the same position PG uses (outside Bearer/content-type,
inside HeadMcp).

### 8.4 Bearer-token 401 challenge — copy PG (not in MindSort today)

Not flagged in the original review but required for clean Claude DCR. PG's
`BearerAuthMiddleware` returns a standards-compliant 401 + `WWW-Authenticate`
(`resource_metadata=".../.well-known/oauth-protected-resource/mcp", scope="..."`)
on unauthenticated `/mcp`, BEFORE FastMCP closes the stream. **Copy PG's
`BearerAuthMiddleware` and `WWW_AUTHENTICATE_VALUE` construction** from
`server_dupl.py`. MindSort scope is `clarity.write` (not PG's scope).

### 8.5 OAuth discovery + proxy routes — copy PG pattern

Claude requires issuer + all OAuth endpoints on the **same origin** as the MCP
server. PG solves this with same-origin OAuth proxy routes (`/oauth/jwks`,
`/oauth/authorize`, `/oauth/token`, `/oauth/register`) forwarding to the shared
backend, plus `/.well-known/oauth-protected-resource` (and `/mcp`-suffixed
variants). **Copy PG's discovery + proxy route setup** from `server_dupl.py`,
pointing at the same shared `/oauth/pg/*` backend endpoints MindSort already uses.
The `resource` field in protected-resource metadata MUST equal the deployed Claude
MCP URL (operational verify at deploy, §8.10 below).

### 8.6 Widget — MCP Apps directory requirements (net-new build)

The Claude widget (new build, §3) requirements are now classified in **§7** above.
Summary of what applies here:

**CONSTRAINTS** per official design-guidelines — treat as submission requirements:
- **Inline card:** auto-fit height (host clips overflow, no published px limit), ≤2 actions at bottom, ≤4-5 data points, no popovers/menus/drill-ins, no nested scroll, touch targets ≥44×44pt. If scroll viewport needed, escalate to fullscreen.
- **Host CSS tokens:** all structural colors via `var(--color-*)` (Anthropic tokens,
  NOT the OpenAI `@openai/apps-sdk-ui` tokens the current widget uses). Light + dark.
- **CSP:** declare `_meta.ui.csp` (connectDomains/resourceDomains) on the `ui://`
  resource. MindSort widget calls only its own backend via the bridge → minimal CSP.
- **WCAG AA:** contrast, keyboard nav, text alternatives for icons (`aria-label`),
  tested in both themes.
- **SDK `App`/`useApp()` class** (not a hand-rolled postMessage bridge) — required
  (§4M); the planned `@modelcontextprotocol/ext-apps` satisfies this.
- **`ui.domain` binding** — mandatory, widget won't render without it.
- **`appCapabilities.availableDisplayModes`** — required protocol.

**[RECOMMENDED]** per §4N — "strongly recommended" but not submission-gating:
- **Transparency/theming:** `html,body{background:transparent;margin:0}`,
  `<meta name="color-scheme" content="light dark">`, `useHostStyles(app)` hook,
  `_meta.ui.prefersBorder:false`.
- **Note:** While formally "strongly recommended," skipping this makes the widget
  render with an opaque box that breaks the conversational blend. Reviewers will see
  this in mandatory screenshots. **Treat as practically obligatory** for visual
  quality even though it won't cause technical rejection.

Reference: PG's `resources_dupl.py` (CSP, `prefersBorder`, `ui.domain`) and its
widget's `useHostStyles` + transparent-background setup.

### 8.7 Instance supersession — **[RECOMMENDED]** explicitly deferrable (biggest save)

MindSort's board widget is a stateful single-instance dashboard;
`organize_thoughts`/`edit_board`/`load_saved_board`/`start_prioritization_flow` all
render it and can be called repeatedly → multiple live iframes.

**Compliance status:** Per master §4M, instance supersession is explicitly stated as
**"not a submission blocker but a known UX degradation. Track as post-submission."**
This is the **single largest deferrable item** — implementing BroadcastChannel
election with `createdAt`+`seq` keys and handling iOS `toolInfo.id` edge cases is
complex work that can be safely skipped for initial submission.

**Recommendation:** Defer to post-submission. Same status PG carries.

### 8.8 Out-of-architecture blockers (named, not solved here)

Not architecture, but will block submission — flagged so they're not forgotten:
- **MindSort privacy policy / legal pages** — currently missing (immediate rejection
  per master §7). Must exist at a stable HTTPS URL before submission.
- **Claude docs page** with ≥3 usage examples (master §4F).
- **MCP App screenshots** (master §5) — needs widget rendering confirmed.
- **Test account** fully populated, no MFA (master §4D) — MindSort equivalent of
  PG's `review@priority-guard.com`.

### 8.9 `_dupl` marking convention

Files in `mindsort_claude/` that exist only due to platform coupling use the
`_dupl` suffix and a 2-line header:
```
# (duplicate) — exists only because <specific reason>.
# Mirrors <OpenAI counterpart path>. Maintain alongside; consolidate only on demonstrated churn.
```

**What the `_dupl` suffix means:**
- The file is the per-platform double-booking — when you change its OpenAI counterpart, check if this file needs the same change.
- Files importing pure logic by reference (§2) are NOT `_dupl` — only mirrored/duplicated infra is.

**Why no migration promise:** Consolidating `_dupl` files into `mcp_server/shared/` (via config injection) is theoretically possible for generic infra (auth, http client), but not warranted now. The duplication is low-maintenance (infra rarely changes), config injection adds indirection, and sharing concentrates blast radius. The trigger for consolidation is **demonstrated recurring churn** — if you find yourself fixing the same bug in multiple `_dupl` counterparts repeatedly, extraction earns its cost. Until then, visible per-platform files are easier to maintain than invisible shared coupling. Do not promise migration in the header; state the principle.

**Scope note:** This correction applies to MindSort's `_dupl` files. PG's existing `_dupl` headers (which say "move to shared/") are left as-is — they're in the in-review codebase and are harmless aspirational text, not blocking.

### 8.10 Operational verifies (at deploy, not now)

- `curl https://<CLAUDE_MCP_URL>/.well-known/oauth-protected-resource` → `resource`
  field must equal the deployed URL exactly.
- `ui.domain` recomputed from final `/mcp` URL (§5), re-verified against live docs.
- Add `https://claude.ai` to CORS only if Claude's browser client hits the MCP
  server directly (PG found it does not — Claude proxies widget calls; confirm for
  MindSort).
- Claude callback URIs added to backend allowlist — Phase 2, post-OpenAI-approval.

---

## Known doc-vs-code drift (fix when files next open — NOT during review)

- `delete_my_data.py` docstring claims `arguments: {confirm: bool}`; handler never reads `confirm` (backend enforces). One-line docstring fix.
- These are noted for living-artifact accuracy, not actioned now (`clarity/` is in review).

---

## Out of scope for this record

Increment breakdown, Claude Code briefings, and widget visual design are separate deliverables. This document fixes the architecture only.
