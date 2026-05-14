# Structural Guideline: Priority Guardian for Claude vs. ChatGPT

**Created:** March 2026
**Updated:** May 2026
**Status:** Implemented — Increments Claude-01 through Claude-06 complete
**Context:** Priority Guardian v1.0 is accepted into the OpenAI GPT store. This document captures the architecture decisions for extending PG to the Anthropic MCP Directory as a second distribution channel.

**Current State:** Claude MCP server deployed, OAuth callbacks configured, response adapter built, widget implemented. Widget rendering blocked by platform-side issue (anthropics/claude-ai-mcp #61). Pending: `title` annotation missing on ChatGPT server, `destructive_hint=False` incorrect on write tools.

---

## Background

Priority Guardian was built on the OpenAI Apps SDK stack (ChatGPT). Anthropic launched MCP Apps in January 2026 as an open standard co-authored with OpenAI. Claude now supports MCP Apps with widget rendering, making a Claude-targeted version of PG feasible.

The widget layer is platform-specific. The backend, OAuth provider, and tool logic are platform-agnostic. This creates a clean separation boundary.

---

## Decision: Same Repo, Separate MCP Server, Separate Render Service

### Repo structure

```
mcp_server/
├── priority_guardian/           # ChatGPT — existing, unchanged
│   ├── server.py
│   ├── config.py
│   ├── mcp_auth.py
│   ├── tools/                   # SOURCE OF TRUTH for all tool logic
│   ├── widget-react/src/        # ChatGPT widget (window.openai bridge)
│   └── widgets/pg-dashboard.html
│
└── priority_guardian_claude/    # Claude — new
    ├── server.py                # thin wrapper; different widget path + env vars
    ├── config.py                # Claude-specific config (callback URIs, CORS)
    ├── widget-react/src/        # Claude widget (MCP Apps ui/* postMessage bridge)
    └── widgets/pg-dashboard-claude.html
    # NO tools/ directory — imports directly from priority_guardian.tools
```

### Why not a separate repo

A separate repo would require syncing tool logic, backend schema changes, migration changes, and OAuth changes across two codebases permanently. Tool drift would happen within weeks. Same repo with a module boundary is the correct tradeoff.

### Why a separate Render service

- `PG_MCP_SERVER_URL` differs per platform (e.g. `pg.priority-guard.com` vs `pg-claude.priority-guard.com`)
- The `resource` field in `/.well-known/oauth-protected-resource` must exactly match the URL Claude uses to connect. Two platforms = two resource identifiers = two services.
- Independent deploys: a widget change for Claude does not touch the ChatGPT service and vice versa.
- Separate env var sets (CORS origins, OAuth callback URLs, widget paths).

---

## Shared vs. Platform-Specific — Layer Boundary

| Layer | Shared | Platform-specific |
|---|---|---|
| Backend (FastAPI, DB, Redis, Celery) | ✅ | — |
| Google OAuth integration | ✅ | — |
| Inbound OAuth provider (DCR, PKCE, JWT) | ✅ | — |
| All tool handlers (`tools/*.py`) | ✅ imported by reference | — |
| Tool definitions (`ToolDefinition` objects) | ✅ | — |
| MCP server infrastructure (auth middleware, http_client) | ✅ | — |
| Widget HTML/JS (bridge layer) | — | ✅ diverges by platform |
| OAuth callback URLs | — | ✅ diverges by platform |
| CORS allowed origins | — | ✅ diverges by platform |
| `PG_MCP_SERVER_URL` / `resource` claim | — | ✅ diverges by platform |
| Render service | — | ✅ separate per platform |

**Rule: duplicate UI, never duplicate logic.**

---

## The Widget Divergence

This is the largest implementation difference. The two bridge APIs are fundamentally different.

### ChatGPT (current — `window.openai.*`)

```typescript
// Data access
window.openai.toolOutput

// Tool calls from widget
window.openai.callTool('get_priorities', {})

// State persistence
window.openai.setWidgetState(state)

// Host communication
window.openai.notifyIntrinsicHeight()
window.openai.requestDisplayMode({ mode: 'fullscreen' })

// Event updates
window.addEventListener('openai:set_globals', handler)
```

### Claude / MCP Apps standard (`ui/*` postMessage bridge)

```typescript
// Standard MCP Apps extension (SEP-1865)
// Transport: JSON-RPC 2.0 over postMessage
// Tool I/O: ui/notifications/tool-result
// Tool calls: tools/call via bridge
// State: ui/setState, ui/getState
```

`window.openai` is a ChatGPT-specific compatibility layer — it is not injected by Claude. The Claude widget must use the MCP Apps standard `ui/*` bridge exclusively.

Reference: OpenAI docs state: *"Use MCP Apps standard keys and bridge methods (`_meta.ui.resourceUri`, `ui/*`) when there's an equivalent. Use OpenAI extensions only when you need ChatGPT-specific capabilities."*

The Claude widget is a new React implementation starting from the MCP Apps standard SDK (`@modelcontextprotocol/ext-apps`). It is not a patch of the ChatGPT widget.

---

## Tool Logic Sharing — Import Pattern

`priority_guardian_claude` does **not** have its own `tools/` directory. It imports directly:

```python
# priority_guardian_claude/server.py (or tools_registry.py)
from mcp_server.priority_guardian.tools import TOOL_REGISTRY, list_tools
from mcp_server.priority_guardian.tools.get_priorities import GET_PRIORITIES
# etc.
```

Feature work on tool logic (new tool, new endpoint, backend change) is done once in `priority_guardian/tools/`. Both variants inherit the change automatically.

**What touches once vs. twice when building a feature:**

| Feature type | Touches |
|---|---|
| New tool / tool logic change / backend change | Once — `priority_guardian/tools/` only |
| Feature requiring visible widget UI change | Twice — both widget React sources (unavoidable) |

---

## MCP Server Response Adapter — Required for Claude

The assumption that only the widget needs changing is incorrect. The MCP server layer for Claude also requires a **response adapter** due to fundamental differences in how ChatGPT and Claude handle tool response fields.

### The core problem: `structuredContent` handling differs

ChatGPT behaviour (documented in compliance_master): when both `content` and `structuredContent` are returned, ChatGPT ignores `content` entirely. This is why PG puts `assistant_guidance` inside `structuredContent` — it is the only channel ChatGPT passes to the model.

Claude behaviour (MCP Apps standard): `content` is what the LLM sees. `structuredContent` is data for the UI. Claude reads `content` correctly and passes `structuredContent` to the widget via `ui/notifications/tool-result`. The model receives both.

This creates two specific problems in PG's current tool responses:

**Problem 1: `assistant_guidance` is inside `structuredContent`**

All PG tool handlers return `assistant_guidance` nested inside `structuredContent`:
```python
structuredContent={
    "data": {"priorities": [...]},
    "_meta": {"openai/outputTemplate": WIDGET_URI},
    "assistant_guidance": "Do not repeat priorities — the widget displays them..."
}
```
For Claude, `assistant_guidance` guidance still reaches the model (Claude reads `structuredContent`), but the full `data` payload also enters model context — increasing token consumption and latency. More critically, this is the wrong channel by the MCP Apps standard.

**Problem 2: `_meta` is nested inside `structuredContent` instead of top-level**

Widget linking metadata (`openai/outputTemplate`, `ui.resourceUri`) is embedded inside `structuredContent._meta` in every tool handler. The MCP Apps standard expects `_meta` as a top-level field on the tool result. Claude may expose this to the model as noise.

### Solution: Response adapter layer in `priority_guardian_claude`

`priority_guardian_claude` needs a thin response-shaping layer between the shared tool handlers (unchanged) and the MCP protocol serialisation. This adapter:

1. Moves `assistant_guidance` from `structuredContent` into `content` text (where Claude's model reads it)
2. Strips ChatGPT-specific `_meta` fields (`openai/outputTemplate`, invocation messages) from `structuredContent`
3. Places widget linking metadata at the correct top-level `_meta` position using the standard `ui.resourceUri` key
4. Keeps `structuredContent` as clean UI-only data

The shared tool handlers in `priority_guardian/tools/` return the same shape they always have. The adapter in `priority_guardian_claude` rewrites the response before it leaves the MCP server. This is a bounded, well-defined layer — but it is real work beyond the widget refactor.

### What stays shared despite this

All tool *logic* remains shared. The adapter only touches response serialisation. Feature work on priorities, calendar integration, patterns, etc. still happens once.

### Updated scope estimate

| Component | Effort |
|---|---|
| Widget refactor (bridge API) | Large — new React implementation |
| Response adapter (server layer) | Medium — well-defined transformation layer |
| OAuth callback URIs | Small — additive config change |
| Documentation page | Medium — write from scratch |
| CORS verification | Small — test and confirm |

---

## Token Size Risk Assessment — Pre-Decision Analysis

**This must be evaluated before committing to the Claude build.** Anthropic's directory policy item 15 requires tool responses to be "roughly commensurate with the complexity or impact of the task." PG has one tool that warrants scrutiny: `get_weekly_report`.

### The `structuredContent` / `_meta` separation is critical

Per the MCP Apps spec (confirmed from OpenAI's own documentation, Step 3 of Build your MCP server):

- **`structuredContent`** — the widget uses it AND the model reads it. Only put what the model should see here.
- **`_meta`** — large or sensitive data exclusively for the widget. `_meta` never reaches the model.

From the OpenAI troubleshooting guide: *"Structured payloads are huge — Trim `structuredContent` to what the model truly needs; oversized payloads degrade model performance and slow rendering."*

### `get_weekly_report` — `allEvents` is in the wrong field

PG currently puts `allEvents` inside `structuredContent.data`. This means every calendar event — title, description, timestamps — goes into the model context on every `get_weekly_report` call for the current week.

The backend fetches up to 250 events/page × 10 pages = 2,500 raw events from Google Calendar. After filtering, these become `all_events`.

**Critical finding from the code:** Past weeks served from snapshots return `"all_events": []`. The full event payload only exists for the **current week**.

| Scenario | Approx. tokens | Risk |
|---|---|---|
| Past week (from snapshots) | ~500–800 | None — `all_events` is empty |
| Current week, normal user (30–60 events) | ~3,000–6,000 | Real but tolerable |
| Current week, busy user (150+ events, long descriptions) | 15,000+ | Violates item 15 |

### The correct field placement

| Data | Currently in | Should be in | Model sees it? |
|---|---|---|---|
| `priorities`, `timeAllocation`, `slices` | `structuredContent` | `structuredContent` | Yes — correct |
| `allEvents` | `structuredContent` | `_meta` | No — widget only |
| `assistant_guidance` | `structuredContent` | `content` | Yes — correct channel |

Moving `allEvents` to `_meta` fixes the token problem entirely. The widget reads `_meta` via the bridge; the model never sees it.

### The semantic grouping feature consequence

The semantic grouping feature **relies on the model seeing `allEvents`** to propose categories for non-priority time. If `allEvents` moves to `_meta`, the model can no longer read event titles and the feature breaks.

This is not a Claude-specific problem — it is a correctness issue on both platforms. `allEvents` is currently in the wrong field by the MCP Apps spec, and fixing it breaks the semantic grouping design.

Options:
1. **Keep `allEvents` in `structuredContent` with a hard cap** (e.g. 50 events max) — pragmatic, technically non-compliant with the spirit of item 15 for busy users, but defensible for submission
2. **Move `allEvents` to `_meta`, redesign semantic grouping** — grouping becomes widget-side or a separate explicit tool call. Architecturally correct, more work
3. **Drop semantic grouping from Claude version** — Claude gets aggregates-only weekly report, no interactive breakdown

### All other tools — not a concern

- `get_priorities`: max 3 priorities × fields + deliverables/goals. ~500–800 tokens. Bounded by design.
- `get_patterns`: computed aggregates only, no raw event data. Bounded.
- `create_priority`, CRUD tools: same shape as `get_priorities`. Bounded.

### Decision needed before building

This does not block the Claude build for most tools. But the weekly report widget implementation depends on the `allEvents` decision. Decide before investing in that widget view:
- If keeping in `structuredContent` with cap: implement cap at backend, widget reads from `structuredContent` as now
- If moving to `_meta`: widget reads from `_meta` via bridge, semantic grouping feature redesigned or dropped

---

## Known Risk: Shared Tools Future Branching

If Claude's MCP client ever passes different metadata or context in tool calls than ChatGPT (e.g. different `_meta` fields, different error handling expectations), shared tool handlers may need platform-specific branching. This is unlikely now but is the one place "share everything" could create friction later.

Mitigation: keep tool handlers clean of ChatGPT-specific assumptions. If branching becomes necessary, introduce a thin platform adapter layer rather than forking the handler files.

---

## Compliance Blockers Before Submission to Anthropic MCP Directory

The following tracks Claude-specific blockers. See `claude_connectors_compliance_master.md` for comprehensive requirements.

### ✅ Resolved — OAuth Callback URLs (Increment Claude-03)

Claude callback URLs added to `backend/core/config.py` allowlist:
- `https://claude.ai/api/mcp/auth_callback`
- `https://claude.com/api/mcp/auth_callback`
- `http://localhost:6274/oauth/callback`
- `http://localhost:6274/oauth/callback/debug`

PKCE S256 already implemented. No further code change needed.

### ✅ Resolved — Widget Bridge Refactor (Increment Claude-06)

Full widget rewrite completed using `@modelcontextprotocol/ext-apps` SDK. Implemented:
- `ui/notifications/tool-result` for data delivery
- `tools/call` via MCP Apps bridge for CRUD operations
- `ui/setState` / `ui/getState` for state persistence
- MCP Apps context for locale/theme/displayMode

Widget implementation is correct per spec. Currently blocked by platform-side issue — claude.ai does not call `resources/read` for third-party custom connectors (anthropics/claude-ai-mcp #61, open since February 2026).

### ✅ Resolved — Response Adapter (Increment Claude-04)

Adapter layer in `priority_guardian_claude/` correctly:
- Moves `assistant_guidance` from `structuredContent` to `content`
- Strips ChatGPT-specific `_meta` from `structuredContent`
- Places `ui.resourceUri` at top-level `_meta`
- Applies `MAX_LIST_ITEMS = 10` threshold for token efficiency

Gap: `_meta.ui.domain` not set. Should be added when widget rendering resolves.

### 🟡 Pending — `title` Annotation on ChatGPT Server

Claude server compensates via `tools_list_dupl.py` which derives `title` from tool name using `_derive_title()`. ChatGPT server in `priority_guardian/` lacks `title` — needs fix in shared `ToolDefinition` dataclass.

### 🔴 Blocker — `destructive_hint` Incorrect on Write Tools

`create_priority`, `add_priority`, `update_priority` have `destructive_hint=False` when they should be `True`. Affects both platforms. Fix in `priority_guardian/tools/` (shared).

### 🟡 Pending — Documentation Page

No Claude-specific documentation page exists. Must be published at a stable HTTPS URL before submission with all required sections including minimum 3 usage examples.

### 🟡 Pending — MCP App Screenshots

Screenshots of widget rendering in Claude.ai mandatory for directory listing. Blocked until platform widget rendering issue resolves.

### 🟡 Item — CORS Origins (Operational Verify)

Confirm whether Claude's browser client hits the MCP server directly. If yes, `https://claude.ai` must be in `CORS_ALLOWED_ORIGINS`.

### 🟡 Item — `/.well-known/oauth-protected-resource` URL Match (Operational Verify)

Before submitting, verify:
```bash
curl https://<CLAUDE_SUBMISSION_URL>/.well-known/oauth-protected-resource
# → "resource" must equal <CLAUDE_SUBMISSION_URL>
```

---

## Items That Do NOT Need Changes for Claude

- Backend API endpoints — unchanged
- Google OAuth integration — unchanged
- Inbound OAuth provider (DCR, PKCE, JWT issuance, JWKS) — unchanged
- Token verification logic (`mcp_auth.py`) — unchanged
- All tool handlers — unchanged (shared via import)
- `_meta.ui.resourceUri` — Claude adapter sets at top-level correctly
- MIME type `text/html;profile=mcp-app` — already correct in `handlers/resources.py`
- Privacy policy — already discloses Google Calendar data handling per Google and GDPR requirements
- Test account — `review@priority-guard.com` with seed data already exists
- Transport — FastMCP Streamable HTTP is what Anthropic requires; SSE deprecated path not used
- Production readiness — error handling, timeouts, Render Hobby tier all already in place

**Items that DO need changes (cross-platform):**
- `title` annotation — missing on all tools in shared `ToolDefinition`; Claude server compensates via `_derive_title()`, ChatGPT server does not
- `destructive_hint` — incorrectly `False` on `create_priority`, `add_priority`, `update_priority`; should be `True`

---

## Implementation Sequencing — OpenAI Review Risk Management

Priority Guardian is currently under OpenAI review. The Claude build must not risk breaking the ChatGPT service during this period.

**The actual risk surface is small, not the whole codebase.** What can break the OpenAI review:
- Redeploying the backend with a changed or broken `_CHATGPT_REDIRECT_URIS`
- Introducing a regression in the ChatGPT MCP server
- Changing `OAUTH_ISSUER`, CORS origins, or any OAuth discovery field

What cannot break the OpenAI review:
- Adding a new folder `priority_guardian_claude/` to the repo
- Deploying a new Render service on a different domain
- Writing a new widget React source that doesn't touch the ChatGPT widget
- Writing documentation

### Do NOT copy the repo

Copying the repo to isolate risk is the wrong move. Even a "temporary" copy creates two sources of truth. Any fixes, bug discoveries, or improvements made during the Claude build will need manual reconciliation back into the main repo. That reconciliation is more expensive than the risk being avoided, and "temporary" architectural decisions tend to become permanent.

### Phase 1 — Zero risk to ChatGPT review (do now)

- Create `mcp_server/priority_guardian_claude/` folder structure
- Write the Claude widget (`widget-react/src/` using MCP Apps `ui/*` bridge)
- Write `server.py` and `config.py` for the Claude service (pointing at existing backend)
- Deploy the Claude Render service on its own domain — the service will be live but OAuth won't complete end-to-end yet (Claude callback URIs not yet in allowlist, intentionally)
- Write the Anthropic documentation page

### Phase 2 — One backend redeploy (do after OpenAI approves)

- Add the four Claude callback URIs to `_CHATGPT_REDIRECT_URIS` in `backend/core/config.py`
- Redeploy backend
- Test Claude OAuth flow end-to-end
- Submit to Anthropic MCP Directory

The Phase 2 backend change is additive (new URIs in an allowlist). It cannot break existing ChatGPT OAuth flows. Deferring it until after OpenAI approval removes even the theoretical concern.

---

## Summary

Two services. One codebase. One backend. One tool registry.

The boundary is at the widget layer. Everything below the widget is shared. Everything above it (the host bridge API) diverges by platform and must be maintained separately.

This is the minimum viable structure for supporting two platforms long-term without tool drift.
