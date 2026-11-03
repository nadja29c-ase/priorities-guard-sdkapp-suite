# Investigation: PG-OpenAI MCP `POST /mcp` → 400 + `anyio.ClosedResourceError` (2026-11-03)

**Type:** read-only root-cause analysis. No code, config or production changes were made.
**Trigger:** during a PG ChatGPT tool call on 2026-11-03 16:35 UTC (user `e974b9ad`), the PG-OpenAI MCP
logged 68 × `POST /mcp` → 400, each followed by an error-level traceback, coinciding ~1:1 with
`record_widget_diagnostic` calls. Found while verifying the rate-limit hotfix `4822aef`; **unrelated to it**
(the PG MCP was last deployed 2026-09-15; the hotfix touched only the shared backend).

**Status:** cause narrowed to one SDK code path family and reproduced locally; the exact trigger in
production is **not 100% confirmed** (see §2). No fix proposed here — a fix needs its own briefing.

## 0. What is deployed

| | Value | Source |
|---|---|---|
| Service | `priority-guard-pg-mcp` (`srv-d64ea0khg0os73d588t0`) | Render |
| Deployed commit | `9c8bf38` (deploy `dep-dakj6th42hec73ap4eu0`, live since 2026-09-15) | Render deploy list |
| MCP Python SDK | `mcp` 1.12.4 | `poetry.lock` at `9c8bf38` |
| Transport | `FastMCP(..., streamable_http_path="/mcp", stateless_http=True)` | `mcp_server/priority_guardian/server.py:665` at `9c8bf38` |
| `mcp_server/priority_guardian/` | identical between `9c8bf38` and `3b926e7` (`git diff --stat` empty) | git |

SDK file:line references below are to `mcp` 1.12.4 (`mcp/server/streamable_http.py`, `streamable_http_manager.py`,
`transport_security.py`), the version in the deployed lock file.

## 1. Why ~66 diagnostic calls per render — host events, not a loop

**Confirmed (code + logs).**

- `PG_DIAG_FULLSCREEN = true` is hard-coded (`widget-react/src/App.tsx:19` at `9c8bf38`), added in `d9d994b`
  (2026-05-24, Increment 89) and never changed since (`git log -S`). The reporter is marked
  "Temporary — remove after fullscreen flash-revert bug is diagnosed" (`widgetErrorReporter.ts:81`).
- Every `openai:set_globals` event from the host sends **two** diagnostic tool calls once the widget is
  initialised: `set_globals` (`App.tsx:736`) and `displayMode.change` via `logDisplayModeChange`
  (`App.tsx:131`, called at `:758`/`:761`). Each mount sends one more (`App.tsx:708`).
- `reportWidgetDiagnostic` has no retry; it is capped at 200 per widget session
  (`widgetErrorReporter.ts:88-119`). Errors are swallowed (fire-and-forget).
- Better Stack, 16:35–16:36 UTC, `e974b9ad`: 2 widget sessions (2 `sid`s, 2 `mount`s), 33 `set_globals`,
  33 `displayMode.change` (`hostSync`) = 68 diagnostics.
- So the volume = number of host `set_globals` events × 2. ChatGPT fired ~33 in ~37 s here; for `f0c610f7`
  (10:24 UTC) it was ~4–5 per widget session. Why the host fires that often is not visible from our side.

## 2. What returns the 400

**Narrowed and reproduced locally; production trigger not confirmed.**

Production sequence, 16:35:32 UTC (one tool-call cycle):

| Request | Status | Server time | Notes |
|---|---|---|---|
| 1 | **400** | 4.6 ms | no `Processing request …` line → rejected inside the SDK transport, before our handlers |
| 2 | 200 | 4.2 ms | (initialize) |
| 3 | 202 | 3.4 ms | (notification, e.g. `notifications/initialized`) |
| 4 | 200 | 653 ms | `CallToolRequest` → `get_priorities` succeeded |

Hourly totals fit 2×200 + 1×202 + 1×400 per tool call (16:00 UTC hour: 140 / 70 / 70).
The `BearerAuthMiddleware` (`server.py:209`) passed these requests (it returns 401, not 400), so they were authenticated.

**The traceback is a consequence, not the cause.** In stateless mode the manager creates a transport per request
and terminates it afterwards (`streamable_http_manager.py:146-193` → `terminate()`, `streamable_http.py:623-630`,
logging `Terminating session: None`). When the request returned early with an error, the message router then
reads from the closed stream and logs `Error in message router` / `anyio.ClosedResourceError`
(`streamable_http.py:880`). It occurs after 400s only, never after 200s.

**SDK paths that can return 400 to an authenticated POST (1.12.4):**

| | Trigger | Location |
|---|---|---|
| **H1 (most likely)** | `MCP-Protocol-Version` header not in `2024-11-05`, `2025-03-26`, `2025-06-18` | `streamable_http.py:706-723` |
| H2 | body is not a valid JSON-RPC message | `streamable_http.py:347` |
| H3 | malformed JSON | `streamable_http.py:340` |
| (unlikely) | Content-Type not JSON — would also log `Invalid Content-Type header`, not seen; ChatGPT's `application/octet-stream` is rewritten by `MCPContentTypeAndAcceptFixMiddleware` (`server.py:530`) | `transport_security.py:111` |

The Origin/Host checks (`transport_security.py:120,125`) are inactive: no `transport_security` is configured.

**Why H1 is most likely:** the 400 is the first request of every cycle and is followed by a fresh `initialize`,
which fits a client that tries a newer protocol version, is rejected, and re-negotiates. Initialize requests are
exempt from the header check, and the server answers with `2025-06-18` (see §2a, probe E).

### 2a. Local reproduction (SDK 1.12.4, localhost only)

PG MCP from the working tree (identical to `9c8bf38` for `mcp_server/priority_guardian/`), run on
`127.0.0.1:8798` with `ENV=dev`. JWT validation pointed at a throwaway local RSA key served as JWKS from
`127.0.0.1:8799` — no production key, token or endpoint involved. Request shape:

```bash
curl -s -w '\nHTTP %{http_code}\n' -X POST http://127.0.0.1:8798/mcp \
  -H "Authorization: Bearer $LOCAL_TEST_TOKEN" -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H 'MCP-Protocol-Version: 2025-11-25' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

| Probe | `MCP-Protocol-Version` | Body | Status | Response body | Router traceback |
|---|---|---|---|---|---|
| A | `2025-11-25` | `tools/list` | **400** | `{"jsonrpc":"2.0","id":"server-error","error":{"code":-32600,"message":"Bad Request: Unsupported protocol version: 2025-11-25. Supported versions: 2024-11-05, 2025-03-26, 2025-06-18"}}` | **yes** |
| B | `2026-07-28` | `tools/list` | **400** | same, with `2026-07-28` | **yes** |
| C | `2025-06-18` | `tools/list` | 200 | tool list | no |
| D | (none) | `tools/list` | 200 | tool list | no |
| E | `2025-11-25` | `initialize` asking `2025-11-25` | 200 | `"protocolVersion":"2025-06-18"` | no |
| F | `2025-06-18` | `{"jsonrpc":"2.0","id":3}` (H2) | 400 | `-32602 Validation error …` | **yes** |
| G | `2025-06-18` | `{not json` (H3) | 400 | `-32700 Parse error …` | **yes** |

For each 400 the server log shows exactly the production signature: `Terminating session: None`, `http.request … 400`,
`Error in message router` with `anyio.ClosedResourceError`, and no `Processing request` line.

**Result:** H1 reproduces the production signature and fits the retry pattern. But H2 and H3 produce an
**identical** server-side log, so the logs alone cannot distinguish them. Confirming H1 needs the production
request's `MCP-Protocol-Version` header or the 400's response body, neither of which is logged today
(adding a log line is a code change → own briefing).

## 3. Why `f0c610f7` had no 400s — a different client variant

**Evidence only.**

| User / time (UTC) | User agent | Requests per tool call | 400s |
|---|---|---|---|
| `f0c610f7`, 10:24–10:25 | `openai-mcp/1.0.0` | 1 POST → 200, no handshake | 0 |
| `e974b9ad`, 13:09–13:25 and 16:35 | `openai-mcp/1.0.0 (Codex)` | 4 (400, 200, 202, 200) | 1 per tool call |

The difference is in the ChatGPT client, not the user or the server. The isolated 400s on 2026-11-01 (`(Codex)`),
2026-11-02 and 2026-11-03 02:41 (`openai-mcp/1.0.0`) each occurred within a 4-request cycle of the same kind.

## 4. User impact — none observed server-side

**Inferred, not observed client-side.** Each rejected request is followed by a successful one in the same cycle:
`tool.get_priorities.success` ×2, widget served (`resource.read.serving_widget`), all 66 diagnostics logged.
Cost: one extra round trip + re-initialize per tool call; one error-level traceback per call in Better Stack
(inflates error counts); ~70 extra MCP requests per render from always-on diagnostics.

## 5. Before 2026-10-31? Yes — since at least 2026-10-17

Raw logs are kept ~3 days; Better Stack metrics (PG MCP source `2397712`, label `Event`, from 2026-10-01):

| Day | `widget.diagnostic` | level=error | Note |
|---|---|---|---|
| 2026-10-08 | 355 | 3 | diagnostics without error spike |
| 2026-10-16 | 209 | 3 | " |
| 2026-10-21 | 200 | 1 | " |
| 2026-10-17 | 17 | **20** | errors ≈ diagnostics (user `dcbba8c2`) |
| 2026-10-27 | 95 | **103** | " (user `16aef972`) |
| 2026-10-28 | 19 | **22** | " |
| 2026-10-29 | 42 | **45** | " |
| 2026-11-03 | 173 | **140** | " (`e974b9ad`; `f0c610f7`'s 42 without errors) |

Baseline on other days: 1–5 errors. The split is per session, not per user (`dcbba8c2` had 21 diagnostics with
1 error on 2026-10-01), consistent with a per-session client variant (§3). The diagnostic volume itself predates
the errors.

## 6. Related findings (read-only)

- **PG-Claude** (`priority-guardian-claude-mcp`, `srv-d6vbrt9r0fns73c6n080`) runs `e180686` (deployed 2026-08-24),
  also `mcp` 1.12.4 and also `FastMCP(..., stateless_http=True)` (`server_dupl.py:820`). It would reject the same
  protocol versions the same way if a client sent them. Its widget is a **separate** source tree
  (`mcp_server/priority_guardian_claude/widget-react/`) and bundle (`widgets/pg-dashboard-claude.html`); neither
  contains `record_widget_diagnostic`, `reportWidgetDiagnostic` or `PG_DIAG_FULLSCREEN`. PG-Claude does not ship
  logs to Better Stack, so whether it sees such 400s is unknown.
- **Increment 89 status:** the flash-revert bug was **diagnosed** (H2, host `set_globals` overwriting local
  fullscreen — confirmed in a dev-mode capture, per `claude increments/PRIORITY_GUARDIAN/pg_v1.0/inc_89.10.md:4`) and a
  fix shipped in `c1fddf1` (2026-05-25, desktop fullscreen intent guard). `inc_89.10.md:143` keeps diagnostics on
  until "v15 is approved AND the fix is verified by production diagnostic events", with cleanup "in a later
  increment". No record of that production verification or of a cleanup increment was found in the repo, and
  `PG_DIAG_FULLSCREEN` is still `true`. Today's logs (13:09 UTC, `e974b9ad`) do show 16 `sync-ignored` /
  `handleSetGlobals.intentGuard` events after a fullscreen click — i.e. the guard firing in production.

## 7. Not verified

- Which of H1–H3 triggers the production 400 (no header or response-body logging).
- That the 2026-10-17 and 2026-10-27–29 sessions used the `(Codex)` client (raw logs expired; correlation only).
- Why ChatGPT fires `set_globals` ~33 times in ~37 s for some sessions.
- Client-side user experience (no client-side visibility).
- Whether a newer MCP SDK accepts these clients (dependency change affecting all services → own briefing).
- Whether PG-Claude receives protocol-version 400s (no Better Stack logs for PG-Claude).
- Whether the Inc 89.10 fix was formally verified in production / approved for diagnostic removal (no record found).
- The local reproduction used requests that need no backend (`tools/list`, `initialize`); `tools/call` paths
  were not exercised locally (the protocol-version check runs before message dispatch, so the method should not matter).
