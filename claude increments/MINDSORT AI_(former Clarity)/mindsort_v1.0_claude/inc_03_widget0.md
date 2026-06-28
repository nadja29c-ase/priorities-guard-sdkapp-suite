# Increment MindSort-Claude-Widget-0: Server-Side Widget Resource Registration

**Goal:** Create the server-side delivery surface for the future Claude MindSort widget. After this increment the Claude MCP server advertises a `ui://` widget resource (with `ui.domain`, CSP, `prefersBorder` on the resource), serves its HTML on `resources/read`, and the four widget-producing tools carry `_meta.ui.resourceUri`. **No React. No widget UI. No bridge.** This makes a widget *renderable in principle* — the widget itself is Widget-A.

This is the increment that was missing between Claude-02b and the widget build. Widget-A (scaffold + bridge + inline summary) has a hard dependency on this surface: a Claude widget with no `ui://` resource registration is UI code with no delivery surface and cannot render.

---

## Context

MindSort (`clarity/`) is being extended to the Anthropic MCP Directory. Server-side Claude work to date:

- **Claude-01** — scaffold (server, config, auth wrapper, empty tool registry)
- **Claude-02** — tool wiring + response adapter; `tools_list_dupl.py` sets `_meta=None` on every tool and explicitly defers `ui.*` metadata to "when the Claude widget lands" — **this increment is that, for the server side**
- **Claude-02b** — discovery/resource-URL fix

The current Claude server (`mcp_server/mindsort_claude/server_dupl.py`) registers a tools-list handler and a `CallToolRequest` handler, mounts OAuth discovery, and exposes health + OAuth proxy routes. **It registers no resource handlers** (`list_resources`, `list_resource_templates`, `read_resource`). FastMCP therefore advertises no widget resource, and no tool references one. That is the gap this increment closes.

### Architectural reference

The reference is **PG's Claude resource layer**, which already does exactly this for the Priority Guardian widget:

- `mcp_server/priority_guardian_claude/handlers/resources_dupl.py` — resource discovery + serving, `ui.domain` (sha256 hash form), CSP, `prefersBorder:false`
- `mcp_server/priority_guardian_claude/server_dupl.py` — how the resource handlers are registered on the FastMCP server (read PG's, because MindSort's Claude `server_dupl.py` does NOT yet have this wiring)
- `tests/unit/mcp_pg_claude/test_scaffold.py` — PG's Claude tests, including the resource + widget-URI tests this increment's tests mirror (`test_list_resources_returns_widget`, `test_widget_uri_consistency`, `test_get_priorities_has_widget_meta`, `test_non_widget_tools_have_no_meta`)

Mirror PG's **structure and test approach**. Do not copy PG's widget URI, widget filename, or any PG-specific values.

### What this is NOT

- NOT the React widget (Widget-A)
- NOT the ext-apps bridge
- NOT OAuth discovery work. **Do not touch `discovery_dupl.py`.** There is a separately-tracked OAuth-discovery concern (the deferred `authorization_servers` path-qualification from Claude-02b); it is out of scope here and must not be pulled in. If you find yourself editing discovery, stop — you have left this increment's scope.

---

## Canonical guidance (READ FIRST)

This is a **Claude/Anthropic** SDK-app increment. Per the canonical-guidance rule, read before implementing:

1. `doc/Claude_Compliance/claude_connectors_compliance_master.md` — §4K (MCP Apps design guidelines: CSP `_meta.ui.csp`, `ui.domain` mandatory + hash formula, display modes), §4N (transparency/theming — relevant here only to which CSP origins you declare), §4O (technical requirements)
2. `doc/Claude_Compliance/structural_guideline_claude_vs_openai_MindSortAI.md` — §3 (platform-specific `resources.py`), §5 (`ui.domain` — host policy, verify at deploy), §8.6 (widget requirements)

Both verified June 2026.

### Pre-Implementation

Read `doc/OPERATIONS_PREDEPLOY.md` before implementing. Two of its sections apply directly here and are NOT optional:
- **"Widget Bundle Changes"** — the single-source-of-truth `WIDGET_URI` discipline and the silent stale-cache failure mode. This increment establishes that discipline for MindSort Claude from the start.
- **"Better Stack Log Shipping" → "Deferred Services"** — MindSort Claude is a deferred Render service; logging/env-var setup is a deploy-time concern, noted so it is not forgotten.

**No migrations in this increment.** No new DB column, table, or persistence. (Consequence for GDPR/retention: see Production Readiness — the retention-doc trigger is not met.)

---

## Implementation Approach — Copy and Adjust, Never Rewrite

Mirror PG's resource layer. Copy PG's `resources_dupl.py` as the starting structure, then change only the MindSort-specific values listed below. Do not rewrite, restructure, or "improve" PG's pattern. If something in PG's source looks wrong, **flag it — do not silently fix it.** (One known PG artifact is called out below so you don't replicate it: a dead `_extract_origin`/`WIDGET_DOMAIN` pair.)

`_dupl` convention (structural guideline §8.9): files that exist only due to platform coupling carry the 3-line header. Do NOT include a "move to shared/" migration promise.

```python
# (duplicate) — exists only because <specific reason>.
# Mirrors mcp_server/clarity/handlers/resources.py (OpenAI) and
# mcp_server/priority_guardian_claude/handlers/resources_dupl.py (Claude pattern).
# Consolidate into shared/ ONLY if this file proves to churn — not preemptively.
```

---

## Scope

### IN

1. **`handlers/resources_dupl.py`** (new) — widget resource discovery + serving for the Claude MindSort widget.
2. **Widget HTML placeholder** at `mcp_server/mindsort_claude/widgets/` — a minimal valid HTML file so `read_resource` serves real bytes this increment (Widget-A replaces it with the built bundle). The `widgets/` directory already exists (created in Claude-01 with `.gitkeep`).
3. **Single production definition of the Claude widget URI** — one constant, imported by every production consumer. (See "Widget URI consistency" — hard requirement from OPERATIONS_PREDEPLOY and the ADR, not a nicety.)
4. **Server wiring** in `server_dupl.py` — register `list_resources`, `list_resource_templates`, and `read_resource` on the FastMCP server, mirroring PG's Claude `server_dupl.py`. This is the ONLY change to `server_dupl.py`.
5. **`ui.resourceUri` wiring** in `tools_list_dupl.py` — the four widget-producing tools gain `_meta.ui.resourceUri` pointing at the Claude widget URI. The two non-widget tools keep `_meta=None`.

### OUT

- React widget, ext-apps bridge, inline summary (Widget-A)
- `availableDisplayModes` / `appCapabilities` declaration (that is declared by the *widget* at `ui/initialize`, i.e. Widget-A — not server-side)
- Any change to `discovery_dupl.py`, `mcp_auth_dupl.py`, `config.py` logic, `clarity/`, `backend/`
- Instance supersession, fullscreen, any UI concern

---

## Widget-producing tools — VERIFIED from source (do not re-derive)

The set of tools that get `ui.resourceUri` was verified by reading each tool's `register_tool(...)` block in `clarity/tools/`. Do not guess this set; do not include a tool because it "returns clusters."

| Tool | `widget_uri` in `clarity/` | Gets `ui.resourceUri` in Claude? |
|---|---|---|
| `organize_thoughts` | `WIDGET_URI` | **YES** |
| `load_saved_board` | `WIDGET_URI` | **YES** |
| `start_prioritization_flow` | `WIDGET_URI` | **YES** |
| `edit_board` | `WIDGET_URI` | **YES** |
| `read_board_before_editing` | `None` (explicitly "Never produces widget") | **NO** — keep `_meta=None` |
| `delete_my_data` | `None` (no widget output) | **NO** — keep `_meta=None` |

`read_board_before_editing` returns cluster data but deliberately renders no widget (its job is to feed the LLM data before an edit). A naive "any cluster-returning tool" rule would wrongly wire it. It must NOT get `resourceUri`.

**The Claude widget URI is distinct from the OpenAI one.** `clarity/`'s tools import `WIDGET_URI` from `clarity.handlers.resources` (value `ui://widget/...`, OpenAI). The Claude `resourceUri` must be the **Claude** widget URI defined in the new `resources_dupl.py` (mirror PG's scheme — PG uses `ui://pg-claude/dashboard-v1.html`). **Do not import or reuse the OpenAI `WIDGET_URI`.** `tools_list_dupl.py` reads the Claude value from the new resources module.

---

## Metadata placement — explicit split (do not conflate)

This is a hard structural rule, verified against PG's working Claude code. The two metadata surfaces carry **different** keys:

| Surface | Keys it carries | Where |
|---|---|---|
| **Resource** (the `Resource` / `ResourceTemplate` advertised by `list_resources`, AND the `TextResourceContents` returned by `read_resource`) | `_meta.ui.domain`, `_meta.ui.csp`, `_meta.ui.prefersBorder` | `resources_dupl.py` |
| **Tool** (each widget-producing tool in `list_tools_for_claude()`) | `_meta.ui.resourceUri` **only** | `tools_list_dupl.py` |

Do NOT put `domain` / `csp` / `prefersBorder` on tool `_meta`. Do NOT put `resourceUri` as the only thing on the resource (the resource is identified by its own `uri` field; `resourceUri` is the *tool's* pointer to it). PG follows exactly this split — mirror it.

---

## Hard requirements — read before writing code

### `ui.domain` (compliance master §4K + structural guideline §5) — on the RESOURCE

- **Mandatory.** Without it the widget will not render.
- Formula (master §4K, structural §5): `sha256(MCP_RESOURCE_URL)[:32] + ".claudemcpcontent.com"`, where `MCP_RESOURCE_URL` is the **full** deployed Claude MCP endpoint **including `/mcp`** — not the origin.
- This is **host policy, deploy-dependent, mutable** (structural §5). Compute it from config (`MCP_RESOURCE_URL`), never hardcode. Final deployed domain is not decided yet — the value is correct as long as it derives from config at runtime.
- PG's pattern: hash `MCP_RESOURCE_URL` → `{hash}.claudemcpcontent.com`. Mirror it.
- **Known PG artifact — do NOT replicate:** PG's `resources_dupl.py` also computes `WIDGET_DOMAIN = _extract_origin(MCP_SERVER_URL)` (origin-only) which is **never used** — the served domain is the sha256 hash. Origin-only is wrong for Claude (structural §5). Use only the hash form; do not copy the dead `_extract_origin`/`WIDGET_DOMAIN` pair.

### CSP (compliance master §4K) — on the RESOURCE

- Declare `_meta.ui.csp` on the `ui://` resource. Default-deny: all external origins blocked unless declared.
- The MindSort widget (when built) calls only its own backend via the MCP Apps bridge (postMessage), not direct HTTP — so `connectDomains` is empty, same as PG.
- `resourceDomains`: include `https://assets.claude.ai` only if you intend host font loading (§4N, "optional but expected"). PG includes it; mirroring is reasonable. If included, comment that it's for host font loading per §4N. **Security note from §4N:** `resourceDomains` also widens `script-src`/`style-src` — only `assets.claude.ai` (Anthropic-owned) belongs there. Add nothing else.

### `prefersBorder` (compliance master §4N) — on the RESOURCE

- Set `_meta.ui.prefersBorder: false` on the resource (structural §8.6 treats this as practically obligatory for visual blend). Mirror PG.

### MIME type — one rule, evidence may override

**There is a real fork in the codebase's own canonical sources:**
- The installed SDK (`@modelcontextprotocol/ext-apps`, `dist/src/spec.types.d.ts`) declares `RESOURCE_MIME_TYPE = "text/html;profile=mcp-app"` and states `McpUiClientCapabilities.mimeTypes` *must include* `"text/html;profile=mcp-app"`.
- PG's shipped `resources_dupl.py` serves `text/html+mcp` — and PG's **passing** Claude test (`tests/unit/mcp_pg_claude/test_scaffold.py::test_list_resources_returns_widget`) asserts exactly `text/html+mcp`. PG both ships and enshrines `+mcp`.

Both strings live in the working codebase and differ. Not resolvable by reading docs alone.

**The rule (single, non-contradictory):**
> Default to `text/html;profile=mcp-app` (the installed SDK's declared constant). If an empirical host test — MCP Inspector or a dev Claude connection — proves a different MIME is required to render, document the evidence in a code comment and use the proven value instead.

Whichever value you commit, add a one-line comment recording that PG ships/tests `text/html+mcp` while the SDK declares `text/html;profile=mcp-app`, so the fork is visible at review. Do not silently copy PG.

> **FLAG TO HUMAN (do not fix here):** PG ships AND tests `text/html+mcp`; the installed SDK declares `text/html;profile=mcp-app`. Since PG's connector reportedly renders, the host may accept both — or PG is stale, or the SDK type is aspirational. Needs a ~10-minute empirical reconciliation by Nadja, and likely a correction to either PG's resource layer + its test, or the structural guideline. Report it; do not edit PG.

### Widget URI consistency (OPERATIONS_PREDEPLOY "Widget Bundle Changes" + ADR "Widget URI Consistency")

**Hard requirement**, not style. Documented failure mode: if any production consumer references a stale/forked widget URI, the host serves an empty result and silently falls back to a stale cached widget — no error in logs, production bugs hidden for hours.

- **One production definition** of the Claude widget URI constant. Every production consumer (the resource handler AND `tools_list_dupl.py`'s `resourceUri` wiring) **imports** it. There must be no second production assignment of the URI string.
- Tests MAY contain the expected URI as a literal, but only in clearly-isolated assertion sites (this is exactly what PG does — `test_list_resources_returns_widget` and the widget-meta tests hold the literal; `test_widget_uri_consistency` imports the constant from both modules and asserts equality). Do not treat test literals as a violation.
- The resource handler's advertised `uri` and the tools' `resourceUri` must be the same value by construction (same imported constant), not by coincidence.

### Server-side resource handler shape

- Mirror how PG's Claude `server_dupl.py` registers the three handlers on `mcp._mcp_server` (the same object MindSort's server already uses for `list_tools` and `CallToolRequest`). Read PG's server for the exact registration mechanism for `list_resources` / `list_resource_templates` / `read_resource` — MindSort's Claude `server_dupl.py` does not have it yet.
- `read_resource` for an **unknown** URI must return cleanly (PG returns empty contents + error `_meta`), not raise. Reviewers call edge cases.
- Module cleanup contract (ADR): the resource module loads widget HTML once at import (like PG). It owns no stateful async resource, so it needs no `cleanup_*()` — confirm that's true for what you write; if you add any client/cache, expose cleanup and wire it into the server's existing `_cleanup_on_shutdown`.

---

## What NOT to touch

- `mcp_server/clarity/` — ChatGPT MindSort is under OpenAI review. (You will READ `clarity/handlers/resources.py` and `clarity/tools/*` register blocks as reference — read only, never edit.)
- `backend/`
- `mcp_server/mindsort_claude/discovery_dupl.py`, `mcp_auth_dupl.py`, `config.py` logic, `response_adapter_dupl.py`, `handlers/tools_dupl.py`
- The OAuth proxy routes, middleware stack, discovery routes in `server_dupl.py` — the ONLY `server_dupl.py` change is registering the three resource handlers.
- `clarity/widget-react/` and `priority_guardian_claude/widget-react/` — no widget code this increment.

---

## Tests

Use the existing pattern: `httpx.AsyncClient(app=create_app(), base_url="http://test")`, `ENV=dev` via `monkeypatch.setenv`, no real backend connectivity. Add to the existing `tests/unit/mcp_claude_mindsort/` module(s); do NOT modify existing tests or the autouse `restore_mcp_auth_globals` fixture. All existing scaffold/tool/discovery tests must continue to pass unchanged.

### Unit tests (no host, no network)

1. **Resource is advertised** — `list_resources()` (called directly as a function, PG-style) returns exactly one resource; its `uri` equals the single production Claude widget URI constant; `mimeType` equals the MIME string committed.
2. **`ui.domain` is hash-derived, not hardcoded** — the resource's `_meta.ui.domain` equals `sha256(MCP_RESOURCE_URL)[:32] + ".claudemcpcontent.com"` computed independently in the test from configured `MCP_RESOURCE_URL`. Assert it ends with `.claudemcpcontent.com` and is NOT a server origin/hostname.
   - *Bug that would still pass:* handler and test both deriving from a wrong-but-identical source. Mitigate by computing expected hash in the test from `config.MCP_RESOURCE_URL` directly, independent of handler internals.
3. **`ui.domain` uses the full `/mcp` URL** — set `CLARITY_CLAUDE_MCP_RESOURCE_URL` to a value ending in `/mcp`, reload config + resources, assert domain hash matches `sha256("<that value>")[:32]`. Then (isolation-restored) confirm a value WITHOUT `/mcp` produces a different hash — proving the path is in the hash input.
4. **CSP present and minimal** — resource `_meta.ui.csp` exists; `connectDomains == []`; `resourceDomains` is `[]` or `["https://assets.claude.ai"]` only.
5. **`prefersBorder` false** — resource `_meta.ui.prefersBorder is False`.
6. **Metadata placement split** — the resource carries `ui.domain`/`ui.csp`/`ui.prefersBorder` and does NOT carry `ui.resourceUri`; a widget-producing tool carries `ui.resourceUri` and does NOT carry `ui.domain`/`ui.csp`/`ui.prefersBorder`. (Guards against conflating the two surfaces.)
7. **`read_resource` serves the widget** — reading the advertised URI returns contents with non-empty HTML body and `mimeType` matching the advertised one.
8. **`read_resource` unknown URI is graceful** — reading `ui://does-not-exist` returns a clean result (empty contents + error `_meta`), does NOT raise, does NOT 500.
9. **Widget-producing tools carry `resourceUri`** — from `list_tools_for_claude()`: `organize_thoughts`, `load_saved_board`, `start_prioritization_flow`, `edit_board` each have `_meta.ui.resourceUri` equal to the single production Claude widget URI constant.
   - *Bug that would still pass:* a hardcoded duplicate URI in `tools_list_dupl.py` that happens to match. Mitigate by asserting the tool's `resourceUri` equals the constant imported from the resources module (PG's `test_widget_uri_consistency` pattern: import from both modules, assert equal).
10. **Non-widget tools stay `_meta=None`** — `read_board_before_editing` and `delete_my_data` have `_meta is None` (unchanged from Claude-02). Guards against over-wiring.
11. **Widget URI consistency (PG pattern)** — import the URI constant from the resources module and from wherever `tools_list_dupl.py` consumes it; assert they are the same object/value. (Mirrors PG's `test_widget_uri_consistency`. This replaces any brittle "grep for one assignment" check.)
12. **Annotations/listing unchanged** — Claude-02 invariants still hold for all six tools (title present, `destructiveHint` override for `start_prioritization_flow` still True, sort order). Guards against the `resourceUri` change regressing the list.

### Integration tests (separate from unit tests)

Behavior-level, through the app. **Do NOT inspect FastMCP internals** (`_mcp_server.request_handlers` etc.) — PG does not, and it is fragile across SDK versions. Test the observable contract instead.

13. **End-to-end resource round trip in-process** — through the running app (or by calling the registered `list_resources` / `read_resource` the same way PG's tests do): list resources → take the advertised URI → read it → assert non-empty HTML body and matching MIME. This proves the handlers are wired and serve correctly without reaching into FastMCP internals.

For each test, the implementer must state what bug would still pass it. Some are pre-annotated; apply the same discipline to the rest.

---

## Production Readiness (evaluated at INCREMENT scope)

Production-readiness is judged in context (increment vs product vs suite). At **increment** scope:

- **Scalability:** Loads one static HTML file once at import, serves identical bytes per request (mirrors PG and `clarity/`). No per-request DB or backend call. No scaling concern introduced.
- **GDPR / data retention:** **No new personal-data column, table, or collection.** Per OPERATIONS_PREDEPLOY "Schema Change Checklist," the trigger for updating the Data Retention Strategy / ROPA is *adding a personal-data column or table* — not met here. A static widget resource collects and persists nothing. **No retention-doc update required for this increment.** (Product-level retention work — the OpenAI-vs-Claude runtime/processor disclosure gap — remains a *product submission* concern, tracked, out of scope here.)
- **Run under load + latency:** Serving a static in-memory HTML string is sub-millisecond; no backend round trip on the resource path. No latency risk added. (Latency budgets in OPERATIONS_PRESUBMISSION concern *tool* calls, not resource reads.)

**Deploy note (not actioned now):** MindSort Claude is a deferred Render service. At deploy, the widget-bundle cache-invalidation discipline (OPERATIONS_PREDEPLOY "Widget Bundle Changes") and deferred-service logging/env setup apply. The placeholder HTML shipped here is replaced by the built bundle in Widget-A; the `WIDGET_URI` version string is the cache-busting lever.

---

## Tracked separately — do NOT address here

- **OAuth discovery `authorization_servers` path-qualification** (Claude-02b deferred; ADR tension). Tracked separately. Not part of Widget-0. Not part of Widget-A. Do not touch discovery; do not raise it inside this increment.
- **MIME-string discrepancy** PG vs SDK (flag above) — report to Nadja; do not fix PG.
- **Product-level Claude/Anthropic data-retention & ROPA disclosure** — product submission blocker, not an increment-0 concern.
- **`clarity/` self-registration via import side effects** violates the ADR's explicit-registry rule — pre-existing in the in-review OpenAI module; flag only, never edit.

---

## Definition of Done

- [ ] `handlers/resources_dupl.py` exists, mirrors PG structure, carries the 3-line `_dupl` header (no "move to shared/" promise).
- [ ] Claude widget URI has exactly one production definition under `mindsort_claude/`; resource handler and `tools_list_dupl.py` both import that constant (no second production assignment).
- [ ] `ui.domain` derives from `config.MCP_RESOURCE_URL` via `sha256(...)[:32] + ".claudemcpcontent.com"` — not hardcoded, includes `/mcp` in the hash input. No dead `_extract_origin`/`WIDGET_DOMAIN` pair copied from PG.
- [ ] Metadata split correct: resource carries `ui.domain` + `ui.csp` + `ui.prefersBorder`; widget-producing tools carry `ui.resourceUri` only.
- [ ] `_meta.ui.csp` (connectDomains `[]`; resourceDomains `[]` or `assets.claude.ai` only) and `_meta.ui.prefersBorder: false` set on the resource.
- [ ] MIME string committed is `text/html;profile=mcp-app` by default (or an empirically host-verified value), with a code comment recording the PG `text/html+mcp` fork.
- [ ] Placeholder widget HTML present under `widgets/`; `read_resource` serves it.
- [ ] `server_dupl.py` registers `list_resources` / `list_resource_templates` / `read_resource` and nothing else changes.
- [ ] The four widget-producing tools carry `_meta.ui.resourceUri`; `read_board_before_editing` and `delete_my_data` remain `_meta=None`.
- [ ] All existing Claude-01/02/02b tests pass unchanged; the `restore_mcp_auth_globals` fixture untouched.
- [ ] All new unit + integration tests pass. Integration test does NOT inspect FastMCP internals.
- [ ] Full `tests/unit/` suite run: only the known pre-existing failures remain, no new ones. **(Establish the exact pre-existing failure list by running the suite BEFORE writing code; if the count differs from what Claude-02/02b recorded, STOP and report.)**
- [ ] Zero files modified in `clarity/`, `backend/`, `discovery_dupl.py`, `mcp_auth_dupl.py`.
- [ ] **Before committing:** re-read `doc/OPERATIONS_PREDEPLOY.md` and confirm no additional pre-deploy task applies to a resource/widget change.

**Scope honesty:** This produces a *renderable surface*, not a rendered widget. It is not submission-ready and not visually verifiable — nothing to screenshot yet. A green DoD means "the server advertises and serves a widget resource, and widget-producing tools point at it." Widget-A builds the actual UI against this surface.

---

## Notes for the implementer (flag, don't fix)

- If PG's `resources_dupl.py` registration mechanism differs from what MindSort's `server_dupl.py` expects (FastMCP version skew between the two modules), STOP and report — do not guess a registration call.
- If any symbol you need from the MindSort Claude modules doesn't match (e.g. config export names), STOP and report — do not invent.
- If you cannot run the test suite or a smoke test in your environment, say so explicitly and tell me exactly what to run (commands + expected output) — do not silently skip the pre-existing-failure baseline or the MIME empirical check.
- Verify every edit actually persisted (re-read the file after writing).
