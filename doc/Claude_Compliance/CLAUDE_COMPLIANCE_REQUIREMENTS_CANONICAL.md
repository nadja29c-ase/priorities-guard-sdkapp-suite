# Claude MCP App — Canonical Compliance Requirements

**What this is.** Every requirement an MCP App for Claude must satisfy to pass directory review, and
nothing else. **If you are shipping or submitting, this is the only compliance document you need to
read.** The master (`claude_connectors_compliance_master.md`) remains the source synthesis and audit
record — changelog, provenance, standing checks, sweep results, implementation mechanism. It is not
a substitute for this file, and this file is not a substitute for it.

**Folder layout after the 2026-08-05 consolidation** — three layers, no middle:
`sources_raw/` holds the bytes · **this file** holds the requirements · the master holds synthesis
and the audit record. The per-page extraction artifacts were removed; every requirement they
carried is a row here. See the master's changelog for the removal manifest and the recovery commit.

**Not here by design:** mechanism. No CSS token tables, no `BroadcastChannel` election protocol, no
SDK helper lists, no code. This file states **what must be true**. To learn *how*, follow the source.

**Current against 11 captured sources** (`sources_raw/`): `software-directory-policy` ·
`software-directory-terms` · `authentication` · `design-guidelines` · `transparent-theming` ·
`cross-compatibility` · `instance-supersession` · `submission` · `review-criteria` · `testing` ·
`lazy-authentication`.

**Coverage, counted with its predicate** (standing check #7 — a number needs its pattern *and* its
predicate; an earlier version of this line said "silent on 9", which reconciled to nothing):

- **Silent on 8** — *predicate: nothing has been read at all.* Five binding documents (Trademark
  Guidelines + four via Policy §1A) and three referenced requirement surfaces (Enterprise Managed
  Auth, `directory-vs-custom`, `managing-your-listing`).
- **Weakly sourced on 3** — *predicate: content is known but no artifact exists in the tree.*
  `external-links`, `troubleshooting`, `after-publishing` — all marked `[relay-only]` in the rows
  that depend on them.

**Eleven items in total.** See §13. **Four of the eight are binding via Policy §1A alone.**

### Round 2 — citation integrity, run 2026-08-05

**Round 1 catches omission. Round 2 catches invention**, by checking the reverse direction: does
every claim here trace to the line it cites? Mechanically verified across all rows:

| | |
|---|---|
| Rows | **121** |
| Citing a **resolvable** raw line (file exists, line within it) | **113** |
| `[relay-only]` — no artifact to cite | **8** — L5–L8, S6, PUB1, PUB3, PUB4 |
| **Unresolvable citations** | **0** |

**Three defects found and fixed by this pass:**

1. **14 rows cited a file with no line number** — M5–M9, M12, S3–S5, S7–S9, S12, S14. Briefing §9
   required a line. All 14 now carry one, and several gained detail the source had that the row
   had dropped (M7's z-index rationale, M9's no-horizontal-scrolling clause, S9's three API
   categories, S12's *"every link, credential and step"*).
2. **L1–L4 were marked `[relay-only]` when a CAPTURED source carries them** —
   `submission.raw.md:73-86`. **Under-attribution is as much a defect as over-attribution**: it
   makes a real obligation look weakly evidenced and hides that the tree already holds the proof.
   §10 is now half captured, half relay-only, instead of wholly relay-only.
3. **S7 cited "(raw 17)" with no file named** — unresolvable without guessing. Now explicit.

⚠️ **What round 2 did NOT do.** This verified that every citation **resolves**. It did **not**
verify that each cited line **says what the row claims** — that is semantic, row by row, and has
been done only for the high-stakes rows (A18, A19, P5E, M10, X1, S1, S12). **The remaining ~105
rows are citation-verified, not content-verified.**

**Date: 2026-08-05. This file states current state only.** Superseded entries go to the master's
changelog, **never inline here**.

### Provenance markers, inherited from `sources_raw/PROVENANCE.md`

| Marker | Meaning |
|---|---|
| *(unmarked)* | Paste or paste-corroborated — bytes checked against Nadja's copy |
| `[fetch-only]` | `review-criteria`, `testing`, `lazy-authentication` — **undated and uncorroborated** |
| `[relay-only]` | `external-links`, `troubleshooting`, **`after-publishing`** — **no artifact in the tree**; source cited by page and section, since there is no file to give a line in |

⚠️ `cross-compatibility` and `instance-supersession` sit between the first two: both were pasted to
the review chat but **never byte-compared** against the fetch. Left unmarked per the increment
briefing; noted here so the header does not overstate.

### Level taxonomy — the point of this document

| Level | Meaning |
|---|---|
| `POLICY` | Software Directory Policy MUST — binding, review-enforced |
| `TERMS` | Directory Terms warranty or obligation — contractual |
| `PORTAL` | Enforced by the submission portal, or a required form field |
| `DOC-CONSTRAINT` | Constraint stated on a docs page; binding via Policy §3H |
| `SPEC` | Inherited from the MCP specification via an Anthropic page — **not a directory gate** |
| `REVIEW-ONLY` | Appears only in `review-criteria` — reviewer-facing, not in the binding documents |
| `RECOMMENDED` | Explicitly soft in the source. Listed so nobody re-promotes it. |
| `CONDITIONAL` | Binding only under a stated precondition — the precondition is in the requirement text |

**Never round upward.** A row whose level cannot be determined from the source is `RECOMMENDED`.

**PG status** — `✅ verified` (with citation) · `⚠️ <finding>` (measured discrepancy) ·
`— not assessed` (the default, and the correct answer where nothing was established). **Recorded
status, not a work list.**

---

## 1. Safety & Security

| ID | Requirement | Level | Source | PG status |
|---|---|---|---|---|
| P1A | Must not violate or facilitate violation of the Usage Policy; must comply with Universal Usage Standards, High-Risk Use Case requirements and the supported-countries policy | `POLICY` | policy §1A (raw 7) | — not assessed — **the four referenced documents are uncaptured (§13)** |
| P1B | Must not evade, or let users circumvent, Claude's safety guardrails, system instructions or sandbox | `POLICY` | policy §1B (raw 9) | — not assessed |
| P1C | Must prioritise user **and third-party** privacy; handle personal and sensitive data responsibly; comply with applicable law | `POLICY` | policy §1C (raw 11) | **— not assessed.** *Context, not a finding:* PG ingests calendar events carrying other people's names and meeting titles, so this clause applies. **This audit did not assess PG against it.** A pre-existing tracked item (backlog #11, "three versions of the retention model exist") predates this audit and is not one of its findings — cited as a pointer, not as evidence |
| P1D | Must collect only data from the user's context necessary to function. **Must not collect extraneous conversation data, even for logging purposes** | `POLICY` | policy §1D (raw 13) | ⚠️ `record_widget_diagnostic` accepts an open `data` object (`additionalProperties: true`). No violation evidenced — its only caller is the ChatGPT widget sending event names and user-agent — but the schema is not the guarantee; call sites are. **Not called from the Claude path** |
| P1E | Must not infringe intellectual property rights | `POLICY` | policy §1E (raw 15) | — not assessed |
| P1F | **Must not query or extract Claude's memory, chat history, conversation summaries, or user-generated/uploaded files** | `POLICY` | policy §1F (raw 17) · review-criteria (raw 55) `[fetch-only]` | ✅ verified — **pattern and scope stated:** `grep -rniE "conversation_(history\|summary)\|chat_history\|claude_memory\|user_files\|conversation_summar"` over `mcp_server/**/*.py` and `backend/**/*.py`, excluding tests → **0 matches**. ⚠️ *Bounded by the pattern: this proves no identifier-level match, not that no such access exists under a name the pattern misses* |

---

## 2. Tool & capability descriptions

Policy §2 governs "Instructional Software", which **includes MCP servers** (raw 21).

| ID | Requirement | Level | Source | PG status |
|---|---|---|---|---|
| P2A | Each tool defined through **narrow, unambiguous** natural language stating what it does **and when it should be invoked** | `POLICY` | policy §2A (raw 23) | — not assessed |
| P2B | Descriptions must **precisely match actual functionality**; no unexpected functionality, **no promising undelivered features** | `POLICY` | policy §2B (raw 25) · review-criteria R5 (raw 35) `[fetch-only]` | ⚠️ `inspect_adapt`'s description says it **records** confirmed action steps; the handler persists nothing (332 lines, zero backend calls, docstring *"validate provenance → return success"*). **Recorded finding. Descriptions are shared with the live ChatGPT app and are not touched.** |
| P2C | Descriptions must not create confusion or conflict **with other Software in the Directories** | `POLICY` | policy §2C (raw 27) | — not assessed — **cross-connector**: PG and MindSort ship from one developer with adjacent purposes |
| P2D | Must not call or coerce Claude into calling other external software unless the user requested it; descriptions must not be written so as to make other Software be called extraneously | `POLICY` | policy §2D (raw 29) · review-criteria R6 (raw 41) `[fetch-only]` | — not assessed |
| P2E | Must not attempt to **interfere with Claude calling tools from other software** | `POLICY` | policy §2E (raw 31) · review-criteria R6 (raw 42) `[fetch-only]` | — not assessed |
| P2F | Must not direct Claude to pull behavioural instructions dynamically from external sources | `POLICY` | policy §2F (raw 33) · review-criteria R6 (raw 43) `[fetch-only]` | — not assessed |
| P2G | No hidden, obfuscated or encoded instructions; **all behavioural guidance human-readable and clearly presented** | `POLICY` | policy §2G (raw 35) · review-criteria R6 (raw 44) `[fetch-only]` | — not assessed |
| R6a | Descriptions are **rejected** if they tell Claude to behave in ways unrelated to the tool's function, **attempt to override system instructions**, or promote products. *"Describe what the tool does. Do not tell Claude how to behave."* | `REVIEW-ONLY` | review-criteria (raw 45, 47) `[fetch-only]` | ⚠️ Three of eight public descriptions carry override language (`BINDING RULES`, `SUSPENDED`, `default behavior`): `create_priority`, `inspect_adapt`, `onboarding_calendar_setup`. Five are clean. **Recorded. Not changed.** |

---

## 3. Developer requirements

| ID | Requirement | Level | Source | PG status |
|---|---|---|---|---|
| P3A | Provide a **clear, accessible privacy policy link** explaining collection, usage **and retention**; provide links to all applicable policies to Anthropic; present them to users as required by law | `POLICY` | policy §3A (raw 39) | ⚠️ Published, but still routes PG full deletion to `support@priority-guard.com`, which is wrong now the deletion tool ships. Separately: v3.2 characterises Anthropic as an **Art. 28 processor**, which is incorrect — see T3/T4 |
| P3B | Provide **verified** contact information **and** support channels for users with **product or security** concerns | `POLICY` | policy §3B (raw 41) | — not assessed |
| P3C | Document **how the Software works, its intended purpose, and how users troubleshoot issues** | `POLICY` | policy §3C (raw 43) | ⚠️ No Claude-specific documentation page exists |
| P3D | Provide a **standard testing account with sample data** for Anthropic to verify full functionality | `POLICY` | policy §3D (raw 45) · submission B (raw 70) · testing (raw 39) `[fetch-only]` | — not assessed |
| P3D-i | Test credentials must be a **fully populated account, not an empty shell** — reviewers list real records, search real data and exercise write tools on real resources — **and must include step-by-step setup instructions for someone unfamiliar with the service** | `PORTAL` | testing (raw 39) `[fetch-only]` | — not assessed |
| P3E | Provide **at least three working examples** of prompts or use cases demonstrating core functionality | `POLICY` | policy §3E (raw 47) | — not assessed |
| P3F | Must **verify ownership or control** of any API endpoint, domain or UI the Software connects to, **and any external resources it retrieves or renders** | `POLICY` | policy §3F (raw 49) · review-criteria R8 (raw 59) `[fetch-only]` | ✅ verified — first-party backend; `mcp.priority-guard.com` matches the service |
| P3G | Maintain the Software and address issues within reasonable timeframes | `POLICY` | policy §3G (raw 51) | — not assessed |
| P3H | Agree to the Software Directory Terms **and follow the design guidelines Anthropic publishes** | `POLICY` | policy §3H (raw 53) | — not assessed. **This clause is what makes §8/§9 `DOC-CONSTRAINT` rows binding** |
| DOC1 | Public documentation is required **by your publish date** — **a blog post or help-centre article is sufficient**; may be shared privately with Anthropic during review | `REVIEW-ONLY` | review-criteria (raw 72) `[fetch-only]` | ⚠️ Not created. **There is no seven-section requirement in any binding document** |

---

## 4. Unsupported use cases

| ID | Requirement | Level | Source | PG status |
|---|---|---|---|---|
| P4A | Must not transfer money, cryptocurrency or other financial assets, or execute financial transactions on a user's behalf | `POLICY` | policy §4A (raw 59) · review-criteria (raw 65) `[fetch-only]` | ✅ verified — PG does none of this |
| P4B | Must not use AI models to generate images, video or audio. **Design-focused visual aids are permitted** (slides, diagrams, charts, UI mockups, logos) provided standalone generation is not offered as a primary service | `POLICY` | policy §4B (raw 61) · review-criteria (raw 66) `[fetch-only]` | ✅ verified — PG generates no media |
| P4C | Must not serve **advertisements, sponsored content or paid product placements**, or exist primarily as an advertising or promotional vehicle | `POLICY` | policy §4C (raw 63) | ✅ verified — PG carries none. **Absent from `review-criteria`; binding only via the policy** |

---

## 5. MCP server requirements

| ID | Requirement | Level | Source | PG status |
|---|---|---|---|---|
| P5A | Must **gracefully handle errors** and provide helpful feedback rather than generic error messages | `POLICY` | policy §5A (raw 67) · review-criteria R7 (raw 51) `[fetch-only]` | — not assessed |
| P5B | Must be **frugal with tokens** — usage roughly commensurate with task complexity or impact; **where possible give users options to exclude unnecessary text** | `POLICY` | policy §5B (raw 69) | — not assessed. **A hard MUST appearing on no other page**; PG returns full dashboards from `get_priorities` and `render_weekly_report` |
| P5C | Tool names must not exceed **64 characters** | `POLICY` | policy §5C (raw 71) · review-criteria R4 (raw 31) `[fetch-only]` | ✅ verified — 8/8 public tools; longest served is `delete_my_priority_guardian_data` at **32** |
| P5D | Remote servers that connect to a remote service and require authentication must use **secure OAuth 2.0 with certificates from recognized authorities** | `POLICY` | policy §5D (raw 73) | ✅ verified — OAuth 2.0 + PKCE S256, TLS on both hosts |
| P5E | Must provide **all applicable annotations**, in particular **`readOnlyHint`, `destructiveHint` and `title`** | `POLICY` | policy §5E (raw 75) · review-criteria R3 (raw 27) `[fetch-only]` | ✅ verified on the **Claude serving surface** — all 8 public tools carry a title and at least one hint. `title` is structurally guaranteed (required positional field on `ToolDefinition`). ⚠️ `create_priority` is `destructive_hint=False` in the **shared registry** and overridden to `True` for Claude in `tools_list_dupl.py` — **audit the serving path, not the registry** |
| P5F | **Should** support **Streamable HTTP**. SSE is tolerated *"for the time being"* and **will be deprecated** | `RECOMMENDED` | policy §5F (raw 77) | — not assessed — PG's transport not checked |
| P5G | Local servers must use reasonably current dependency versions, including `node_modules` | `POLICY` | policy §5G (raw 79) | n/a — PG is remote |
| R1 | **Read and write tools must be separate.** A single tool accepting both safe (GET/HEAD/OPTIONS) and unsafe (POST/PUT/PATCH/DELETE) methods is **rejected**. Documenting the split inside one description **does not satisfy this** | `REVIEW-ONLY` | review-criteria (raw 15-17) `[fetch-only]` | ✅ verified — purpose-built tools, no catch-all with a `method` parameter; writes already split by action type |
| R2 | **CONDITIONAL — applies only to custom query tools.** If a tool accepts freeform endpoint paths, query strings or request bodies constructed by the caller, its description must link to or explicitly name the target API | `CONDITIONAL` | review-criteria (raw 19-23) `[fetch-only]` | n/a — no PG tool accepts caller-constructed paths or bodies |
| R7a | Every tool must return a **successful response** when called with valid parameters; generic errors fail review. Validate inputs and return **actionable** errors. Keep responses reasonably sized | `REVIEW-ONLY` | review-criteria (raw 51-53) `[fetch-only]` | — not assessed |
| R11 | **Before submitting, exercise every tool** through the MCP Inspector **and** as a custom connector in Claude | `REVIEW-ONLY` | review-criteria (raw 78) `[fetch-only]` · testing `[fetch-only]` | ⚠️ Only `delete_my_priority_guardian_data` has been exercised end to end. See S12 — this is attested to in the portal |

---

## 6. Directory Terms warranties

Policy §3H makes agreeing to these mandatory. **The Policy says what the Software must do; the
Terms are what you warrant when you submit.** Published 16 March 2026.

| ID | Requirement | Level | Source | PG status |
|---|---|---|---|---|
| T1 | You have and will maintain all rights necessary to provide the Software and grant the rights in the Terms | `TERMS` | terms (raw 3-i) | — not assessed |
| T2 | The Software and its ordinary intended use comply with all applicable law and do not violate the Policy **as updated from time to time** | `TERMS` | terms (raw 3-ii) | — not assessed |
| T3 | **"Any information you give us will be accurate and up-to-date."** A warranty over **every field of the submission portal** | `TERMS` | terms (raw 3-iii) | ⚠️ The privacy policy's **Art. 28 characterisation of Anthropic is incorrect** — inaccurate information given to Anthropic |
| T4 | Provide **and adhere to** a privacy policy; **provide all applicable third-party privacy policies**; all such policies must **clearly and accurately describe** what you **and third parties** collect, use and share | `TERMS` | terms (raw 3-iv) | ⚠️ PG connects to Google Calendar, so **Google's policy must be provided**, not merely disclosed around. Not verified. Compounded by the Art. 28 error |
| T5 | Indemnify and hold Anthropic harmless from claims arising from the Software or users' interactions with it | `TERMS` | terms (raw 5-i) | — recorded as accepted |
| T6 | Grant Anthropic non-exclusive, royalty-free, worldwide licences to reproduce, display and distribute Software descriptions and documentation, and to display your name, trademarks, logos and branding in the Directories | `TERMS` | terms (raw 5-ii) | — recorded as accepted |
| T7 | Authorise Anthropic to review and test the Software, and to **collect, use and share functional metadata** about it | `TERMS` | terms (raw 5-iii) | — recorded as accepted |
| T8 | **Continue implementing and maintaining quality and security standards consistent with the Policy, as updated.** Failure may result in removal | `TERMS` | terms (raw 9) | — not assessed. **This is why compliance is a repeatable process, not a one-time gate** |
| T9 | **Implement and maintain a mechanism for receiving security vulnerability reports from Anthropic and from third parties, and investigate them with a reasonable standard of care** | `TERMS` | terms (raw 9) | ⚠️ **Appears unimplemented.** Distinct from P3B, which is a *user support* channel — T9 names Anthropic and third parties and adds a **duty of care** |
| T10 | Make **no statement suggesting partnership, sponsorship or endorsement** by Anthropic without prior written approval; **comply at all times with Anthropic's Trademark Guidelines** | `TERMS` | terms (raw 11) | — not assessed. ⚠️ **Trademark Guidelines are uncaptured (§13)** — an obligation whose content is unknown |

**Also binding, recorded:** Anthropic has **no obligation** to include the Software and may remove it
at any time for any reason without liability (raw 7). Terms may be **modified without prior notice**;
continued maintenance constitutes acceptance (raw 11).

---

## 7. Authentication & OAuth

| ID | Requirement | Level | Source | PG status |
|---|---|---|---|---|
| A1 | AS must **support S256 PKCE** — Claude sends `code_challenge_method=S256` on **every** authorization request, regardless of registration mechanism | `DOC-CONSTRAINT` | authentication (raw 55) | ✅ verified |
| A2 | AS metadata must advertise `"code_challenge_methods_supported": ["S256"]` | `SPEC` | authentication (raw 55) | ✅ verified — live AS metadata |
| A3 | Return **401** with a `WWW-Authenticate` header whose `resource_metadata` points at the PRM document. **The 401 status is required — Claude does not honor `WWW-Authenticate` on a 200** | `DOC-CONSTRAINT` | authentication (raw 63, 70) | ✅ verified live — `HTTP/2 401`, `resource_metadata=…`, `scope="pg.access"` |
| A4 | PRM `resource` must match the MCP server URL **exactly as the user enters it in Claude**, including any path component | `DOC-CONSTRAINT` | authentication (raw 76) | ✅ verified — `https://mcp.priority-guard.com/mcp` |
| A5 | PRM `authorization_servers` must list the AS issuer URL. **Claude uses the first entry and does not fall back** | `DOC-CONSTRAINT` | authentication (raw 77) | ✅ verified — single entry |
| A6 | AS must serve its own discovery metadata (RFC 8414 or OIDC Discovery) at its `/.well-known/` paths | `DOC-CONSTRAINT` | authentication (raw 78) | ✅ verified |
| A7 | That AS host must be **reachable from Anthropic's egress range** `160.79.104.0/21` — a WAF in front of the IdP breaks the flow even when the MCP server is reachable | `DOC-CONSTRAINT` | authentication (raw 78, 141) | — not assessed — cannot originate traffic from Anthropic's range |
| A8 | Register the redirect URI `https://claude.ai/api/mcp/auth_callback` for hosted surfaces | `DOC-CONSTRAINT` | authentication (raw 92-96) | ✅ verified — both `.ai` and `.com` variants registered |
| A9 | For Claude Code, accept **both** `http://localhost/callback` **and** `http://127.0.0.1/callback` **with the port component ignored** | `DOC-CONSTRAINT` | authentication (raw 104) | ✅ verified against Claude Code's **published CIMD** — both accepted, port-agnostic, negative controls rejected |
| A10 | Return RFC 6749-compliant error codes — **`invalid_grant`**, not `invalid_request` or a custom code — when a refresh token is no longer valid | `DOC-CONSTRAINT` | authentication (raw 112) | ✅ verified live — token endpoint returned `invalid_grant` |
| A11 | **Rotate refresh tokens for public clients.** If rotating, return the new refresh token in the same response that invalidates the old | `SPEC` | authentication (raw 113) | ✅ verified |
| A12 | `/token` must accept `Content-Type: application/x-www-form-urlencoded` (RFC 6749 §4.1.3) | `DOC-CONSTRAINT` | authentication (raw 115) | ✅ verified live — form body parsed, 400 `invalid_grant`, **not 415** |
| A13 | `/register` uses `application/json` (RFC 7591 §3.1) — **do not assume one parser serves both** | `DOC-CONSTRAINT` | authentication (raw 115) | ✅ verified indirectly — JSON to `/token` returns 422, confirming the split |
| A14 | Respond within **10 s** for discovery, registration and token endpoints and **30 s** for refresh; **return headers and body without buffering behind upstream work**, and ensure no proxy, gateway or WAF holds the response | `DOC-CONSTRAINT` | authentication (raw 135, 137) | — not assessed — not measured under load |
| A15 | Machine-to-machine `client_credentials` is **not supported**; every connection requires user consent | `DOC-CONSTRAINT` | authentication (raw 30) | ✅ verified — not implemented |
| A16 | **Do not put tokens or API keys in the connector URL.** The MCP spec **prohibits** access tokens in the URI query string | `SPEC` | authentication (raw 26) | ✅ verified — bearer header only |
| A17 | **CONDITIONAL — CIMD selection.** Claude selects CIMD **only when** AS metadata advertises **both** `"client_id_metadata_document_supported": true` **and** `"none"` in `token_endpoint_auth_methods_supported`. If either is missing it falls back to DCR | `CONDITIONAL` | authentication (raw 50) | n/a — describes Claude's selection logic, not a duty. PG advertises `"none"` only → DCR |
| A18 | AS must **display the redirect URI hostname clearly on the consent screen** (unconditional), and **should** add an extra warning when the only registered redirect URIs are loopback addresses | `SPEC` | authentication (raw 106) | ⚠️ **Not satisfied.** None of the eight `oauth_consent_*.html` templates render it. **NOT A DIRECTORY GATE** — absent from `review-criteria` and from the binding policy. Open security item, post-submission |
| A19 | **`clientInfo` is unauthenticated and must never feed an authorization decision.** Any client can claim any name; do not gate behaviour on an exact `name` or `version` — both vary across surfaces and releases | `DOC-CONSTRAINT` | testing (raw 35) `[fetch-only]` | **— not assessed.** Whether anything on the Claude path reads `clientInfo` has not been checked. ⚠️ **Same class as open task #10** — `_meta["openai/subject"]` is client-controlled and unbound to the JWT on the OpenAI deletion path |
| A20 | **CONDITIONAL — Microsoft Entra ID only.** Register the MCP server URL as an **Application ID URI** on the Entra app registration, or the token request fails `AADSTS9010010` | `CONDITIONAL` | authentication (raw 81) | n/a — PG runs its own AS |
| A21 | **CONDITIONAL — `oauth_anthropic_creds` only.** Credentials are bound to the issuing AS; email `mcp-review@anthropic.com` with new credentials **before** migrating to a new authorization server | `CONDITIONAL` | authentication (raw 41) | n/a — PG uses `oauth_dcr` |
| A22 | Return **401**, not a tool error. A **200 with `isError: true` is an application-level failure** — Claude passes the text to the model and moves on, with **no auth prompt**. A **403** triggers re-authentication **only** with `error="insufficient_scope"`; any other 403 is terminal | `DOC-CONSTRAINT` | lazy-authentication (raw 43, 123) `[fetch-only]` | ✅ verified — PG returns a transport-level 401 |
| A23 | Include a `scope` parameter in the 401's `WWW-Authenticate`. Omitting it makes Claude request everything in PRM `scopes_supported` plus `offline_access`, **which can produce an over-broad consent prompt** | `RECOMMENDED` | authentication (raw 57) · lazy-authentication (raw 32) `[fetch-only]` | ✅ verified — PG sends `scope="pg.access"` |
| A24 | **RECOMMENDED — DCR at scale.** For servers expecting high traffic from the directory, **prefer CIMD or `oauth_anthropic_creds` over DCR**; DCR registers a new client on every fresh connection | `RECOMMENDED` | authentication (raw 53) | — recorded. PG is directory-bound and uses DCR; supported out of the box |

---

## 8. MCP Apps — display modes & design

Binding via **Policy §3H** (*"follow design guidelines Anthropic publishes"*).

| ID | Requirement | Level | Source | PG status |
|---|---|---|---|---|
| M1 | All views must support **both light and dark themes**; use host style tokens; **never hardcode colors**; test both modes | `DOC-CONSTRAINT` | design-guidelines (raw 204) — **one of only two developer "must" statements on the page** | — not assessed |
| M2 | **WCAG AA** contrast minimum, keyboard navigation, text alternatives, tested with assistive technologies — *"your app must be usable by everyone"* | `DOC-CONSTRAINT` | design-guidelines (raw 278) — the other developer "must" | — not assessed |
| M3 | Render interactive UI **inside `safeAreaInsets`**. **Not mobile-specific** — on web and desktop the composer can overlay the bottom of an inline app | `DOC-CONSTRAINT` | design-guidelines (raw 134) | ⚠️ Applied only under `platform === 'mobile' && hostFullscreen`; horizontal padding hardcoded 16px, so `.left`/`.right` are unused |
| M4 | Inline: **auto-fit content height, no nested vertical scroll.** The host caps and clips. **No pixel value is published** | `DOC-CONSTRAINT` | design-guidelines (raw 39, 62, 186) | — not assessed |
| M5 | Inline: maximum **2 actions**, at the bottom of the card | `DOC-CONSTRAINT` | design-guidelines (raw 63) | — not assessed |
| M6 | Inline: maximum **4–5 data points** | `DOC-CONSTRAINT` | design-guidelines (raw 64) | — not assessed |
| M7 | No drill-ins, breadcrumbs or multiple views; no menus or popovers — use visible controls (they get clipped by container boundaries or conflict with host z-index) | `DOC-CONSTRAINT` | design-guidelines (raw 65-66, 38, 40) | — not assessed |
| M8 | Fullscreen: **avoid** floating panels — use collapsible sidebars, tabs or pagination; the app provides its own fullscreen button; a close button appears in the native header; the composer remains available | `RECOMMENDED` | design-guidelines (raw 99) | — not assessed. ⚠️ Previously labelled "(mandatory)" here with no basis |
| M9 | Touch targets **≥ 44pt** on mobile; content adapts to narrow viewports **without horizontal scrolling** | `DOC-CONSTRAINT` | design-guidelines (raw 68) | — not assessed |
| M10 | **No fixed-width layouts**; responsive from **320px**; **no side margins** that waste screen real estate — apps always fill the container width, with no fixed breakpoints | `DOC-CONSTRAINT` | design-guidelines (raw 284-286) | ⚠️ **Four layered width caps**, outermost smallest: `#root` 600px (binds), inline `<main>` 560px (binds), fullscreen `<main>` 672px (**dead**), pie section 672px (**dead**). Compliant inline; **in fullscreen the cap binds and auto margins produce the artifact M10 names** |
| M11 | Declare `_meta.ui.csp` — **CONDITIONAL:** required only if the widget loads external origins. All external origins are blocked by default | `CONDITIONAL` | design-guidelines (raw 150-159) | ✅ verified — declared on all three `_meta.ui` blocks |
| M12 | Declare `appCapabilities.availableDisplayModes` in `ui/initialize` | `DOC-CONSTRAINT` | design-guidelines §Display modes (raw 43, 144) | ✅ verified — `['inline','fullscreen']` |
| M13 | **CONDITIONAL — carousels.** Maintain consistent card dimensions; on mobile design for thumb reach with primary actions in the lower portion, and **peek the next card** to signal scrollability | `CONDITIONAL` | design-guidelines (raw 72-95) | n/a — PG ships no carousel |
| M14 | **`prefersBorder` — set true or false explicitly.** If unspecified: **borderless on web, bordered on mobile.** Borderless runs edge-to-edge with **no host padding**, so honouring `safeAreaInsets` becomes essential | `RECOMMENDED` | design-guidelines (raw 138) · transparent-theming (raw 21) | ⚠️ Set `false` on all three blocks → borderless on mobile too, while `safeAreaInsets.left`/`.right` go unapplied. **One decision with two consequences** |
| M15 | Mobile fullscreen **is supported.** Mobile renders in a native WebView, not a sandboxed iframe: no camera/mic/location, and connectors must be added via web or desktop before appearing on mobile | `DOC-CONSTRAINT` | design-guidelines (raw 120, 128) | — not assessed |

---

## 9. MCP Apps — widget domain, CSP, theming

| ID | Requirement | Level | Source | PG status |
|---|---|---|---|---|
| X1 | **CONDITIONAL — `_meta.ui.domain` is OPTIONAL.** Its format and validation are **host-determined**. **Without it, Claude derives the iframe origin per conversation and connector.** Setting it opts into a **stable sandbox origin — needed if the app runs its own OAuth flow** | `CONDITIONAL` | cross-compatibility (raw 27) · instance-supersession (raw 179) | ✅ Set deliberately — PG's widget runs its own OAuth flow (`openLink` to a Google connect URL). **Accepted cost:** origin shared across conversations |
| X2 | **CONDITIONAL — if `ui.domain` is set for Claude:** `sha256(<full connector URL>)[:32] + ".claudemcpcontent.com"`. **Hash the exact string entered in Settings > Connectors, including path and any trailing slash** | `CONDITIONAL` | cross-compatibility (raw 29-33) | ✅ verified — computed at import from `MCP_RESOURCE_URL`; `https://mcp.priority-guard.com/mcp` → `a7b31ccb…` |
| X3 | **Local stdio connectors have no URL** — omit `_meta.ui.domain` rather than inventing a value | `CONDITIONAL` | cross-compatibility (raw 27) | n/a — PG is remote |
| X4 | `html, body { margin: 0; background: transparent; }` — any opaque background on either hides the chat surface | `DOC-CONSTRAINT` | transparent-theming (raw 16) | ✅ verified — `main.css:8-15` |
| X5 | `<meta name="color-scheme" content="light dark" />` in the document head, **kept** even though `applyDocumentTheme` sets it at runtime — the tag covers first paint | `DOC-CONSTRAINT` | transparent-theming (raw 17) | ✅ verified — in the Vite build input **and** the served artifact |
| X6 | **CONDITIONAL — host fonts only.** CSP `resourceDomains` must include `https://assets.claude.ai` for `applyHostFonts` to load the `@font-face` files | `CONDITIONAL` | transparent-theming (raw 18) | ⚠️ Granted on all three blocks but **hollow** — no `--font-*` variable is referenced anywhere in the widget, so the CSP is widened for a capability not exercised |
| X7 | **Register the `hostcontextchanged` listener before you connect**, so an early update is not missed | `DOC-CONSTRAINT` | transparent-theming (raw 19) | — not assessed — SDK internals not read |
| X8 | `resourceDomains` **also adds the listed origins to `script-src` and `style-src`** — keep it to origins trusted to serve executable code; prefer bundling third-party fonts over allowlisting public CDNs | `DOC-CONSTRAINT` | transparent-theming (raw 52-54) | — recorded, see X6 |

---

## 10. External links

⚠️ **Provenance corrected by round 2, 2026-08-05.** This section previously marked **all eight**
rows `[relay-only]`. **Four of them (L1–L4) are carried by a CAPTURED source** —
`submission.raw.md:73-86` states the ownership rule, the HTTPS-origin matching, subdomains-not-
implied, custom schemes, and that the field is optional. They are now cited there and the markers
are off. **L5–L8 remain `[relay-only]`** — those four come from `external-links`, which has no
artifact in the tree.

**This is the reverse-direction check working:** round 1 attributed four requirements to the
weakest provenance category in the document when a stronger source already carried them.
**Under-attribution is as much a defect as over-attribution** — it makes a real obligation look
optional, and it hides that the tree already contains the evidence.

| ID | Requirement | Level | Source | PG status |
|---|---|---|---|---|
| L1 | **CONDITIONAL — the field is optional.** It applies only if the connector uses `ui/open-link`. If omitted the connector functions normally, but **users are shown a confirmation prompt each time it opens a link** | `CONDITIONAL` | **submission §Allowed link URIs (raw 75, 85-86)** | ✅ PG calls `openLink` |
| L2 | **Every origin and scheme listed must be owned by you (the submitting organization).** You may not list third-party domains or schemes registered to apps you don't publish. **Entries you don't own will be removed during review** | `PORTAL` | **submission (raw 82)** | ✅ verified — the target is `BACKEND_PUBLIC_URL` (`https://www.priority-guard.com`), a domain PG owns; **not** `accounts.google.com` |
| L3 | An HTTPS origin entry matches **scheme and hostname only** — paths, ports and query strings are ignored. **Subdomains are not implied — list each one** (`https://app.example.com`, `https://docs.example.com`) | `PORTAL` | **submission (raw 79)** | — not assessed — confirm the live `BACKEND_PUBLIC_URL` before filling the portal |
| L4 | A **custom URI scheme** entry (`myapp:`) is for deep links into a native app **you own**; only the scheme is matched | `PORTAL` | **submission (raw 80)** | n/a |
| L5 | **Malformed entries are IGNORED** — not rejected. Both this and L2 fail **silently**: the listing ships, the entry is gone, and users get the confirmation modal on every link | `PORTAL` | external-links `[relay-only]` | — recorded |
| L6 | The reserved-scheme list is **open-ended** (*"This includes…"*), not closed | `PORTAL` | external-links `[relay-only]` | — recorded |
| L7 | A bypassed `ui/open-link` **resolves once the open is attempted** — that is **not** confirmation the user reached the destination | `DOC-CONSTRAINT` | external-links `[relay-only]` | — not assessed |
| L8 | **Custom and local connectors always show the confirmation modal**, regardless of the allowlist | `DOC-CONSTRAINT` | external-links `[relay-only]` | — recorded. **PG is a custom connector until published** |

---

## 11. Submission portal

| ID | Requirement | Level | Source | PG status |
|---|---|---|---|---|
| S1 | **A Team or Enterprise organization is required.** Admin settings — and therefore the portal — are unavailable on individual plans | `PORTAL` | submission (raw 21-23) | ⚠️ **BLOCKS SUBMISSION.** Not an engineering task |
| S2 | The submitter must be an **Owner or Primary Owner**. Enterprise may delegate via a custom role with **Directory management** or **Libraries**; **Team plans have no custom roles** | `PORTAL` | submission (raw 24) | — not assessed |
| S3 | Server URL must be **`https://`** | `PORTAL` | submission §Connection (raw 152) | ✅ verified |
| S4 | Every tool must carry a **`title`** and the applicable **`readOnlyHint`/`destructiveHint`**; the portal flags violations to fix **on the server before submitting** | `PORTAL` | submission (raw 46) | ✅ verified — 8/8 public tools; nothing lands in the un-annotated group |
| S5 | Listing limits: **name ≤ 100**, **tagline ≤ 55**, **description ≤ 2,000** characters; **1–5 categories**; plus documentation URL, privacy policy URL, support contact and icon | `PORTAL` | submission (raw 144) | — not assessed |
| S6 | **The URL slug is PERMANENT once published** — `https://claude.ai/directory/connectors/SLUG`. Display names can change; the slug cannot | `PORTAL` | submission · after-publishing `[relay-only]` | — not assessed. **The only irreversible choice in the portal** |
| S7 | **MCP Apps: screenshots required.** 3–5 **PNG**, **≥ 1000px** wide, cropped to the app response area, **the prompt must not appear in the image** (supply prompt text separately). **Aspect ratio unconstrained. Video and GIF rejected. One batch covers all surfaces.** Figma carousel template available | `PORTAL` | submission (raw 88-101) · submission (raw 17) | — not assessed |
| S8 | **Seven compliance acknowledgments, all required** — directory guidelines, first-party API usage, financial transactions, AI media generation, prompt injection, conversation data collection, public documentation. Under **T3** each is a **warranty**, not a checkbox — see the mapping below | `PORTAL` | submission (raw 168) | — not assessed |
| S9 | Data-handling declarations: whether the underlying API is **your own, proxied from a partner with permission, or a third party's you don't control**; whether the connector handles **personal health data** or **sponsored content** | `PORTAL` | submission (raw 160) | — not assessed |
| S10 | **CONDITIONAL — plugins only.** Plugins must link a **public GitHub repo**; closed-source is not accepted | `CONDITIONAL` | review-criteria (raw 73) `[fetch-only]` | n/a |
| S11 | **CONDITIONAL — MCPB only.** The open-source and "spec will evolve" clauses of the Directory Terms are **required and not waivable** | `CONDITIONAL` | review-criteria (raw 74) `[fetch-only]` | n/a |
| S12 | **Attestation:** *"You also confirm you've run every tool yourself, either via MCP Inspector or as a custom connector in Claude."* Test-account setup and access instructions must be **detailed enough for a reviewer to access the server end to end: every link, credential and step** | `PORTAL` + `TERMS` | submission (raw 164) · **T3** | ⚠️ **Cannot be ticked truthfully today** — 1 of 8 public tools exercised end to end. Ticking it is a **warranty defect**, not a process shortcut |
| S13 | Testing happens **in production as a custom connector — there is no staging environment.** **Any Claude account (Free, Pro, Max, Team, Enterprise) can add a custom connector**, and custom connectors use **the exact same runtime** as directory connectors | `DOC-CONSTRAINT` | testing (raw 9, 13) `[fetch-only]` | — recorded. **S12's work is NOT gated behind S1** — only the portal is |
| S14 | **Skills are not a standalone submission type** — bundle them in a plugin | `PORTAL` | submission (raw 122) | n/a |

**S8 — the seven acknowledgments, each mapped to what it warrants:**

| # | Acknowledgment | Warrants |
|---|---|---|
| 1 | directory guidelines | P3H + the published design guidelines (§8, §9) |
| 2 | first-party API usage | P3F |
| 3 | financial transactions | P4A |
| 4 | AI media generation | P4B |
| 5 | prompt injection | P2D–P2G |
| 6 | conversation data collection | P1D and P1F |
| 7 | public documentation | P3A / P3B / P3C / P3E |

---

## 12. Post-publication

⚠️ `[relay-only]` — `after-publishing` has no artifact in the tree.

| ID | Requirement | Level | Source | PG status |
|---|---|---|---|---|
| PUB1 | **Tool changes require no resubmission and there is no scheduled re-review.** Deploy to the server; Claude picks up the new tool surface on the next connection | `DOC-CONSTRAINT` | after-publishing `[relay-only]` | — recorded |
| PUB2 | **"No scheduled re-review" is not "never reviewed."** Anthropic conducts **both initial and ongoing reviews**, and **T8** obliges continued compliance with the Policy as updated | `POLICY` + `TERMS` | policy (raw 3) · terms (raw 9) | — recorded |
| PUB3 | Listing edits go through the submissions dashboard; `managing-your-listing` defines which changes can be made directly and which require review | `PORTAL` | after-publishing `[relay-only]` | — not assessed. ⚠️ **`managing-your-listing` is uncaptured (§13)** |
| PUB4 | Delisting is requested by emailing **`mcp-review@anthropic.com`** | `PORTAL` | after-publishing `[relay-only]` | — recorded |

---

## 13. Uncaptured obligations — known to bind, never read

**Nine gaps.** These are not rows above because nothing has been read. They are listed so the gaps
are visible **in the canonical document**, not only in the master's header.

**Binding, never read (5):**

| Document | Made binding by |
|---|---|
| **Trademark Guidelines** | Terms **T10** — and it constrains launch copy directly |
| **Usage Policy** | Policy **§1A** |
| **Universal Usage Standards** | Policy **§1A** |
| **High-Risk Use Case requirements** | Policy **§1A** |
| **Supported-countries policy** | Policy **§1A** |

⚠️ **Policy §1A alone makes four of these binding**, and `llms.txt` indexes `claude.com/docs` only —
so a clean read of the documentation index is **not** full coverage.

**Referenced requirement surfaces, never read (2):**

- **Enterprise Managed Auth** — SSO organisations can connect users **without an interactive OAuth
  consent step**, via an IdP-signed identity assertion. The linked page states what the
  authorization server must support.
- **`building/directory-vs-custom`** — PG is a **custom connector today** and becomes a directory
  connector after review. Behaviour already differs (see **L8**); other differences are unknown.

**Post-publication, never read (1):**

- **`building/managing-your-listing`** — holds the edit-vs-review boundary (**PUB3**).

**One page away from full traceability (3):**

| Page | Feeds | Marker comes off when |
|---|---|---|
| `external-links` | **all of §10** | pasted to the committing session |
| `troubleshooting` | §4O of the master | pasted to the committing session |
| **`after-publishing`** | **all of §12**, and **S6** (the permanent slug) | pasted to the committing session |

⚠️ **These three are `[relay-only]`, NOT unobtainable.** All were pasted into the review chat; they
simply have not been handed to the session that commits files. **One paste each and the markers come
off** — §10 and §12 become paste-provenance, the strongest category in this document.

*[Corrected 2026-08-05: `after-publishing` was cited and marked `[relay-only]` in §12 while being
absent from both the header's marker definition and this list — the apparatus did not know about a
source the rows already depended on. Two of three, listed as all of them.]*

**Header count reconciliation:** 5 binding + 3 referenced surfaces = **8 silent**; 3 relay-only =
**weakly sourced**; **11 items**. Stated because *"silent on 9"* previously appeared in the header
and reconciled to nothing in this section.
