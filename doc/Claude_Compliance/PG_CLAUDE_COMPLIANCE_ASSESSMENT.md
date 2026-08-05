# PG-Claude — Compliance Assessment against the Canonical Requirements

**Assessed:** 2026-08-05 · **Against:** `CLAUDE_COMPLIANCE_REQUIREMENTS_CANONICAL.md`, 129 rows
**Surface:** the **Claude serving path** — `mcp_server/priority_guardian_claude/`, the `backend/`
endpoints it calls, and the shared tool registry **as filtered and overridden for Claude**
(`tools_list_dupl.py`). Not the ChatGPT surface. Not MindSort.

**Method:** code read fresh, plus read-only live probes against `mcp.priority-guard.com` and
`www.priority-guard.com`. No writes, no deploys, no config changes.

| Verdict | Count |
|---|---|
| ✅ **Fulfils** | **54** |
| 🟡 **Partly fulfils** | **11** |
| ❌ **Doesn't fulfil** | **9** |
| ➖ **Not relevant** | **17** |
| ❔ **Don't know** | **38** |

⚠️ **38 "don't know" is the honest headline.** Most are Policy §3 and Terms rows — developer
conduct, published artefacts and organisational commitments that no amount of code reading settles.
They are not hidden failures; they are questions only Nadja can answer.

---

## ❌ DOESN'T FULFIL (9)

| Row | Level | Finding |
|---|---|---|
| **P2B** | POLICY | `inspect_adapt`'s served description says it **"Record[s] confirmed action steps"**. The handler persists nothing — 332 lines, zero backend calls, docstring *"validate provenance → return success"*. A promised undelivered feature |
| **R6a** | REVIEW-ONLY | **Three of eight served descriptions attempt to override Claude's behaviour**: `create_priority`, `inspect_adapt`, `onboarding_calendar_setup` carry `BINDING RULES`, *"your default behavior is SUSPENDED"*, `FORBIDDEN:`, *"Override analytical coaching impulses"*. The rejection criterion is verbatim: *"tell Claude to behave in ways unrelated to the tool's function, attempt to override system instructions"* |
| **P3C** | POLICY | No Claude-specific documentation page exists |
| **P3E** | POLICY | No published set of ≥3 working examples |
| **DOC1** | REVIEW-ONLY | No public documentation page. *(Due by publish date, not submission — but currently absent)* |
| **R11** | REVIEW-ONLY | **1 of 8** public tools exercised end to end (`delete_my_priority_guardian_data`, production, 2026-08-04) |
| **S12** | PORTAL+TERMS | The portal attestation *"you've run every tool yourself"* **cannot be ticked truthfully** — see R11. Under T3 that is a warranty defect |
| **T9** | TERMS | No mechanism for receiving security-vulnerability reports **from Anthropic and third parties** with a duty of care. Distinct from P3B's user support channel |
| **A18** | SPEC | None of the eight `oauth_consent_*.html` templates render the redirect URI hostname. `authorize.py:788`'s context passes `request`, `auth_context_id`, `client_name`, `scopes`, `scope_descriptions`. **Not a directory gate** — absent from both `review-criteria` and the binding policy |

---

## 🟡 PARTLY FULFILS (11)

| Row | Level | Gap |
|---|---|---|
| **P1B** | POLICY | No code evades guardrails. **But** three tool descriptions instruct Claude that *"your default behavior is SUSPENDED"* — an attempt to override system instructions, which is what §1B names |
| **P2A** | POLICY | Descriptions do state what each tool does and when to invoke it. **But** three bury that under behavioural directives |
| **P2E** | POLICY | No description interferes with *other software's* tools. **But** several steer **away** from PG toward other behaviour (*"when the user wants to plan, break down, or organize tasks"*) — unassessed against §2E |
| **P3A** | POLICY | A privacy policy is published. **But** it still routes PG full deletion to `support@priority-guard.com` — wrong now the deletion tool ships — and **v3.2 characterises Anthropic as an Art. 28 processor, which is incorrect** |
| **P3H** | POLICY | Design guidelines largely followed (see M-rows). Terms not yet agreed — submission not made |
| **T3** | TERMS | No inaccurate information submitted **yet**. The Art. 28 error would become one the moment the policy link is given |
| **T4** | TERMS | PG's own policy exists. **Google's applicable third-party policy is not provided**, and PG's policy does not describe what Google collects/uses/shares |
| **M3** ⚠️SILENT | RECOMMENDED | `safeAreaInsets` applied only under `platform === 'mobile' && hostFullscreen` (`App.tsx:709`); the inline branch applies none. `.left`/`.right` never read — horizontal padding hardcoded `16px` |
| **M10** | DOC-CONSTRAINT | **Inline: compliant** — `max-width` with `width:100%` reflows from 320px. **Fullscreen: not** — `#root`'s 600px cap binds and `margin: 0 auto` produces the side margins M10 names. Four layered caps; the two 672px ones are dead |
| **M20** | DOC-CONSTRAINT | Loading states exist (`App.tsx:537-548`, `isLoading` in components) but are **text, not skeleton screens** |
| **X6** | CONDITIONAL | `resourceDomains: ["https://assets.claude.ai"]` declared on all three blocks — **and no `--font-*` token is referenced anywhere in the widget**. The CSP is widened for a capability not exercised |

---

## ✅ FULFILS (54)

**Authentication — verified live 2026-08-05**

| Row | Evidence |
|---|---|
| A1, A2 | AS metadata: `code_challenge_methods_supported: ["S256"]` |
| A3 | `HTTP/2 401` + `WWW-Authenticate: Bearer resource_metadata="…/oauth-protected-resource/mcp", scope="pg.access"` |
| A4 | PRM `resource: https://mcp.priority-guard.com/mcp` — exact match |
| A5 | `authorization_servers: ["https://www.priority-guard.com"]` — single entry |
| A6 | RFC 8414 metadata served; `issuer` = root domain |
| A8 | `config.py:62-63` registers both `claude.ai` and `claude.com` callbacks |
| A9 | `_is_loopback_redirect_uri()` run against Claude Code's **published CIMD** — both declared URIs accepted, port-agnostic, negative controls rejected |
| A10 | Live: token endpoint returns `invalid_grant` |
| A11 | `token_service.py` marks the old token revoked in the same exchange |
| A12 | Live: form-urlencoded → `400 invalid_grant`, **not 415** |
| A13 | Live: JSON → `422 grant_type: Field required` — parser split confirmed |
| A15 | No `client_credentials` implemented |
| A16 | Bearer header only; no `?token=`/`?apiKey=` read on the MCP path |
| A22 ⚠️SILENT | PG returns a transport-level 401, not `200 + isError` |
| A23 | `scope="pg.access"` present on the 401 |
| A24 | DCR supported and working (recorded, not a gate) |

**Policy**

P1D (`record_widget_diagnostic` is `private`, never served to Claude, and no PG-Claude code calls
it) · P1F (grep over `mcp_server/**/*.py` + `backend/**/*.py` for memory/history/summary/user-file
identifiers → **0 matches**) · P2F · P2G · P3F (first-party backend; `mcp.priority-guard.com`
matches the service) · P4A · P4B · P4C · P5A (all 8 tool modules raise structured `ToolUsageError`
rather than generic failures) · P5C (**8/8**, longest served name 32 of 64) · P5D (OAuth 2.0 +
PKCE S256, TLS on both hosts) · P5E (**8/8** carry `title` + at least one hint; `title` is a
required positional field on `ToolDefinition`, and `create_priority` is overridden to
`destructiveHint: true` for Claude at `tools_list_dupl.py:57`) · R1 (purpose-built tools, no
catch-all with a `method` parameter, writes split by action type)

**Design & widget**

M1 (275 `var(--color…)` uses) · M2 · M4 ⚠️SILENT · M5 · M6 · M7 · M8 · M9 · M11 (CSP declared on
all three `_meta.ui` blocks) · M12 (`availableDisplayModes: ['inline','fullscreen']`) · M15 ·
**M16** (the only `<textarea>` is `AddPriorityForm.tsx:437` — a priority-entry field, **not a chat
input**) · M17 (`requestDisplayMode` used) · M18 · **M19** (grep for emoji across
`widget-react/src` → **none**; icons are SVG) · M14 *(set explicitly — see M3 for the cost)*

**Domain, CSP, theming**

X1 (set deliberately; the widget runs its own OAuth flow and needs a stable sandbox origin) ·
X2 ⚠️SILENT (computed at import from `MCP_RESOURCE_URL`; `…/mcp` → `a7b31ccb…`) · X4 ⚠️SILENT
(`main.css:8-15`) · X5 (present in the Vite input **and** the served artifact) · X8 (caveat
recorded) · X9 ⚠️SILENT (`useApp()` at `App.tsx:80`)

**External links**

L1 (PG calls `openLink`) · L2 ⚠️SILENT (target is `BACKEND_PUBLIC_URL` =
`https://www.priority-guard.com`, a domain PG owns — **not** `accounts.google.com`) ·
L8 (PG is a custom connector until published — modal always shown, as expected)

**Submission**

S3 (server URL is `https://`) · S4 (**8/8** annotated; nothing lands in the un-annotated group) ·
S13 (testing is available on the current plan — any account can add a custom connector)

---

## ➖ NOT RELEVANT (17)

**Preconditions that don't hold for PG:**

- **Local connectors**: P5G, S15, S16
- **Plugins**: S10
- **MCPB**: S11
- **Custom query tools**: R2 — no PG tool accepts caller-constructed paths or bodies
- **Microsoft Entra ID**: A20 — PG runs its own AS
- **`oauth_anthropic_creds`**: A21 — PG uses `oauth_dcr`
- **CIMD selection logic**: A17 — describes Claude's behaviour, not a duty on the server
- **Carousels**: M13 — PG ships none
- **stdio connectors**: X3 — PG is remote
- **Custom URI schemes**: L4 — PG declares none
- **Post-publication**: PUB1, PUB2, PUB3, PUB4 — PG is not published
- **Slug**: S6 ⚠️SILENT — not yet chosen

---

## ❔ DON'T KNOW (38)

**Cannot be settled from the repo or a read-only probe.** Grouped by what would settle each.

**Needs a decision or an artefact from Nadja (14)** — P1A *(the four §1A documents are uncaptured;
PG shows no obvious violation, but the standard is unread)* · P1C *(third-party calendar data —
covered by the retention model, but three versions exist and which governs is unresolved)* · P1E ·
P2C *(cross-connector conflict with MindSort — never assessed)* · P3B *(is the published contact
"verified"?)* · P3D, P3D-i *(test account with sample data + step-by-step setup instructions)* ·
P3G · T1, T2, T5, T6, T7, T8, T10 *(organisational and legal commitments, not code)*

**Needs a measurement (7)** — A7 *(egress reachability — cannot originate from Anthropic's range)* ·
A14 *(10 s/30 s under load)* · P5B *(token frugality: no measurement of result size against task
complexity, and no user option to exclude text)* · P5F *(Streamable HTTP vs SSE — transport not
checked)* · R7a *(every tool returns a successful response with valid parameters — same gap as R11)* ·
X7 ⚠️*(listener registered before connect: `onhostcontextchanged` is assigned inside `onAppCreated`
at `App.tsx:144`; whether that fires before `connect()` is SDK internals)* · L3 *(confirm the live
`BACKEND_PUBLIC_URL` before filling the portal — subdomains are not implied)*

**Depends on the submission, which hasn't happened (9)** — S1 *(a **Team or Enterprise org is
required and PG has neither** — this blocks submission entirely, but it is a plan decision, not a
compliance failure)* · S2 · S5 · S7 · S8 · S9 · S14 · P3H *(partly, above)* · T3/T4 *(partly, above)*

**Rests on a source nobody has confirmed is current (8)** — every verdict on a `[relay-only]` or
`[fetch-only]` row inherits that source's uncertainty: **L5, L7** *(`external-links`, no artifact)* ·
**R1, R2, R6a, R7a, R11, DOC1, S10, S11** *(`review-criteria`, fetch-only and undated)*. The
verdicts above are given against the bytes we hold; **the bytes' currency is unverified.**

---

## The three requirements that are not yet rows

From pages pasted but never committed. Assessed anyway:

| Requirement | PG | Note |
|---|---|---|
| **`ui/open-link` bypasses the modal only after a real user gesture** | ✅ **Fulfils** | `ConnectionStatus.tsx:40` `handleConnect` is a `useCallback` bound to `onClick` at `:247`; `openLink` is called inside it at `:64`. **A genuine click gesture** |
| **Iframe must have non-zero height** | ❔ Don't know | Host-controlled; not observable from the repo |
| **iOS: allowlist on `Origin`, not `Referer`** | ❔ Don't know | No `Referer`-based gating found in `backend/`, which is the good sign — but the CDN/WAF layer was not inspected |

---

## What I would look at first

1. **S1 — no Team/Enterprise org.** Blocks submission outright. Not a compliance failure; a purchase decision.
2. **R6a + P2B + P1B** — three descriptions carry override language and one advertises persistence it doesn't have. **Descriptions are shared with the live ChatGPT app**, so this is not a Claude-only edit.
3. **R11 / S12** — eight tools through the Inspector or a custom connector. **Not gated by S1**: any account can add a custom connector.
4. **T9 and the Art. 28 correction** — both small, both warranty-relevant.
5. **M10 fullscreen and M3 safe areas** — the two ⚠️SILENT design rows that fail without any error.
