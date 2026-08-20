# MindSort-Claude — Compliance Assessment

**Audited:** 2026-08-19 · **Against:** `CLAUDE_COMPLIANCE_REQUIREMENTS_CANONICAL.md` (129 rows)
**Codebase at:** `99113d1` (working tree clean for all audited files)
**Live surface:** `mindsort-mcp.priority-guard.com` (srv-d90din3sq97s7399nbl0), deploy `dep-da27ed3ncjis73fe7k90`

---

## ⚠️ Three caveats that bound this entire document

**1. The requirements corpus is knowingly incomplete.** §13 of the canonical doc declares **11 obligations
never read** — 5 binding documents (Trademark Guidelines, Usage Policy, Universal Usage Standards,
High-Risk Use Case requirements, supported-countries policy), 3 referenced requirement surfaces, 3 weakly
sourced. Policy §1A alone makes four of them binding. **A clean result here does not mean "compliant."**

**2. Row count is 129, not 128.** `P3D-i` (`PORTAL`, canonical line 269) is a distinct row that the
audit record's "128 canonical rows" appears to miss. Verified with two independent parsers.

**3. IDK is a real verdict and appears 41 times.** Portal fields, listing entries, contractual warranties
and in-client rendering are **not determinable from a codebase**. Marking them green on code-reading alone
would be fabrication. Where a row needs human observation, the exact check is stated.

---

## Verdict summary

**As first audited (2026-08-19, at `99113d1`)**, with one row re-classified 2026-08-20: **M2** moved IDK → Partly once contrast was
actually computed (8→9 Partly, 41→40 IDK). Total unchanged at 129.

| Verdict | Count |
|---|---|
| **Fulfilled** | 62 |
| **Partly fulfilled** | 9 |
| **Not fulfilled** | 4 |
| **IDK — not determinable from codebase** | 40 |
| **N/A — conditional precondition does not hold** | 14 |
| **Total** | **129** |

### ⚠️ Remediation status — read this before quoting any verdict above

Two of the four Not-fulfilled rows have since been fixed. **Neither is marked Fulfilled**, because
code-fixed ≠ verified-live and this document does not award green on a commit:

| Row | Fixed in | Status now |
|---|---|---|
| **R7a** — diagnostic tool advertised but always 403 | `5c48d05`, **deployed** (`dep-da2qpjugekts73e1nih0`, live 2026-08-19) | **Fixed, pending live confirmation.** Unit + integration green and the OpenAI surface verified untouched. Outstanding: in-client `tools/list` shows exactly six tools and `_diagnostic_tiny_widget` is absent |
| **M3** — inline card ignored safe-area insets | `77eb332`, live since v11 | **Implemented, UNEXERCISED.** 6 tests incl. a dynamic host-context update; 3 fail against pre-fix code. The host reported **zero insets** on the surfaces tested, so the fix is a no-op there and rendered padding is identical to pre-fix — nothing to observe. Not marked Fulfilled: that would claim verification of a path that never ran. Exercising it needs **mobile** (keyboard up), where the test is a tap, not a look |
| **M20** — loading skeleton | `efa1ad6` v12 + `d38601f` v13, live | **Implemented; runtime behaviour measured, not merely asserted.** Visible and correct on slow loads (~1620ms); imperceptible on fast loads (~18ms, zero paints) because the widget fetches nothing at mount. No timer added. Structural compliance unchanged — the `role="status"` announcement claim remains weaker than first recorded |
| **M1** — light/dark | — | **Dark mode confirmed on-device 2026-08-20.** Supports M1; does *not* discharge M2's contrast measurement |

`P3A` (privacy policy) and `A24` (DCR over CIMD) are unchanged. When the two live checks are done,
move those rows to Fulfilled and update the counts — **not before**.

### Bucket (derived from Level + ⚠️SILENT, stronger level wins)

| Bucket | Rule | Count |
|---|---|---|
| MUST — listing-blocking | `POLICY`/`TERMS`/`PORTAL`/`DOC-CONSTRAINT` | 97 |
| MUST — production-breaking | `⚠️SILENT` at any level | 2 (`M3`, `X2`) |
| MUST — reviewer-rejection | `REVIEW-ONLY` | 5 |
| MUST — conditional | `CONDITIONAL`, precondition holds | 16 |
| NICE | `SPEC` / `RECOMMENDED` | 9 |

---

# NOT FULFILLED (4)

## ❌→✅ R7a — `REVIEW-ONLY` — reviewer-rejection · **mindsort-only**
> **FIXED in `5c48d05`, deployed.** `CLAUDE_ADVERTISED_TOOLS` allowlist in `tools_list_dupl.py`; Claude now advertises 6, the shared registry still carries 7 for OpenAI. Live in-client confirmation still outstanding. Original finding preserved below.

> *"Every tool must return a successful response when called with valid parameters; generic errors fail review."*

**`_diagnostic_tiny_widget` is advertised to Claude but can never succeed.**

- It self-registers into the shared registry (`clarity/tools/diagnostic_widget.py:132-143`) with
  `REQUIRED_SCOPES = []`.
- `list_tools_for_claude()` iterates **all** of `TOOL_REGISTRY` with **no visibility filter**
  (`mindsort_claude/tools_list_dupl.py:78-82`, and its own docstring says *"No visibility filter"*).
- It is **absent** from `mindsort_claude/config.py:451-459` `TOOL_SCOPES`.
- Scope enforcement **fails closed on unknown tools** — `clarity/mcp_auth.py:398-407` raises
  `InsufficientScopeError` for any tool not in `TOOL_SCOPES`.

So Claude is shown a 7th tool whose description opens *"INTERNAL DIAGNOSTIC TOOL - DO NOT USE IN NORMAL
CONVERSATION"* and which returns 403 on every invocation. A reviewer exercising every tool (which S12
requires them to attest **you** did) hits a hard failure.

**Also degrades:** `P2B` (descriptions must match actual functionality), `S12`/`R11` (cannot attest to
running every tool successfully), `P2A`.

**Provenance (git-verified, added after the first draft of this report):** the tool was added
**2026-07-05** in commit `1bbd16c` — *"feat(mindsort): Add inc_91 diagnostic increment for widget render
isolation"* — a sanctioned increment with a briefing (`claude increments/PRIORITY_GUARDIAN/pg_v1.0/inc_91.md`)
and 18 unit tests (`tests/unit/mcp_clarity/test_inc91_diagnostics.py`). It has **never been modified since**
(one commit total). It was built for the **OpenAI/ChatGPT** surface: the commit message cites a
`cdn.openai.com` CSP-matching fix, and the tool's `_meta` is entirely OpenAI-shaped
(`openai/outputTemplate`, `openai/toolInvocation/*`, `openai/widgetAccessible`).

**Why it leaked into Claude:** MindSort-Claude was created **2026-06-28** (`5ae514b`), a week *before* the
diagnostic landed. The diagnostic went into **shared** `clarity/tools/`, self-registers via the import at
`clarity/tools/__init__.py:152`, and **both** list builders advertise the entire registry with no filter.
Nobody added it to MindSort-Claude's separate `TOOL_SCOPES` — so on Claude it is advertised but fails closed.

**⚠️ Do NOT delete it — it is live and functional on OpenAI.** `clarity/config.py:300` grants it
`"_diagnostic_tiny_widget": []`, so on the OpenAI surface it *is* callable. Deleting the tool or its
registration would remove a working OpenAI diagnostic. The Claude-side defect is the **missing filter**, not
the tool's existence.

**Fix shape (Claude side only):** exclude it from `list_tools_for_claude()`
(`mindsort_claude/tools_list_dupl.py`) — either an explicit deny-list or skipping `_`-prefixed names.
Not attempted — out of scope for an audit.

**Secondary note:** on OpenAI it requires **no scopes at all** (`[]`), so any authenticated user can invoke
it. It is `read_only_hint=True` and side-effect-free, so the exposure is low, but it is an unscoped tool.

## ❌→✅ M3 — `RECOMMENDED` **⚠️SILENT** — production-breaking · **mindsort-only**
> **FIXED in `77eb332`** (live since v11). Inline root padding is now `16px + hostContext.safeAreaInsets` per side, read at render.
> **DISPOSITION — implemented per the documented contract; UNEXERCISED rather than verified.** The fix is a no-op whenever the
> host reports zero insets: rendered padding is then byte-identical to the pre-fix `16px`, so there is no visual before/after to
> observe. On the surfaces tested (desktop web) the host reported zero insets, so the code path that the fix exists to serve was
> never exercised. The meaningful surface is **mobile** — keyboard up, nav bar present — where the test is a *tap*, not a look:
> is the card's bottom-edge "Open full board" button still reachable with the composer focused?
> **Deliberately NOT marked Fulfilled.** Marking it green off a desktop glance would claim verification of a path that did not
> run. To exercise it: inspect the inline `<main>`'s computed padding — `16px` on all sides means zero insets reported;
> anything larger means the host is sending them and the fix is doing its job. Original finding preserved below.

> *"The interactive portion SHOULD be rendered inside `safeAreaInsets`… The user won't be able to interact with anything rendered outside the safe area."* **Explicitly not mobile-specific.**

**Insets are honoured in fullscreen only. The inline path ignores them entirely.**

- Applied once, in `FullscreenBoardView`: `widget-react/src/App.tsx:1542`
  (`padding: ${safeAreaInsets.top + 16}px …`).
- Passed only on the fullscreen branch: `App.tsx:804-810` (`if (displayMode === 'fullscreen')`).
- The inline render path never reads `hostContext.safeAreaInsets`.

The inline card's only footer action — **"Open full board"** (`App.tsx:951-954`) — sits at the bottom
edge, exactly where the row warns the composer overlays. This is the canonical ⚠️SILENT failure: no error,
no log line, the button simply stops responding.

**Direct quote from the live guidelines (fetched 2026-08-19), which is stronger than the canonical row's
paraphrase:** *"Read `hostContext.safeAreaInsets.{top, right, bottom, left}` (in pixels) and apply them as
padding on your root container… Safe areas are **not mobile-specific: on web and desktop the composer can
overlay the bottom of an inline app, so avoid placing interactive controls flush against any edge**."*
That is a precise description of the current inline card: a single interactive control, flush against the
bottom edge, with insets read but never applied on that path.

**Note:** `prefersBorder: false` (`handlers/resources_dupl.py:115`) makes this *worse*, not neutral — M14
states borderless runs edge-to-edge with **no host padding**, "so honouring `safeAreaInsets` becomes
essential."

**Needs live observation to confirm impact** (I cannot render in the client), but the code gap is certain.

## ❌ P3A — `CONDITIONAL`, precondition **holds** — listing-blocking · **shared**
> *"Provide a clear, accessible privacy policy link explaining collection, usage **and retention**."*

Precondition — *Software that collects user data **or** connects to a remote service* — holds on both
counts. This is the **Framer privacy-policy gap**, and it is a binding row, not a nice-to-have.
Paired with `T4` (same obligation as a contractual warranty) and `S5` (portal requires the URL).

**Not determinable from the codebase whether a policy exists at a URL** — but you have stated it does not.
Recorded here as Not fulfilled on your own account, not on evidence I gathered.

## ❌ A24 — `RECOMMENDED` — NICE · **shared**
> *"For servers expecting high traffic from the directory, prefer CIMD or `oauth_anthropic_creds` over DCR."*

AS advertises `registration_endpoint` and **not** `client_id_metadata_document_supported`
(live `/.well-known/oauth-authorization-server`), so Claude uses **DCR** — a new client registered per
fresh connection. Explicitly soft; listed so it is not mistaken for satisfied.

---

# PARTLY FULFILLED (8)

| ID | Level | Finding | Evidence |
|---|---|---|---|
| **P2B** | `POLICY` | Six tools describe real functionality accurately; the 7th (`_diagnostic_tiny_widget`) is advertised and non-functional | see R7a |
| **M20** | `DOC-CONSTRAINT` | *"Skeleton screens, not spinners… match the layout structure of the final content."* **Original finding:** a centred `Loading...` text block — not a spinner, but not a skeleton either. **Now implemented** (`efa1ad6` v12, footer defect fixed `d38601f` v13): mirrors the loaded card's header + 3 cluster rows. **Runtime behaviour MEASURED** (temporary instrumentation `e356da2`, removed `56d6ce0`): on a *slow* load the skeleton commits at 49ms, paints through two rAFs and stays visible to ~1620ms — it works and is seen. On a *fast* load it commits at 41ms, the tool result lands at 58.8ms and it unmounts at 61.3ms — **~18ms, zero paints**. Cause: the widget performs **no fetch at mount** (its only server round-trip is `handleViewRemainingContent`); board data arrives inside the tool result that caused the host to render it, so on a fast path there is nothing to wait for. **No minimum-display timer was added** — it would inflate an 18ms path to 300ms to display a loading state for a load with nothing to load. **Structural compliance is separate and unchanged**; see the `role="status"` caveat under M2 | `App.tsx` `!isInitialized` branch |
| **P5B** | `POLICY` | *"Frugal with tokens."* Tool descriptions total **~12.7 KB** and ship on every conversation: `organize_thoughts` 3,788 chars, `edit_board` 3,145, `start_prioritization_flow` 2,069, `read_board_before_editing` 1,974. Much is behavioural framing rather than "what it does / when to call it" | measured from `TOOL_REGISTRY` |
| **P3G** | `POLICY` | *"Maintain the Software and address issues within reasonable timeframes."* MCP SDK pinned **1.12.4**; the `ClosedResourceError` message-router race (upstream #1363) is fixed in **1.23.2**, and production shows **10 tracebacks / 10 fast-fail 400s** in one capture | `poetry.lock:1229`; `attachment.md` |
| **M5** | `DOC-CONSTRAINT` | *"Maximum 2 actions, at the bottom of the card."* Footer has 1 action (**Open full board**, `App.tsx:951`); an **overflow action row** (`App.tsx:1376`) renders *inside* an expanded cluster, not at the bottom. Count is within 2; **placement** deviates | `App.tsx:951, 1376` |
| **M6** | `DOC-CONSTRAINT` | *"Maximum 4–5 data points."* Inline shows a truncated cluster list bounded by a **self-imposed** ~500px budget (`LAYOUT.maxHeight`), not by a data-point count; visible rows vary with content. ⚠️ The 500px is **the app's own engineering budget, not an Anthropic requirement** — see the M4 note | `App.tsx:84, 500-526` |
| **A7** | `DOC-CONSTRAINT` | AS must be reachable from `160.79.104.0/21`. MCP host demonstrably reachable (production logs show `Claude-User` from `160.79.106.x` succeeding), but the **AS is a different host** (`www.priority-guard.com`, Cloudflare-fronted) and was not tested from that range | Render request logs |
| **M2** | `DOC-CONSTRAINT` | **WCAG AA contrast: 4 failures, all light mode, all on Anthropic's OWN host-token pairings.** `--color-text-tertiary` (#73726C) on `--color-background-secondary` (#F5F4ED) = **4.38:1** at three **12px** sites — header count summary, footer "+N more clusters", empty-state "No clusters yet". `--color-text-info` (#3266AD) on `--color-background-info` (#D6E4F6) = **4.48:1** (P3 badge). 12px is normal text (large = ≥24px, or ≥18.66px bold), so **4.5:1 applies** and the 3:1 allowance does not reach them. **Dark mode: 11/11 pass.** Skeleton bars **1.35–1.49:1** vs the 3:1 graphical threshold — arguably exempt (decorative, `aria-hidden`, transient). **M2/M18 TENSION, sourced:** M18 (`raw 220`) mandates host tokens for all structural elements; M2 (`raw 278`) mandates WCAG AA. These pairings are the published palette used as instructed — the failure is in the tokens, not our choices. ⚠️ **MEASUREMENT CAVEAT — testing outside Claude misleads:** `RANK_COLORS` fallbacks (`utils.ts:242-243`, #1E40AF on #DBEAFE = **7.15:1**) are MORE accessible than the resolved host tokens (**4.48:1**). `useHostStyles` resolves the `var()` in Claude so the fallback never paints — always measure against resolved host values, never the fallbacks. **Disposition:** the three tertiary sites are fixable to `--color-text-secondary` (**9.88:1**, still a host token, zero M18 tension) — batch into the next widget rebuild. The P3 badge is **logged, not fixed**: `RANK_COLORS` is shared with the OpenAI surface, so it carries cross-surface blast radius, and 4.48 is marginal. Not submission-gating (`DOC-CONSTRAINT`, not `PORTAL`) | computed from `design-guidelines.raw.md:284-305` token table |
| **P3F** | `POLICY` | Ownership of `mindsort-mcp.priority-guard.com` and `www.priority-guard.com` is evidenced by control; the widget renders **only bundled** assets (0 external `<script src>`), CSP `resourceDomains` lists only `https://assets.claude.ai` (Anthropic's own). **Verification of domain ownership is a portal/registrar matter I cannot see** | `resources_dupl.py:120`; built bundle |

---

# FULFILLED (62) — with evidence

## §1 Safety & Security
| ID | Verdict | Evidence |
|---|---|---|
| P1B | ✅ | No prompt-injection or guardrail-evasion constructs; tool guidance is facilitation copy in `DESCRIPTION` blocks, all human-readable |
| P1C | ✅ | Board data scoped per `user_id` from validated JWT; no third-party data ingress |
| P1D | ✅ | **No user content in any log line.** Logs carry event names + counts only (`start_prioritization_flow.success priority_count=…`). Swept every `logger.*` call in `clarity/tools/` and `mindsort_claude/` for thought/text/content/verbatim payloads — none. *(One note: `server_dupl.py:624` logs 120 bytes of an upstream **OAuth /register** response as hex — not conversation data.)* |
| P1E | ✅ | No third-party content reproduced |
| P1F | ✅ | No tool reads Claude memory, chat history or uploaded files; inputs are explicit user-supplied strings |

## §2 Tool & capability descriptions
| ID | Verdict | Evidence |
|---|---|---|
| P2A | ✅ | Every description states what it does **and** when to call it; several open with explicit preconditions (`edit_board`: *"CRITICAL PRECONDITION…"*, `load_saved_board`: *"ONLY call this tool when…"*) |
| P2C | ✅ | Naming is domain-specific (`organize_thoughts`, `start_prioritization_flow`); no collision framing with other directory software |
| P2D | ✅ | No tool instructs Claude to call external software |
| P2E | ✅ | No interference language |
| P2F | ✅ | All guidance is static in-repo strings; nothing fetched at runtime to steer behaviour |
| P2G | ✅ | No hidden/encoded instructions; all `DESCRIPTION` and `assistant_guidance` text is plain readable English |

## §5 MCP server requirements
| ID | Verdict | Evidence |
|---|---|---|
| P5A | ✅ | Errors are structured and actionable — `assistant_guidance {action, instruction}` on every failure path in all 6 production tools (5 in `start_prioritization_flow`, 5 `load_saved_board`, 4 each `edit_board`/`organize_thoughts`/`read_board_before_editing`, 3 `delete_my_data`) |
| P5C | ✅ | Longest tool name 25 chars (`start_prioritization_flow`, `read_board_before_editing`) — limit 64 |
| P5D | ✅ | OAuth 2.0 + PKCE S256 over TLS; valid public cert chain on both hosts (live probes) |
| P5E | ✅ | `title`, `readOnlyHint`, `destructiveHint`, `openWorldHint` set on every tool (`tools_list_dupl.py:84-92`); `start_prioritization_flow` correctly overridden `destructiveHint=True` for Claude (`:36`) |
| P5F | ✅ | Streamable HTTP (`FastMCP(..., streamable_http_path="/mcp", stateless_http=True)`, `server_dupl.py:426`) |
| P5G | ✅ | N/A-adjacent (remote, not local) but dependencies are lockfile-pinned and the widget bundle is reproducible byte-for-byte |
| R1 | ✅ | Read and write tools are separate: read-only `load_saved_board`, `read_board_before_editing`; write `organize_thoughts`, `edit_board`, `start_prioritization_flow`, `delete_my_data`. No tool accepts both safe and unsafe operations |

## §7 Authentication & OAuth — **all live-verified**
| ID | Verdict | Evidence |
|---|---|---|
| A1 | ✅ | `code_challenge_methods_supported: ["S256"]` advertised; PKCE enforced |
| A2 | ✅ | Same — live AS metadata |
| A3 | ✅ | `POST /mcp` unauthenticated → **401** + `WWW-Authenticate: Bearer resource_metadata="…/.well-known/oauth-protected-resource/mcp", scope="clarity.write"` |
| A4 | ✅ | PRM `resource` = `https://mindsort-mcp.priority-guard.com/mcp` — **includes the path**, matching what the user enters |
| A5 | ✅ | `authorization_servers: ["https://www.priority-guard.com"]`, single entry |
| A6 | ✅ | RFC 8414 **and** OIDC discovery both 200 |
| A8 | ✅ | `https://claude.ai/api/mcp/auth_callback` **and** `claude.com` variant registered (`backend/core/config.py:62-63`) |
| A9 | ✅ | Loopback validator accepts `localhost` + `127.0.0.1`, **port ignored**, `/callback` among approved paths (`validators/client_metadata.py:32-58`) |
| A10 | ✅ | Live probe with a dead refresh token returns **`{"error":"invalid_grant"}`** — RFC 6749-compliant, not a custom code |
| A11 | ✅ | Rotation: old token revoked and new issued in the same response (`token_service.py:353-400`, logs `old_jti`→`new_jti`) |
| A12 | ✅ | `/token` accepts `application/x-www-form-urlencoded` (live probe) |
| A13 | ✅ | `/register` parses `application/json` — 422 field-validation, i.e. body was read (live probe; no client created) |
| A14 | ✅ | Discovery 0.18 s, token/register sub-second — limits are 10 s / 30 s |
| A15 | ✅ | `grant_types_supported: ["authorization_code","refresh_token"]` — no `client_credentials` |
| A19 | ✅ | No authorization decision keys on `clientInfo.name`/`version` anywhere in the auth path |
| A22 | ✅ **⚠️SILENT** | Auth failure returns a true **401** with `WWW-Authenticate`, not a 200+`isError` (live probe) — the row's silent-failure mode is avoided |
| A23 | ✅ | `scope="clarity.write"` present in the challenge, so consent is not over-broad |

## §8/§9 MCP Apps — display, widget domain, CSP, theming
| ID | Verdict | Evidence |
|---|---|---|
| M1 | ✅ | Zero raw hex colours outside `var(--token, #fallback)` form; swept all `background/color/border/fill/stroke` literals in `App.tsx`. **Confirmed on-device 2026-08-20: dark mode renders correctly.** Note this supports M1 only — it is *not* a WCAG AA contrast measurement, which M2 requires and which is now measured — see the M2 finding |
| M4 | ✅ | **No nested vertical scroll anywhere** — zero `overflow-y: auto/scroll` in `App.tsx` or `main.css`; `main.css:79` uses `overflow: hidden`. Content auto-fits via truncation + an overflow affordance |
| M7 | ✅ | Accordion expand/collapse in place; no drill-ins, breadcrumbs, menus or popovers |
| M9 | ✅ | 44 px touch targets explicit (`LAYOUT.boardHeaderHeight/collapsedRowH/overflowActionRowH = 44`; `minHeight/minWidth: '44px'` at `App.tsx:964`) |
| M10 | ✅ | No fixed-width layout, no fixed breakpoints, `width: 100%`, no side margins |
| M12 | ✅ | `capabilities.availableDisplayModes: ['inline','fullscreen']` (`App.tsx:306-307`) |
| M15 | ✅ | Mobile fullscreen supported via host negotiation; no camera/mic/location use |
| M16 | ✅ | **No chat UI** — zero `<input>`, `<textarea>`, `contenteditable` or placeholder in the widget |
| M18 | ✅ | All structural colour via host tokens (`--color-background-*`, `--color-text-*`, `--color-border-*`); brand colour used only for rank accents, which the source explicitly permits (*"semantic accent colors signal status"*) |
| M19 | ✅ | 5 SVGs, **5** with `stroke="currentColor"` — monochromatic, outlined, host-token coloured. **No emoji** anywhere in the widget |
| X4 | ✅ **⚠️SILENT** | `html, body { margin: 0; background: transparent; }` present in source (`main.css:8-14`) **and in the built bundle** — verified in the shipped artifact, not just the source |
| X5 | ✅ | `<meta name="color-scheme" content="light dark" />` present in the **built** HTML |
| X7 | ✅ | `onhostcontextchanged` assigned inside `onAppCreated`, which the SDK fires **before** `connect()` (`App.tsx:331`, with the reasoning documented in-line at `:315-326`) |
| X8 | ✅ | `resourceDomains` = `["https://assets.claude.ai"]` only — Anthropic's own origin; no public CDN allowlisted; all third-party code bundled |
| X9 | ✅ **⚠️SILENT** | `useApp({...})` with **no explicit transport** (`App.tsx:304`) — SDK selects Claude vs ChatGPT |

## §11/§12
| ID | Verdict | Evidence |
|---|---|---|
| S3 | ✅ | Server URL is `https://mindsort-mcp.priority-guard.com/mcp` |
| S4 | ✅ | Every tool carries `title` + `readOnlyHint`/`destructiveHint` (`tools_list_dupl.py:84-92`) |
| S13 | ✅ | Custom-connector testing path is the production service; no staging assumed |
| PUB1 | ✅ | Tool surface is served from the live registry; no resubmission coupling in code |

---

# IDK — not determinable from the codebase (41)

## Needs the submission portal / listing (25)
`P3B` (verified contact + support channels) · `P3C` (documentation of how it works / troubleshooting) ·
`P3D` (test account) · `P3D-i` (**fully populated** test account + step-by-step setup instructions) ·
`P3E` (≥3 working example prompts) · `DOC1` (public documentation by publish date) · `S1` (Team/Enterprise
org) · `S2` (Owner/Primary Owner submitter) · `S5` (name ≤100, tagline ≤55, description ≤2,000, 1–5
categories, doc URL, privacy URL, support contact, icon) · `S6` (permanent slug) · `S7` (**3–5 PNG
screenshots ≥1000px, no prompt visible, no video/GIF**) · `S8` (seven compliance acknowledgments) ·
`S9` (data-handling declarations) · `S12` (attestation you ran every tool — **currently un-attestable, see
R7a**) · `S14` (skills bundling) · `PUB3`, `PUB4` (listing edits / delisting process) · `L2`, `L3`, `L4`,
`L5`, `L6` (external-link allowlist entries — **all `PORTAL`, `L2`/`L5` ⚠️SILENT**) · `T3` (accuracy
warranty over every portal field) · `P4A`–`P4C` partially rest on listing claims

> **`L2`/`L5` are ⚠️SILENT and portal-side.** If you list any external-link origin, unowned or malformed
> entries are removed/ignored **without error** and users then get a confirmation modal on every link.

## Needs human observation in the Claude client (7)
| ID | The exact check to run |
|---|---|
| **M2** | ~~WCAG AA contrast measurement~~ — **MEASURED 2026-08-20, see the M2 finding above.** Still outstanding for M2: **keyboard-only traversal** and a **screen-reader pass** *(the `sr-only` inherited-priority announcement is code-verified present but its spoken output is unverified; and the skeleton's `role="status"` announces in no case — the branch is never re-entered)* |
| **M3** | Inline card on web/desktop with the composer focused — is **"Open full board"** still tappable? |
| **M4** | Confirm the host does not clip the inline card in practice. ⚠️ **There is no published pixel limit** — verified against the live guidelines 2026-08-19, which say only *"Height: auto-fits to content (no nested scrolling)"* and *"the host caps inline height and clips content that exceeds it"*, with the cap undocumented. The app's `LAYOUT.maxHeight = 500` is a **self-imposed budget**, not a requirement; do not audit against it. The requirement is behavioural — fit content, no internal vertical scroll, and *"request fullscreen presentation with `ui/request-display-mode`"* if a scroll viewport is genuinely needed (M17) |
| **M8** | Fullscreen: no floating panels; native close button present *(gated by your standing `mindsort-fullscreen-native-close-unverified` note — still unverified)* |
| **M13** | N/A unless carousels are added |
| **M15** | Mobile fullscreen render |
| **M20** | ~~Whether the loading block reads as acceptable in-client~~ — **ANSWERED by measurement, 2026-08-20.** See the M20 row above: correct on slow loads, imperceptible on fast loads because there is no wait to cover. No further in-client check needed |

## Legal / contractual — not a code property (9)
`T1` (rights to provide) · `T2` (lawful, policy-compliant) · `T4` (privacy policy provided **and adhered
to**, incl. third-party policies) · `T5` (indemnity) · `T6` (licence grants) · `T7` (authorise review) ·
`T8` (ongoing compliance) · `T9` (**mechanism for receiving security vulnerability reports** — no
`SECURITY.md`, no published disclosure address found in-repo; may exist off-repo) · `T10` (no
partnership/endorsement claims; Trademark Guidelines **never read** per §13)

`P1A` is also IDK: it binds four documents §13 records as never read.

`PUB2` (ongoing review) — IDK, process not code.

---

# N/A — conditional precondition does not hold (14)

| ID | Why |
|---|---|
| A17 | CIMD requires **both** `client_id_metadata_document_supported: true` **and** `"none"` in `token_endpoint_auth_methods_supported`. AS advertises `"none"` but **not** the CIMD flag → Claude falls back to DCR. Precondition fails |
| A20 | Not Microsoft Entra ID |
| A21 | Not using `oauth_anthropic_creds` |
| M11 | ✅-by-N/A: widget loads **no** external origins; `csp` is declared anyway (`resources_dupl.py:116-120`) — belt and braces |
| M13 | No carousels |
| M17 | Remedy for M4; app does not request fullscreen to obtain a scroll viewport |
| R2 | No freeform-endpoint custom query tool |
| S10 | Not a plugin |
| S11 | Not MCPB |
| S15, S16 | **LOCAL connectors only** — MindSort is remote. ⚠️ Note `S16` carries the page's only *"immediate rejection"* warning; it does not bind here, but `P3A`/`T4`/`S5` impose the equivalent privacy-policy obligation that **does** |
| X1, X3 | `ui.domain` **is** set (opt-in), and this is not a local stdio connector |
| L1, L8 | No `ui/open-link` usage found; custom connectors always show the modal regardless |
| A16, A18 | `SPEC`-level; no tokens in connector URL (satisfied by absence), consent-screen rendering is AS-side UI not verified here |

**X2 — `CONDITIONAL` ⚠️SILENT — precondition HOLDS, and it is ✅ Fulfilled:**
`ui.domain = sha256(MCP_RESOURCE_URL)[:32] + ".claudemcpcontent.com"` (`resources_dupl.py:94-95`).
`MCP_RESOURCE_URL` is confirmed in production as `https://mindsort-mcp.priority-guard.com/mcp` (it is the
`resource` value the live PRM serves), and **the hashed URL includes the path** as the row requires →
`c3980c6de9767905dbe6d85359dfbd96.claudemcpcontent.com`. The row's documented *unknown* about trailing
slashes remains unknown and untestable from here.

---

# Blast radius of the findings

| Finding | Scope | Fixing it touches |
|---|---|---|
| R7a — diagnostic tool exposed | **mindsort-only** | `tools_list_dupl.py` (Claude list builder). The tool lives in shared `clarity/tools/`, but the leak is the MindSort list builder's missing filter — PG has its own |
| M3 — inline safe-area | **mindsort-only** | `widget-react/src/App.tsx` inline render path |
| M20 — loading skeleton | **mindsort-only** | `App.tsx` loading branch |
| P5B — description size | **shared** | `clarity/tools/*.py` `DESCRIPTION` blocks — **also changes the OpenAI MindSort surface** |
| P3G — SDK 1.12.4 | **suite-wide** | `poetry.lock` — affects PG-Claude, PG-OpenAI, MindSort both variants |
| P3A/T4 — privacy policy | **suite-wide** | External (Framer); blocks every listing, not just MindSort |

---

# What I did NOT verify

- **Anything in the submission portal or the published listing** — 25 rows.
- **Anything requiring the widget rendered in Claude** — 7 rows, including both remaining `⚠️SILENT`
  behavioural rows (`M3` impact, `M4` clipping).
- **Contrast ratios** (`M2`) — now **computed** for MindSort against Anthropic's *published* token values (see the M2 finding). **Not** sampled from rendered pixels: the host may supply values differing from the published table, so a devtools eyedropper would be a stronger check. Still never measured for **PG**.
- **AS reachability from `160.79.104.0/21`** (`A7`) — inferred from the MCP host, not tested for the AS.
- **The 11 obligations §13 records as never read**, including the Trademark Guidelines that `T10` binds.
- **Screen-reader output** of the new inherited-priority announcement — presence verified, speech not.
- I did not run the tool suite against production (auth), so `R11`/`S12` remain your attestation to make —
  and **R7a currently makes that attestation false**.
