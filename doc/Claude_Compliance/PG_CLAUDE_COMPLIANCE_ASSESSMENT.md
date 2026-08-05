# PG-Claude — Compliance Assessment

**Assessed:** 2026-08-05 · **Against:** `CLAUDE_COMPLIANCE_REQUIREMENTS_CANONICAL.md`, 129 rows
**Surface:** the Claude serving path. Not ChatGPT. Not MindSort.

| Verdict | Count |
|---|---|
| ✅ **Fulfils** | **59** |
| 🟡 **Partly fulfils** | **13** |
| ❌ **Doesn't fulfil** | **4** |
| ➖ **Not relevant** | **17** |
| ❔ **Don't know** | **36** |

> ## ⚠️ Every row now carries a VERDICT SOURCE
>
> | Source | Meaning |
> |---|---|
> | **`code`** | Settleable by reading the repository or probing the live service |
> | **`conduct — Nadja`** | Something done, prepared or agreed. **Invisible to a codebase read** |
> | **`conduct — published artefact`** | Something published outside the repo |
>
> **A row not marked `code` is not the code session's to resolve.**

> ## The correction that produced this column
>
> **Six of ten `❌` verdicts in the first version were manufactured** — R11, S12, T9, P3C, P3E,
> DOC1. Every one had a **conduct** subject: testing performed, accounts prepared, pages published,
> addresses monitored. **"Not in the repo" was reported as "not done."**
>
> That is standing check #2 — *state the scope a negative was proved over* — applied to a whole
> class of rows. The claim proved was about the repository; the claim written was about the
> product. **All six were already satisfied.** Each competed for attention against roughly four
> weeks of runway.

---

## ❌ DOESN'T FULFIL (4) — and none is a pre-submission blocker

| Row | Source | Status |
|---|---|---|
| **M5 + M6** | `code` | **One finding, not two: inline card density.** `App.tsx:662` maps `sortedPriorities` with no `.slice()` — confirmed. **But capping the list alone does not fix it**: the inline card also renders `TimeAllocationBar`, `CalendarConnectionMinimal`, `ExpandButton` and a hint line. M6 (4–5 data points) and M5 (2 actions, at the bottom) govern the same surface. **A product decision about what the inline card shows, not a one-line fix** |
| **P2B** | `code` | `inspect_adapt` advertises persistence it lacks. **A real Policy §2B violation** — POLICY level, binding. **Blocked by the standing rule: tool descriptions are shared with the live ChatGPT app and are not touched.** Recorded, not actioned |
| **R6a** | `code` ⚠️ **CONTESTED** | Override language in three descriptions. ⚠️ **Sourced from `review-criteria` — `[fetch-only]`, undated, uncorroborated, the weakest source in the canonical file.** The **binding** Policy §2 contains **no clause prohibiting behavioural guidance**; §2G *presupposes it exists* and regulates its form — *"All behavioral guidance must be human-readable and clearly presented"* — **which PG satisfies.** ⚠️ **Severity asymmetry: P2B is a binding POLICY violation; R6a rests on an uncorroborated reviewer-facing page. Do not treat them as equivalent** |
| **A18** ⚠️SILENT | `code` | Consent screen omits the redirect URI hostname. `SPEC` level — absent from **both** the reviewer checklist and the binding policy. **Not a directory gate.** Post-submission |

### Deferred by decision — not a failure, not an open task

**S1 — no Team/Enterprise organisation.** The portal requires one. **Deferred deliberately**: the
seat is purchased at submission time to preserve Max-plan capacity until then. Team floor is
**2 seats, €21.04/seat/month billed monthly + VAT.**

---

## ✅ THE SIX CORRECTIONS

| Row | Source | Evidence |
|---|---|---|
| **R11** | `conduct — Nadja` | PG-Claude added and used as a custom connector. `testing.raw.md:13`: *"Any Claude account… can add a custom connector… Custom connectors use the exact same runtime as directory connectors."* **Never gated by S1** |
| **S12** | `conduct — Nadja` | Populated test account and step-by-step setup instructions exist |
| **T9** | `conduct — published artefact` | Terms require *"a mechanism for receiving reports of security vulnerabilities from Anthropic and from third parties."* `support@priority-guard.com` is published with a stated 24-hour response. **A monitored published address is a mechanism.** ⚠️ *The `security.txt` / triage-SLA framing in the first version was invented — it appears nowhere in the source* |
| **P3C** | `conduct — published artefact` | `fulfilling-productivity.com/priority-guardian-mcp` — three-step getting started, how-it-works covering both priority modes, requirements, **five troubleshooting entries with causes and fixes** |
| **P3E** | `conduct — published artefact` | **Six** worked prompts on that page (§3E requires three) |
| **DOC1** | `conduct — published artefact` | Same page. Public, and `noindex` has been removed |

**Also corrected:** **P3A** 🟡→✅ *(privacy policy linked EN + DE, ToS linked — the Art. 28 accuracy
defect belongs under T3/T4, not here)* · **P3B** ❔→✅ *(`support@priority-guard.com` published with
a response commitment)*.

**Copy nits, not compliance:** the page footer reads *"Last Updated: May 2026"*; and the
troubleshooting entry *"Claude-connected accounts are tied to your session"* sits directly under a
sentence saying data is stored persistently — a reviewer testing on two devices may read the pair
as a contradiction.

---

## 🟡 PARTLY FULFILS (13)

| Row | Source | Gap |
|---|---|---|
| **P1B** | `code` | Override language is itself what §1B names ⚠️ *inherits R6a's contested basis* |
| **P2A** | `code` | Three descriptions bury what/when under directives |
| **P2C** | `code` | Delete tools disambiguated; `start_prioritization_flow` vs `create_priority` unassessed |
| **P2E** | `code` | Descriptions steer away from PG, unassessed |
| **T3** | `conduct` | **The Art. 28 characterisation of Anthropic is incorrect** — becomes inaccurate information the moment the policy is submitted |
| **T4** | `conduct` | **Google's third-party policy is not provided**, and PG's policy does not describe what Google collects |
| **P3H** | `conduct` | Terms not yet agreed — no submission made |
| **M2** | `code` | 10 of 27 `<svg>` elements carry no `aria-hidden`/`aria-label`/`<title>` |
| **M3** ⚠️SILENT | `code` | `safeAreaInsets` only under `mobile && hostFullscreen`; `.left`/`.right` never read |
| **M10** | `code` | Compliant inline; **in fullscreen** `#root`'s 600px cap + auto margins produce the side margins M10 names |
| **M20** | `code` | Text loading states, not skeleton screens |
| **X6** | `code` | CSP widened for host fonts the widget never consumes |
| **M1/M18** | `code` | ✅ in substance — 22 of 24 bare hex are **documented product identity**, which M18 permits. Two structural exceptions: `GoalItem.tsx:330`, `KeywordPicker.tsx:230` |

---

## ✅ FULFILS (59) — evidence classes

**Auth, verified live** — A1–A6, A8–A13, A15, A16, A22, A23, A24. 401 + `scope`, PRM exact match,
single AS, S256, `invalid_grant`, form-urlencoded **400 not 415**, JSON rejected, loopback validated
against Claude Code's **published CIMD** with negative controls holding.

**Code, verified by reading** — P1D, P1F, P2F, P2G, P3F, P4A–C, P5A, P5C, P5D, P5E, R1, M4, M7, M9,
M11, M12, M14–M17, M19, X1, X2, X4, X5, X8, X9, L1, L2, L8, S3, S4, S13.

**Conduct, confirmed by Nadja / published artefact** — R11, S12, T9, P3A, P3B, P3C, P3E, DOC1.

**Standout:** the widget **collects and stores nothing** — no analytics/telemetry/sentry, no
`localStorage`/`sessionStorage`/cookies, no `fetch`/XHR/axios (everything via the MCP bridge), no
`navigator.*`/`location`/`referrer`. And **zero emoji**: icons are SVG.

---

## ❔ DON'T KNOW (36) — re-triaged by who holds the evidence

### `conduct — Nadja` (16) — **not resolvable from this session. Likely most are already satisfied.**

| Rows | What would settle it |
|---|---|
| **P3D, P3D-i** | Test account with sample data + setup instructions. ⚠️ **Probably already ✅** — S12's evidence covers both |
| **P1A** | Confirmation that PG does not violate the Usage Policy, Universal Usage Standards, High-Risk Use Case requirements or the supported-countries policy. **All four documents are uncaptured** |
| **P1C** | Which retention model governs third-party calendar data — three versions exist |
| **P1E** | IP position |
| **P3G** | Maintenance and issue-response practice |
| **T1, T2, T5, T6, T7, T8, T10** | Legal and organisational commitments accepted at submission |
| **S1, S2** | The org purchase and Owner role |

### `code` (7) — **mine, and unresolved**

| Row | What would settle it |
|---|---|
| **A7** | Traffic originating from `160.79.104.0/21` — **impossible from here.** Circumstantially satisfied: the connector works |
| **A14** | Latency measurement under load |
| **P5B** | Token cost per tool against task complexity, and whether users can exclude text |
| **P5F** | Whether PG serves Streamable HTTP or SSE — **one probe, not yet run** |
| **R7a** | Every tool returning a successful response with valid parameters |
| **X7** ⚠️ | Whether `onAppCreated` fires before `connect()` — SDK internals |
| **L3** | The live `BACKEND_PUBLIC_URL` value before the portal is filled |

### `conduct — submission-time` (5)

**S5, S7, S8, S9, S14** — listing copy, screenshots, acknowledgments, data-handling declarations.
Answered by filling the portal.

### Rests on an unconfirmed source (8)

**L5, L7** *(`external-links`, no artifact)* · **R2, R6a, R7a, R11, DOC1, S10, S11**
*(`review-criteria`, fetch-only and undated)*. Verdicts hold against the bytes we have; **the
bytes' currency is unverified.**

---

## Where things actually stand

**No remaining pre-submission blocker except the Team seat, which is deferred by decision.**

| Item | Nature |
|---|---|
| **M5 + M6** inline density | Product decision |
| **P2B** | Real §2B violation, **blocked by the do-not-touch-descriptions rule** |
| **R6a** | Contested, weakest source, binding policy does not support it |
| **A18** | Post-submission, not a gate |
| **T3/T4** Art. 28 + Google policy | Small, warranty-relevant, worth doing before the portal |

**Still open from earlier:** the three `[relay-only]` pastes.
**Already done, contrary to the review's list:** the `COMPLIANCE_AUDIT_RECORD.md` citation sweep —
run in `62f897c`, recorded in that file: 14 citations, 12 clean, 2 false positives.
