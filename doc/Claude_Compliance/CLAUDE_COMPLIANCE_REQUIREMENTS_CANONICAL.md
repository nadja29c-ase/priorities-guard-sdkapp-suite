# Claude MCP App — Canonical Compliance Requirements

**What this is.** Every requirement an MCP App for Claude must satisfy to pass directory review, and
nothing else. **This is an EVALUATION INSTRUMENT — the questions, not the answers.** Read it to know
what must be true; use it to assess any app against the current sources.

⚠️ **It contains NO assessment of any particular app, deliberately.** A requirements document that
carries its own answers stops being usable as an instrument: the reader sees a verdict instead of a
criterion, the verdict goes stale while the criterion does not, and the same file then has to be
re-verified every time the code changes.
*[A "PG status" column stood here until 2026-08-05 and was removed for exactly that reason. The
findings it held were not discarded — they are in the master's §9, which is where recorded status
belongs.]*

The master (`COMPLIANCE_AUDIT_RECORD.md`) is the source synthesis and audit record —
changelog, provenance, standing checks, sweep results, per-app status and implementation mechanism.
Neither file substitutes for the other.

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

**How to use this as an instrument.** For each row, ask: *does the app satisfy this, and what is the
evidence?* Record the answer **elsewhere** — per-app status belongs in the audit record, not here.
Levels tell you what a failure costs: `POLICY`, `TERMS`, `PORTAL` and `DOC-CONSTRAINT` rows can
block or unwind a listing; `SPEC` and `RECOMMENDED` rows cannot; `CONDITIONAL` rows only apply when
their stated precondition holds.

---

## 1. Safety & Security

| ID | Requirement | Level | Source |
|---|---|---|---|
| P1A | Must not violate or facilitate violation of the Usage Policy; must comply with Universal Usage Standards, High-Risk Use Case requirements and the supported-countries policy | `POLICY` | policy §1A (raw 7) |
| P1B | Must not evade, or let users circumvent, Claude's safety guardrails, system instructions or sandbox | `POLICY` | policy §1B (raw 9) |
| P1C | Must prioritise user **and third-party** privacy; handle personal and sensitive data responsibly; comply with applicable law | `POLICY` | policy §1C (raw 11) |
| P1D | Must collect only data from the user's context necessary to function. **Must not collect extraneous conversation data, even for logging purposes** | `POLICY` | policy §1D (raw 13) |
| P1E | Must not infringe intellectual property rights | `POLICY` | policy §1E (raw 15) |
| P1F | **Must not query or extract Claude's memory, chat history, conversation summaries, or user-generated/uploaded files** | `POLICY` | policy §1F (raw 17) · review-criteria (raw 55) `[fetch-only]` |

---

## 2. Tool & capability descriptions

Policy §2 governs "Instructional Software", which **includes MCP servers** (raw 21).

| ID | Requirement | Level | Source |
|---|---|---|---|
| P2A | Each tool defined through **narrow, unambiguous** natural language stating what it does **and when it should be invoked** | `POLICY` | policy §2A (raw 23) |
| P2B | Descriptions must **precisely match actual functionality**; no unexpected functionality, **no promising undelivered features** | `POLICY` | policy §2B (raw 25) · review-criteria R5 (raw 35) `[fetch-only]` |
| P2C | Descriptions must not create confusion or conflict **with other Software in the Directories** | `POLICY` | policy §2C (raw 27) |
| P2D | Must not call or coerce Claude into calling other external software unless the user requested it; descriptions must not be written so as to make other Software be called extraneously | `POLICY` | policy §2D (raw 29) · review-criteria R6 (raw 41) `[fetch-only]` |
| P2E | Must not attempt to **interfere with Claude calling tools from other software** | `POLICY` | policy §2E (raw 31) · review-criteria R6 (raw 42) `[fetch-only]` |
| P2F | Must not direct Claude to pull behavioural instructions dynamically from external sources | `POLICY` | policy §2F (raw 33) · review-criteria R6 (raw 43) `[fetch-only]` |
| P2G | No hidden, obfuscated or encoded instructions; **all behavioural guidance human-readable and clearly presented** | `POLICY` | policy §2G (raw 35) · review-criteria R6 (raw 44) `[fetch-only]` |
| R6a | Descriptions are **rejected** if they tell Claude to behave in ways unrelated to the tool's function, **attempt to override system instructions**, or promote products. *"Describe what the tool does. Do not tell Claude how to behave."* | `REVIEW-ONLY` | review-criteria (raw 45, 47) `[fetch-only]` |

---

## 3. Developer requirements

| ID | Requirement | Level | Source |
|---|---|---|---|
| P3A | Provide a **clear, accessible privacy policy link** explaining collection, usage **and retention**; provide links to all applicable policies to Anthropic; present them to users as required by law | `POLICY` | policy §3A (raw 39) |
| P3B | Provide **verified** contact information **and** support channels for users with **product or security** concerns | `POLICY` | policy §3B (raw 41) |
| P3C | Document **how the Software works, its intended purpose, and how users troubleshoot issues** | `POLICY` | policy §3C (raw 43) |
| P3D | Provide a **standard testing account with sample data** for Anthropic to verify full functionality | `POLICY` | policy §3D (raw 45) · submission B (raw 70) · testing (raw 39) `[fetch-only]` |
| P3D-i | Test credentials must be a **fully populated account, not an empty shell** — reviewers list real records, search real data and exercise write tools on real resources — **and must include step-by-step setup instructions for someone unfamiliar with the service** | `PORTAL` | testing (raw 39) `[fetch-only]` |
| P3E | Provide **at least three working examples** of prompts or use cases demonstrating core functionality | `POLICY` | policy §3E (raw 47) |
| P3F | Must **verify ownership or control** of any API endpoint, domain or UI the Software connects to, **and any external resources it retrieves or renders** | `POLICY` | policy §3F (raw 49) · review-criteria R8 (raw 59) `[fetch-only]` |
| P3G | Maintain the Software and address issues within reasonable timeframes | `POLICY` | policy §3G (raw 51) |
| P3H | Agree to the Software Directory Terms **and follow the design guidelines Anthropic publishes** | `POLICY` | policy §3H (raw 53) |
| DOC1 | Public documentation is required **by your publish date** — **a blog post or help-centre article is sufficient**; may be shared privately with Anthropic during review | `REVIEW-ONLY` | review-criteria (raw 72) `[fetch-only]` |

---

## 4. Unsupported use cases

| ID | Requirement | Level | Source |
|---|---|---|---|
| P4A | Must not transfer money, cryptocurrency or other financial assets, or execute financial transactions on a user's behalf | `POLICY` | policy §4A (raw 59) · review-criteria (raw 65) `[fetch-only]` |
| P4B | Must not use AI models to generate images, video or audio. **Design-focused visual aids are permitted** (slides, diagrams, charts, UI mockups, logos) provided standalone generation is not offered as a primary service | `POLICY` | policy §4B (raw 61) · review-criteria (raw 66) `[fetch-only]` |
| P4C | Must not serve **advertisements, sponsored content or paid product placements**, or exist primarily as an advertising or promotional vehicle | `POLICY` | policy §4C (raw 63) |

---

## 5. MCP server requirements

| ID | Requirement | Level | Source |
|---|---|---|---|
| P5A | Must **gracefully handle errors** and provide helpful feedback rather than generic error messages | `POLICY` | policy §5A (raw 67) · review-criteria R7 (raw 51) `[fetch-only]` |
| P5B | Must be **frugal with tokens** — usage roughly commensurate with task complexity or impact; **where possible give users options to exclude unnecessary text** | `POLICY` | policy §5B (raw 69) |
| P5C | Tool names must not exceed **64 characters** | `POLICY` | policy §5C (raw 71) · review-criteria R4 (raw 31) `[fetch-only]` |
| P5D | Remote servers that connect to a remote service and require authentication must use **secure OAuth 2.0 with certificates from recognized authorities** | `POLICY` | policy §5D (raw 73) |
| P5E | Must provide **all applicable annotations**, in particular **`readOnlyHint`, `destructiveHint` and `title`** | `POLICY` | policy §5E (raw 75) · review-criteria R3 (raw 27) `[fetch-only]` |
| P5F | **Should** support **Streamable HTTP**. SSE is tolerated *"for the time being"* and **will be deprecated** | `RECOMMENDED` | policy §5F (raw 77) |
| P5G | Local servers must use reasonably current dependency versions, including `node_modules` | `POLICY` | policy §5G (raw 79) |
| R1 | **Read and write tools must be separate.** A single tool accepting both safe (GET/HEAD/OPTIONS) and unsafe (POST/PUT/PATCH/DELETE) methods is **rejected**. Documenting the split inside one description **does not satisfy this** | `REVIEW-ONLY` | review-criteria (raw 15-17) `[fetch-only]` |
| R2 | **CONDITIONAL — applies only to custom query tools.** If a tool accepts freeform endpoint paths, query strings or request bodies constructed by the caller, its description must link to or explicitly name the target API | `CONDITIONAL` | review-criteria (raw 19-23) `[fetch-only]` |
| R7a | Every tool must return a **successful response** when called with valid parameters; generic errors fail review. Validate inputs and return **actionable** errors. Keep responses reasonably sized | `REVIEW-ONLY` | review-criteria (raw 51-53) `[fetch-only]` |
| R11 | **Before submitting, exercise every tool** through the MCP Inspector **and** as a custom connector in Claude | `REVIEW-ONLY` | review-criteria (raw 78) `[fetch-only]` · testing `[fetch-only]` |

---

## 6. Directory Terms warranties

Policy §3H makes agreeing to these mandatory. **The Policy says what the Software must do; the
Terms are what you warrant when you submit.** Published 16 March 2026.

| ID | Requirement | Level | Source |
|---|---|---|---|
| T1 | You have and will maintain all rights necessary to provide the Software and grant the rights in the Terms | `TERMS` | terms (raw 3-i) |
| T2 | The Software and its ordinary intended use comply with all applicable law and do not violate the Policy **as updated from time to time** | `TERMS` | terms (raw 3-ii) |
| T3 | **"Any information you give us will be accurate and up-to-date."** A warranty over **every field of the submission portal** | `TERMS` | terms (raw 3-iii) |
| T4 | Provide **and adhere to** a privacy policy; **provide all applicable third-party privacy policies**; all such policies must **clearly and accurately describe** what you **and third parties** collect, use and share | `TERMS` | terms (raw 3-iv) |
| T5 | Indemnify and hold Anthropic harmless from claims arising from the Software or users' interactions with it | `TERMS` | terms (raw 5-i) |
| T6 | Grant Anthropic non-exclusive, royalty-free, worldwide licences to reproduce, display and distribute Software descriptions and documentation, and to display your name, trademarks, logos and branding in the Directories | `TERMS` | terms (raw 5-ii) |
| T7 | Authorise Anthropic to review and test the Software, and to **collect, use and share functional metadata** about it | `TERMS` | terms (raw 5-iii) |
| T8 | **Continue implementing and maintaining quality and security standards consistent with the Policy, as updated.** Failure may result in removal | `TERMS` | terms (raw 9) |
| T9 | **Implement and maintain a mechanism for receiving security vulnerability reports from Anthropic and from third parties, and investigate them with a reasonable standard of care** | `TERMS` | terms (raw 9) |
| T10 | Make **no statement suggesting partnership, sponsorship or endorsement** by Anthropic without prior written approval; **comply at all times with Anthropic's Trademark Guidelines** | `TERMS` | terms (raw 11) |

**Also binding, recorded:** Anthropic has **no obligation** to include the Software and may remove it
at any time for any reason without liability (raw 7). Terms may be **modified without prior notice**;
continued maintenance constitutes acceptance (raw 11).

---

## 7. Authentication & OAuth

| ID | Requirement | Level | Source |
|---|---|---|---|
| A1 | AS must **support S256 PKCE** — Claude sends `code_challenge_method=S256` on **every** authorization request, regardless of registration mechanism | `DOC-CONSTRAINT` | authentication (raw 55) |
| A2 | AS metadata must advertise `"code_challenge_methods_supported": ["S256"]` | `SPEC` | authentication (raw 55) |
| A3 | Return **401** with a `WWW-Authenticate` header whose `resource_metadata` points at the PRM document. **The 401 status is required — Claude does not honor `WWW-Authenticate` on a 200** | `DOC-CONSTRAINT` | authentication (raw 63, 70) |
| A4 | PRM `resource` must match the MCP server URL **exactly as the user enters it in Claude**, including any path component | `DOC-CONSTRAINT` | authentication (raw 76) |
| A5 | PRM `authorization_servers` must list the AS issuer URL. **Claude uses the first entry and does not fall back** | `DOC-CONSTRAINT` | authentication (raw 77) |
| A6 | AS must serve its own discovery metadata (RFC 8414 or OIDC Discovery) at its `/.well-known/` paths | `DOC-CONSTRAINT` | authentication (raw 78) |
| A7 | That AS host must be **reachable from Anthropic's egress range** `160.79.104.0/21` — a WAF in front of the IdP breaks the flow even when the MCP server is reachable | `DOC-CONSTRAINT` | authentication (raw 78, 141) |
| A8 | Register the redirect URI `https://claude.ai/api/mcp/auth_callback` for hosted surfaces | `DOC-CONSTRAINT` | authentication (raw 92-96) |
| A9 | For Claude Code, accept **both** `http://localhost/callback` **and** `http://127.0.0.1/callback` **with the port component ignored** | `DOC-CONSTRAINT` | authentication (raw 104) |
| A10 | Return RFC 6749-compliant error codes — **`invalid_grant`**, not `invalid_request` or a custom code — when a refresh token is no longer valid | `DOC-CONSTRAINT` | authentication (raw 112) |
| A11 | **Rotate refresh tokens for public clients.** If rotating, return the new refresh token in the same response that invalidates the old | `SPEC` | authentication (raw 113) |
| A12 | `/token` must accept `Content-Type: application/x-www-form-urlencoded` (RFC 6749 §4.1.3) | `DOC-CONSTRAINT` | authentication (raw 115) |
| A13 | `/register` uses `application/json` (RFC 7591 §3.1) — **do not assume one parser serves both** | `DOC-CONSTRAINT` | authentication (raw 115) |
| A14 | Respond within **10 s** for discovery, registration and token endpoints and **30 s** for refresh; **return headers and body without buffering behind upstream work**, and ensure no proxy, gateway or WAF holds the response | `DOC-CONSTRAINT` | authentication (raw 135, 137) |
| A15 | Machine-to-machine `client_credentials` is **not supported**; every connection requires user consent | `DOC-CONSTRAINT` | authentication (raw 30) |
| A16 | **Do not put tokens or API keys in the connector URL.** The MCP spec **prohibits** access tokens in the URI query string | `SPEC` | authentication (raw 26) |
| A17 | **CONDITIONAL — CIMD selection.** Claude selects CIMD **only when** AS metadata advertises **both** `"client_id_metadata_document_supported": true` **and** `"none"` in `token_endpoint_auth_methods_supported`. If either is missing it falls back to DCR | `CONDITIONAL` | authentication (raw 50) |
| A18 | AS must **display the redirect URI hostname clearly on the consent screen** (unconditional), and **should** add an extra warning when the only registered redirect URIs are loopback addresses | `SPEC` | authentication (raw 106) |
| A19 | **`clientInfo` is unauthenticated and must never feed an authorization decision.** Any client can claim any name; do not gate behaviour on an exact `name` or `version` — both vary across surfaces and releases | `DOC-CONSTRAINT` | testing (raw 35) `[fetch-only]` |
| A20 | **CONDITIONAL — Microsoft Entra ID only.** Register the MCP server URL as an **Application ID URI** on the Entra app registration, or the token request fails `AADSTS9010010` | `CONDITIONAL` | authentication (raw 81) |
| A21 | **CONDITIONAL — `oauth_anthropic_creds` only.** Credentials are bound to the issuing AS; email `mcp-review@anthropic.com` with new credentials **before** migrating to a new authorization server | `CONDITIONAL` | authentication (raw 41) |
| A22 | Return **401**, not a tool error. A **200 with `isError: true` is an application-level failure** — Claude passes the text to the model and moves on, with **no auth prompt**. A **403** triggers re-authentication **only** with `error="insufficient_scope"`; any other 403 is terminal | `DOC-CONSTRAINT` | lazy-authentication (raw 43, 123) `[fetch-only]` |
| A23 | Include a `scope` parameter in the 401's `WWW-Authenticate`. Omitting it makes Claude request everything in PRM `scopes_supported` plus `offline_access`, **which can produce an over-broad consent prompt** | `RECOMMENDED` | authentication (raw 57) · lazy-authentication (raw 32) `[fetch-only]` |
| A24 | **RECOMMENDED — DCR at scale.** For servers expecting high traffic from the directory, **prefer CIMD or `oauth_anthropic_creds` over DCR**; DCR registers a new client on every fresh connection | `RECOMMENDED` | authentication (raw 53) |

---

## 8. MCP Apps — display modes & design

Binding via **Policy §3H** (*"follow design guidelines Anthropic publishes"*).

| ID | Requirement | Level | Source |
|---|---|---|---|
| M1 | All views must support **both light and dark themes**; use host style tokens; **never hardcode colors**; test both modes | `DOC-CONSTRAINT` | design-guidelines (raw 204) — **one of only two developer "must" statements on the page** |
| M2 | **WCAG AA** contrast minimum, keyboard navigation, text alternatives, tested with assistive technologies — *"your app must be usable by everyone"* | `DOC-CONSTRAINT` | design-guidelines (raw 278) — the other developer "must" |
| M3 | Render interactive UI **inside `safeAreaInsets`**. **Not mobile-specific** — on web and desktop the composer can overlay the bottom of an inline app | `DOC-CONSTRAINT` | design-guidelines (raw 134) |
| M4 | Inline: **auto-fit content height, no nested vertical scroll.** The host caps and clips. **No pixel value is published** | `DOC-CONSTRAINT` | design-guidelines (raw 39, 62, 186) |
| M5 | Inline: maximum **2 actions**, at the bottom of the card | `DOC-CONSTRAINT` | design-guidelines (raw 63) |
| M6 | Inline: maximum **4–5 data points** | `DOC-CONSTRAINT` | design-guidelines (raw 64) |
| M7 | No drill-ins, breadcrumbs or multiple views; no menus or popovers — use visible controls (they get clipped by container boundaries or conflict with host z-index) | `DOC-CONSTRAINT` | design-guidelines (raw 65-66, 38, 40) |
| M8 | Fullscreen: **avoid** floating panels — use collapsible sidebars, tabs or pagination; the app provides its own fullscreen button; a close button appears in the native header; the composer remains available | `RECOMMENDED` | design-guidelines (raw 99) |
| M9 | Touch targets **≥ 44pt** on mobile; content adapts to narrow viewports **without horizontal scrolling** | `DOC-CONSTRAINT` | design-guidelines (raw 68) |
| M10 | **No fixed-width layouts**; responsive from **320px**; **no side margins** that waste screen real estate — apps always fill the container width, with no fixed breakpoints | `DOC-CONSTRAINT` | design-guidelines (raw 284-286) |
| M11 | Declare `_meta.ui.csp` — **CONDITIONAL:** required only if the widget loads external origins. All external origins are blocked by default | `CONDITIONAL` | design-guidelines (raw 150-159) |
| M12 | Declare `appCapabilities.availableDisplayModes` in `ui/initialize` | `DOC-CONSTRAINT` | design-guidelines §Display modes (raw 43, 144) |
| M13 | **CONDITIONAL — carousels.** Maintain consistent card dimensions; on mobile design for thumb reach with primary actions in the lower portion, and **peek the next card** to signal scrollability | `CONDITIONAL` | design-guidelines (raw 72-95) |
| M14 | **`prefersBorder` — set true or false explicitly.** If unspecified: **borderless on web, bordered on mobile.** Borderless runs edge-to-edge with **no host padding**, so honouring `safeAreaInsets` becomes essential | `RECOMMENDED` | design-guidelines (raw 138) · transparent-theming (raw 21) |
| M15 | Mobile fullscreen **is supported.** Mobile renders in a native WebView, not a sandboxed iframe: no camera/mic/location, and connectors must be added via web or desktop before appearing on mobile | `DOC-CONSTRAINT` | design-guidelines (raw 120, 128) |
| M16 | **No chat inputs or conversational UI** — *"don't replicate Claude's features"* | `DOC-CONSTRAINT` | design-guidelines (raw 41) |
| M17 | **CONDITIONAL — if the app genuinely needs its own vertically scrollable viewport**, request fullscreen via `ui/request-display-mode` instead of rendering inline. *(This is M4's remedy; M4 states the constraint without it)* | `CONDITIONAL` | design-guidelines (raw 192) |
| M18 | **Use host tokens for ALL structural elements** — backgrounds, text, borders **and icons**. Brand colours are for **accents and identity only**; the core UI uses the provided palette. *(Broader than M1's "never hardcode colors")* | `DOC-CONSTRAINT` | design-guidelines (raw 220, 216) |
| M19 | **Icons: monochromatic and outlined, matching the host's icon colour tokens.** Icons should support understanding, **not be essential to it** | `DOC-CONSTRAINT` | design-guidelines (raw 236) |
| M20 | **Loading states: skeleton screens, not spinners** for inline content. Match the layout structure of the final content so the transition feels seamless | `DOC-CONSTRAINT` | design-guidelines (raw 210) |

---

## 9. MCP Apps — widget domain, CSP, theming

| ID | Requirement | Level | Source |
|---|---|---|---|
| X1 | **CONDITIONAL — `_meta.ui.domain` is OPTIONAL.** Its format and validation are **host-determined**. **Without it, Claude derives the iframe origin per conversation and connector.** Setting it opts into a **stable sandbox origin — needed if the app runs its own OAuth flow** | `CONDITIONAL` | cross-compatibility (raw 27) · instance-supersession (raw 179) |
| X2 | **CONDITIONAL — if `ui.domain` is set for Claude:** `sha256(<full connector URL>)[:32] + ".claudemcpcontent.com"`. **Hash the exact string entered in Settings > Connectors, including path and any trailing slash** | `CONDITIONAL` | cross-compatibility (raw 29-33) |
| X3 | **Local stdio connectors have no URL** — omit `_meta.ui.domain` rather than inventing a value | `CONDITIONAL` | cross-compatibility (raw 27) |
| X4 | `html, body { margin: 0; background: transparent; }` — any opaque background on either hides the chat surface | `DOC-CONSTRAINT` | transparent-theming (raw 16) |
| X5 | `<meta name="color-scheme" content="light dark" />` in the document head, **kept** even though `applyDocumentTheme` sets it at runtime — the tag covers first paint | `DOC-CONSTRAINT` | transparent-theming (raw 17) |
| X6 | **CONDITIONAL — host fonts only.** CSP `resourceDomains` must include `https://assets.claude.ai` for `applyHostFonts` to load the `@font-face` files | `CONDITIONAL` | transparent-theming (raw 18) |
| X7 | **Register the `hostcontextchanged` listener before you connect**, so an early update is not missed | `DOC-CONSTRAINT` | transparent-theming (raw 19) |
| X8 | `resourceDomains` **also adds the listed origins to `script-src` and `style-src`** — keep it to origins trusted to serve executable code; prefer bundling third-party fonts over allowlisting public CDNs | `DOC-CONSTRAINT` | transparent-theming (raw 52-54) |
| X9 | **The app must connect before it can receive anything.** Call `App.connect()` (or `useApp()`, which creates and connects for you in React) **without an explicit transport parameter** — the SDK detects Claude vs ChatGPT and selects the transport. ⚠️ **Tool-input and tool-result events do not fire until the app is connected**, which is the most common cause of an app that renders nothing | `DOC-CONSTRAINT` | cross-compatibility (raw 19) · transparent-theming (raw 86, 112) · ⚠️ the *"events don't fire until connected"* warning is from `troubleshooting` `[relay-only]` |

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

| ID | Requirement | Level | Source |
|---|---|---|---|
| L1 | **CONDITIONAL — the field is optional.** It applies only if the connector uses `ui/open-link`. If omitted the connector functions normally, but **users are shown a confirmation prompt each time it opens a link** | `CONDITIONAL` | **submission §Allowed link URIs (raw 75, 85-86)** |
| L2 | **Every origin and scheme listed must be owned by you (the submitting organization).** You may not list third-party domains or schemes registered to apps you don't publish. **Entries you don't own will be removed during review** | `PORTAL` | **submission (raw 82)** |
| L3 | An HTTPS origin entry matches **scheme and hostname only** — paths, ports and query strings are ignored. **Subdomains are not implied — list each one** (`https://app.example.com`, `https://docs.example.com`) | `PORTAL` | **submission (raw 79)** |
| L4 | A **custom URI scheme** entry (`myapp:`) is for deep links into a native app **you own**; only the scheme is matched | `PORTAL` | **submission (raw 80)** |
| L5 | **Malformed entries are IGNORED** — not rejected. Both this and L2 fail **silently**: the listing ships, the entry is gone, and users get the confirmation modal on every link | `PORTAL` | external-links `[relay-only]` |
| L6 | The reserved-scheme list is **open-ended** (*"This includes…"*), not closed | `PORTAL` | external-links `[relay-only]` |
| L7 | A bypassed `ui/open-link` **resolves once the open is attempted** — that is **not** confirmation the user reached the destination | `DOC-CONSTRAINT` | external-links `[relay-only]` |
| L8 | **Custom and local connectors always show the confirmation modal**, regardless of the allowlist | `DOC-CONSTRAINT` | external-links `[relay-only]` |

---

## 11. Submission portal

| ID | Requirement | Level | Source |
|---|---|---|---|
| S1 | **A Team or Enterprise organization is required.** Admin settings — and therefore the portal — are unavailable on individual plans | `PORTAL` | submission (raw 21-23) |
| S2 | The submitter must be an **Owner or Primary Owner**. Enterprise may delegate via a custom role with **Directory management** or **Libraries**; **Team plans have no custom roles** | `PORTAL` | submission (raw 24) |
| S3 | Server URL must be **`https://`** | `PORTAL` | submission §Connection (raw 152) |
| S4 | Every tool must carry a **`title`** and the applicable **`readOnlyHint`/`destructiveHint`**; the portal flags violations to fix **on the server before submitting** | `PORTAL` | submission (raw 46) |
| S5 | Listing limits: **name ≤ 100**, **tagline ≤ 55**, **description ≤ 2,000** characters; **1–5 categories**; plus documentation URL, privacy policy URL, support contact and icon | `PORTAL` | submission (raw 144) |
| S6 | **The URL slug is PERMANENT once published** — `https://claude.ai/directory/connectors/SLUG`. Display names can change; the slug cannot | `PORTAL` | submission · after-publishing `[relay-only]` |
| S7 | **MCP Apps: screenshots required.** 3–5 **PNG**, **≥ 1000px** wide, cropped to the app response area, **the prompt must not appear in the image** (supply prompt text separately). **Aspect ratio unconstrained. Video and GIF rejected. One batch covers all surfaces.** Figma carousel template available | `PORTAL` | submission (raw 88-101) · submission (raw 17) |
| S8 | **Seven compliance acknowledgments, all required** — directory guidelines, first-party API usage, financial transactions, AI media generation, prompt injection, conversation data collection, public documentation. Under **T3** each is a **warranty**, not a checkbox — see the mapping below | `PORTAL` | submission (raw 168) |
| S9 | Data-handling declarations: whether the underlying API is **your own, proxied from a partner with permission, or a third party's you don't control**; whether the connector handles **personal health data** or **sponsored content** | `PORTAL` | submission (raw 160) |
| S10 | **CONDITIONAL — plugins only.** Plugins must link a **public GitHub repo**; closed-source is not accepted | `CONDITIONAL` | review-criteria (raw 73) `[fetch-only]` |
| S11 | **CONDITIONAL — MCPB only.** The open-source and "spec will evolve" clauses of the Directory Terms are **required and not waivable** | `CONDITIONAL` | review-criteria (raw 74) `[fetch-only]` |
| S12 | **Attestation:** *"You also confirm you've run every tool yourself, either via MCP Inspector or as a custom connector in Claude."* Test-account setup and access instructions must be **detailed enough for a reviewer to access the server end to end: every link, credential and step** | `PORTAL` + `TERMS` | submission (raw 164) · **T3** |
| S13 | Testing happens **in production as a custom connector — there is no staging environment.** **Any Claude account (Free, Pro, Max, Team, Enterprise) can add a custom connector**, and custom connectors use **the exact same runtime** as directory connectors | `DOC-CONSTRAINT` | testing (raw 9, 13) `[fetch-only]` |
| S14 | **Skills are not a standalone submission type** — bundle them in a plugin | `PORTAL` | submission (raw 122) |
| S15 | **CONDITIONAL — LOCAL connectors only.** Must include a **"Privacy Policy" section in `README.md`**, a **`privacy_policies` array in `manifest.json`** (manifest_version 0.2+), and **HTTPS URLs** to those policies | `CONDITIONAL` | submission (raw 55-59) |
| S16 | **CONDITIONAL — LOCAL connectors only.** The privacy policy must cover **all five**: data collection practices · usage and storage · third-party sharing · data retention · contact information. ⚠️ **"Missing or incomplete privacy policies result in immediate rejection"** — the only *immediate rejection* warning on the submission page | `CONDITIONAL` | submission (raw 61-70) |

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

| ID | Requirement | Level | Source |
|---|---|---|---|
| PUB1 | **Tool changes require no resubmission and there is no scheduled re-review.** Deploy to the server; Claude picks up the new tool surface on the next connection | `DOC-CONSTRAINT` | after-publishing `[relay-only]` |
| PUB2 | **"No scheduled re-review" is not "never reviewed."** Anthropic conducts **both initial and ongoing reviews**, and **T8** obliges continued compliance with the Policy as updated | `POLICY` + `TERMS` | policy (raw 3) · terms (raw 9) |
| PUB3 | Listing edits go through the submissions dashboard; `managing-your-listing` defines which changes can be made directly and which require review | `PORTAL` | after-publishing `[relay-only]` |
| PUB4 | Delisting is requested by emailing **`mcp-review@anthropic.com`** | `PORTAL` | after-publishing `[relay-only]` |

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

### ⚠️ THE MISSING PASTES ARE NOW COSTING REQUIREMENTS, NOT JUST PROVENANCE

**Verified 2026-08-05 by checking this file against the pages as pasted in the review chat.** The
result: **four gaps, ~11 missing requirements.** Eight were traceable to captured sources and have
been added (M16–M20, S15–S16, X9). **Three are not, because their only source has never been
committed:**

| Missing requirement | Only source |
|---|---|
| **`ui/open-link` bypasses the modal ONLY after a real user gesture** — a click. Sent programmatically, on a timer, or after the activation window expires, **the modal is shown regardless of the allowlist.** This is the condition that decides whether §10 does anything at all, and an implementation fails it silently | `external-links` |
| **The iframe must have a non-zero height** — a zero height renders nothing | `troubleshooting` |
| **iOS: WebKit omits `Referer` on cross-origin subresource requests.** A server or WAF gating on `Referer` rejects iOS traffic while working everywhere else. Allowlist on **`Origin`** (`{hash}.claudemcpcontent.com`) and return a matching `Access-Control-Allow-Origin` | `troubleshooting` |

**The third is a live functional requirement for the mobile surface.** All three should be rows.

§13 predicted this — *"one paste each and the markers come off"* — but it understated the cost.
**These pages were reviewed in this chat and never handed to the committing session, so their
content was carried by memory and partially dropped.** That is not a provenance downgrade; it is
**absent requirements in the document designated as the sole statement of what must be true.**

**One paste each fixes it, and simultaneously converts three "unsourced" claims** (the
~150,000-character ceiling, the 25,000-token `MAX_MCP_OUTPUT_TOKENS` limit, and the sandbox-
spillover finding) **from unsourced to captured.**

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
