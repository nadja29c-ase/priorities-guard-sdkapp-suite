# PG-Claude — Compliance Assessment

**Assessed:** 2026-08-05 · **Against:** `CLAUDE_COMPLIANCE_REQUIREMENTS_CANONICAL.md`, 129 rows
**Surface:** the **Claude serving path** — `mcp_server/priority_guardian_claude/`, the `backend/`
endpoints it calls, and the shared registry **as filtered and overridden for Claude**
(`tools_list_dupl.py`). Not the ChatGPT surface. Not MindSort.
**Method:** code read, plus read-only live probes. No writes, no deploys, no config changes.

| Verdict | Count |
|---|---|
| ✅ **Fulfils** | **51** |
| 🟡 **Partly fulfils** | **14** |
| ❌ **Doesn't fulfil** | **10** |
| ➖ **Not relevant** | **17** |
| ❔ **Don't know** | **37** |

> **Three passes.** The first assessed many widget rows from `grep` counts. The second read the
> row-relevant paths — **six verdicts moved, all less favourable.** The third read the widget
> **end to end**, all 6,724 lines, and moved **one back up**: the hardcoded colours turn out to be
> documented product identity, which M18 explicitly permits.
>
> **The lesson runs both ways.** Counting made PG look better than it was (M6, M5, M2). Reading a
> flagged line without its rationale made PG look worse than it is (M1/M18). Neither is verification.

> **37 don't-knows is the honest headline.** Most are Policy §3 and Terms rows — developer conduct,
> published artefacts, organisational commitments. No code read settles them.

---

## ❌ DOESN'T FULFIL (10)

| Row | Level | Finding |
|---|---|---|
| **M6** | DOC-CONSTRAINT | **The inline priority list is uncapped.** `App.tsx:602-603` filters actives; `:662` maps them with **no `.slice()`**, and no backend limit exists. Ten active priorities render ten cards inline. M6 is **max 4–5 data points** |
| **P2B** | POLICY | `inspect_adapt`'s served description says it **"Record[s] confirmed action steps"**. The handler persists nothing — 332 lines, zero backend calls, docstring *"validate provenance → return success"* |
| **R6a** | REVIEW-ONLY | **Three of eight served descriptions attempt to override Claude's behaviour** — `create_priority`, `inspect_adapt`, `onboarding_calendar_setup`: `BINDING RULES`, *"your default behavior is SUSPENDED"*, `FORBIDDEN:`, *"Override analytical coaching impulses"* |
| **P3C** | POLICY | No Claude-specific documentation page exists |
| **P3E** | POLICY | No published set of ≥3 working examples |
| **DOC1** | REVIEW-ONLY | No public documentation page *(due by publish date, not submission)* |
| **R11** | REVIEW-ONLY | **1 of 8** public tools exercised end to end |
| **S12** | PORTAL+TERMS | The attestation *"you've run every tool yourself"* **cannot be ticked truthfully**. Under T3, a warranty defect |
| **T9** | TERMS | No mechanism for receiving security-vulnerability reports from **Anthropic and third parties** with a duty of care |
| **A18** ⚠️SILENT | SPEC | None of the eight `oauth_consent_*.html` templates render the redirect URI hostname. `authorize.py:788`'s context omits it. **Not a directory gate** |

---

## 🟡 PARTLY FULFILS (15)

| Row | Gap |
|---|---|
| **P1B** | No code evades guardrails — **but** three descriptions instruct Claude that *"your default behavior is SUSPENDED"*, which is what §1B names |
| **P2A** | Descriptions do state what and when — **but** three bury it under behavioural directives |
| **P2C** | Delete tools **are** deliberately disambiguated (`delete_my_priority_guardian_data` vs MindSort's `delete_my_data`). **But `start_prioritization_flow` and `create_priority` are semantically adjacent** and never evaluated for routing confusion |
| **P2E** | No description interferes with *other software's* tools — **but** several steer away from PG toward other behaviour, unassessed |
| **P3A** | Policy published — **but** still routes PG deletion to `support@priority-guard.com`, and **v3.2 characterises Anthropic as an Art. 28 processor, which is incorrect** |
| **P3H** | Design guidelines largely followed. Terms not yet agreed — no submission made |
| **T3** | No inaccurate information submitted **yet**. The Art. 28 error becomes one the moment the policy link is given |
| **T4** | PG's own policy exists. **Google's third-party policy is not provided**, and PG's policy does not describe what Google collects |
| **M2** | 64 `aria-label`, 24 `role=`, 37 focus rules, 9 keyboard handlers — good. **But 10 of 27 `<svg>` elements carry no `aria-hidden`, `aria-label` or `<title>`** |
| **M3** ⚠️SILENT | `safeAreaInsets` applied only under `platform === 'mobile' && hostFullscreen` (`App.tsx:709`); the inline branch applies none. `.left`/`.right` never read — horizontal padding hardcoded `16px` |
| **M5** | Count right, **placement wrong**: two inline actions, but the refresh button is at the **top** (`TimeAllocationBar.tsx:176`); M5 says actions go at the bottom |
| **M10** | **Inline: compliant** — `max-width` + `width:100%` reflows from 320px. **Fullscreen: not** — `#root`'s 600px cap binds and `margin: 0 auto` produces the side margins M10 names. Four layered caps; the two 672px ones are **dead** |
| **M20** | Loading states exist (`App.tsx:537-548`, `isLoading` in components) but are **text, not skeleton screens** |
| **X6** | `resourceDomains: ["https://assets.claude.ai"]` on all three blocks — **and no `--font-*` token is referenced anywhere in the widget**. CSP widened for a capability not exercised |

---

## ✅ FULFILS (50)

**Authentication — verified live, 2026-08-05**

| Row | Evidence |
|---|---|
| A1, A2 | AS metadata: `code_challenge_methods_supported: ["S256"]` |
| A3 | `HTTP/2 401` + `WWW-Authenticate: Bearer resource_metadata="…", scope="pg.access"` |
| A4 | PRM `resource: https://mcp.priority-guard.com/mcp` — exact match |
| A5 | `authorization_servers: ["https://www.priority-guard.com"]` — single entry |
| A6 | RFC 8414 metadata served; `issuer` = root domain |
| A8 | `config.py:62-63` registers both `claude.ai` and `claude.com` |
| A9 | Validator run against Claude Code's **published CIMD** — both URIs accepted, port-agnostic, negative controls rejected |
| A10 | Live: `invalid_grant` returned |
| A11 | `token_service.py` revokes the old token in the same exchange |
| A12 | Live: form-urlencoded → **400, not 415** |
| A13 | Live: JSON → `422 grant_type: Field required` — parser split confirmed |
| A15 | No `client_credentials` implemented |
| A16 | Bearer header only |
| A22 ⚠️SILENT | Transport-level 401, not `200 + isError` |
| A23 | `scope="pg.access"` on the 401 |
| A24 | DCR supported and working |

**Policy** — P1D *(`record_widget_diagnostic` is `private`, never served to Claude, never called by
PG-Claude)* · P1F *(pattern-searched `mcp_server/**/*.py` + `backend/**/*.py` for memory/history/
summary/user-file identifiers → **0 matches**)* · P2F · P2G · P3F · **P4A, P4B, P4C**
*(pattern-searched all three trees for payment, crypto, image-generation and advertising
identifiers → **no matches**)* · **P5A** *(read `_build_provenance_error`: structured `isError` with
an error code and actionable guidance, not a generic failure)* · P5C *(**8/8**, longest served name
32 of 64)* · P5D · P5E *(**8/8** carry `title` + a hint; `title` is a required positional field, and
`create_priority` is overridden to `destructiveHint: true` at `tools_list_dupl.py:57`)* · R1

**Design & widget** — M4 ⚠️SILENT · **M7** *(no menus or popovers anywhere; `KeywordPicker.tsx:20`
comments "Confirmation is inline (no modal/popover) per MCP Apps guidelines")* · **M9** *(explicit
`44px` on `DeliverableItem`/`GoalItem` action buttons; shared `Button.tsx` reaches 44px by
arithmetic — `16+16+12`, `15+15+14` — deliberate but not a declared floor)* · M11 · M12 · M14 ·
M15 · **M16** *(the only `<textarea>` is `AddPriorityForm.tsx:437`, a priority-entry field — not a
chat input)* · M17 · **M19** *(zero emoji across `widget-react/src`; icons are SVG)*

**M1 / M18** ✅ **— revised UP on the full read.** 24 bare hex literals exist, and **22 are
documented product identity.** `constants.ts` states it outright: *"Priority identity colors —
semantic product colors, not host theme tokens… intentionally fixed."* `PieChart.tsx:44-46` adds
*"Data-viz accent colors — no official solid tokens exist for pie chart fills"*, which is true.
**M18 explicitly permits brand colours for accents and identity**, and `BAR_COLORS.other` uses
`var(--color-text-tertiary, …)` — proof the structural/identity line was drawn deliberately rather
than missed. ⚠️ **Two narrow exceptions remain outside that rationale:** `GoalItem.tsx:330`
`color: '#fff'` on an SVG checkmark, and `KeywordPicker.tsx:230` `?? '#fff'` — both plain
structural white, not P1/P2/P3 identity.

**Domain, CSP, theming** — X1 · X2 ⚠️SILENT · X4 ⚠️SILENT *(`main.css:8-15`)* · X5 · X8 ·
X9 ⚠️SILENT

**External links** — L1 · L2 ⚠️SILENT *(target is `BACKEND_PUBLIC_URL` = `www.priority-guard.com`,
a domain PG owns — **not** `accounts.google.com`)* · L8

**Submission** — S3 · S4 · S13

---

## ➖ NOT RELEVANT (17)

Local connectors: **P5G, S15, S16** · Plugins: **S10** · MCPB: **S11** · Custom query tools:
**R2** · Microsoft Entra: **A20** · `oauth_anthropic_creds`: **A21** · Claude's own CIMD selection
logic: **A17** · Carousels: **M13** · stdio: **X3** · Custom URI schemes: **L4** ·
Post-publication: **PUB1–PUB4** · Slug: **S6** ⚠️SILENT

---

## ❔ DON'T KNOW (37)

**Needs a decision or artefact from Nadja (13)** — P1A *(the four §1A documents are uncaptured)* ·
P1C *(third-party calendar data; three retention models exist and which governs is unresolved)* ·
P1E · P3B · P3D, P3D-i · P3G · T1, T2, T5, T6, T7, T8, T10

**Needs a measurement (7)** — A7 *(egress reachability)* · A14 *(10 s/30 s under load)* · P5B
*(token frugality — no measurement, and no user option to exclude text)* · P5F *(transport)* · R7a ·
X7 ⚠️ *(`onhostcontextchanged` is assigned inside `onAppCreated` at `App.tsx:144`; whether that
fires before `connect()` is SDK internals)* · L3 *(confirm the live `BACKEND_PUBLIC_URL`)*

**Depends on the submission (9)** — **S1** *(**no Team/Enterprise org** — blocks submission
outright; a plan decision, not a compliance failure)* · S2 · S5 · S7 · S8 · S9 · S14 + P3H, T3/T4
*(partly, above)*

**Rests on a source nobody has confirmed is current (8)** — L5, L7 *(`external-links`, no
artifact)* · R1, R2, R6a, R7a, R11, DOC1, S10, S11 *(`review-criteria`, fetch-only and undated)*

---

## The three requirements not yet rows

| Requirement | PG | Note |
|---|---|---|
| **`ui/open-link` bypasses the modal only after a real user gesture** | ✅ **Fulfils** | `ConnectionStatus.tsx:40` `handleConnect` is bound to `onClick` at `:247`; `openLink` called inside at `:64`. A genuine click |
| **Non-zero iframe height** | ❔ | Host-controlled; not observable from the repo |
| **iOS: allowlist on `Origin`, not `Referer`** | ❔ | No `Referer` gating in `backend/` — the good sign — but the CDN/WAF layer was not inspected |

---

## Priority order

1. **S1 — no Team/Enterprise org.** Blocks submission outright. A purchase decision, not engineering.
2. **M6 — the missing `.slice()`.** Smallest fix on the list, and a reviewer with a populated test account sees it immediately.
3. **R6a + P2B + P1B** — one edit surface, three failures. ⚠️ **Descriptions are shared with the live ChatGPT app.**
4. **R11 / S12** — eight tools through the Inspector. **Not gated by S1**; any account can add a custom connector.
5. **T9 and the Art. 28 correction** — both small, both warranty-relevant.
6. **M10 fullscreen, M3 safe areas** — ⚠️SILENT rows that break with no error.

---

## End-to-end read — what the full sweep added

**All 6,724 lines of `widget-react/src` covered.** Four findings the row-driven passes missed:

**1. P1D is stronger than "no violation evidenced" — the widget collects and stores nothing.**
Pattern-searched the whole tree: **no** analytics, telemetry, `gtag`, mixpanel, posthog or sentry ·
**no `localStorage`, `sessionStorage` or `document.cookie`** · **no `fetch`, `XMLHttpRequest` or
`axios`** — every call goes through the MCP bridge · **no** `navigator.*`, `window.location` or
`document.referrer`. For a §1D/§1F assessment that is close to the strongest possible result.

**2. The absence of `localStorage` corroborates the `ui.domain` record.** §4M's caching
optimisation is keyed on `toolInfo.id` and needs storage; PG uses none, so the *only* live reason
for the fixed domain is the widget's own OAuth flow — which is exactly what the decision record
says. Two independent lines of evidence now agree.

**3. M5, refined.** Per card the inline surface has **one** action — the deliverables/goals expand
toggle (`DeadlineCard.tsx:287`, `FlexibleCard.tsx:206`) — which satisfies "max 2". The **aggregate**
inline response has `2 + N` interactive elements (refresh, expand-to-fullscreen, one toggle per
card). Whether M5's "card" means each card or the whole inline response decides this; the row stays
🟡 on that ambiguity, not on a count.

**4. `FlexibleCard` and `GoalSection` carry zero bare hex and full `isInline` display-only guards**
— the same discipline as `DeadlineCard`. `i18n.ts` is 434 lines of static `en`/`de` strings with no
data access.

**Unchanged by any code reading: the 37 don't-knows.** They are questions about conduct, published
artefacts and measurements — not about the codebase.
