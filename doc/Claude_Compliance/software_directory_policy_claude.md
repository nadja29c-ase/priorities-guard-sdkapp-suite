# Anthropic Software Directory Policy — the binding document

**Source:** `https://support.claude.com/en/articles/13145358-anthropic-software-directory-policy`
**Fetched:** 2026-08-04 — direct fetch. **The `.md` suffix works on `support.claude.com` too.**
**Raw source committed:** `sources_raw/software-directory-policy.raw.md` (80 lines, HTTP 200, 7,458 bytes).
**Feeds:** compliance master §4A/§4B/§4F/§5E and the submission checklist.

> ⚠️ **PROVENANCE: FETCH-ONLY** (Option B). Not paste-corroborated. Usable, labelled unverified for
> currency. See `sources_raw/PROVENANCE.md`.

**This is the legal text `review-criteria` points at.** `review-criteria` is the reviewer's
checklist; **this is the obligation.** Where they differ, this governs.

---

## Headline 1 — A18 is RESOLVED. It is not a directory criterion.

**§5D is the only authentication clause in the entire policy:**

> **D.** Remote MCP servers that connect to a remote service and require authentication must use
> **secure OAuth 2.0 with certificates from recognized authorities.**

That is **TLS certificates from recognised CAs, plus OAuth 2.0**. It does **not** incorporate the
MCP spec's consent-screen display requirement, and grep for `consent` / `redirect` across the whole
policy returns **that one line and nothing else.**

**Both authorities are now checked and both are silent:** the reviewer checklist
(`review-criteria`) and the binding policy (this page).

**A18's final label: unmet spec-inherited MUST. NOT a directory criterion. Post-submission.**
It remains a real security control worth fixing — the consent screen is still the only place a
user sees where their authorization is going — but it blocks nothing.

## Headline 2 — Blocker 1's obligation set, from the binding document

**No seven-section requirement exists here.** The full documentation obligation is four clauses:

| § | Requirement |
|---|---|
| **3A** | Privacy policy link — *"clear, accessible"*, explaining collection, usage **and retention**; links provided to Anthropic; presented to users as required by law |
| **3B** | **Verified** contact information **and** support channels, for product **and security** concerns |
| **3C** | Document **how the Software works, its intended purpose, and how users can troubleshoot issues** |
| **3E** | **At least three working examples** of prompts or use cases demonstrating core functionality |

Plus `review-criteria`: a **public page by publish date**, blog post or help-centre article
sufficient, shareable privately during review.

**§3E confirms the three examples are genuinely required** — that half of the earlier figure was
right. **The "seven sections" half is confirmed as an inflation**: it appears nowhere in the
binding policy, and the source it came from says *"Recommended sections."*

**One addition nobody has listed: §3D** — *"a standard testing account with sample data for
Anthropic to verify full Software functionality."* `review-criteria` says "fully populated
account"; **the policy adds "sample data"**, which is a content obligation, not just an access one.

---

## Part 1 — Requirements (28)

### §1 Safety and Security

| # | Requirement |
|---|---|
| P1A | No Usage Policy violation; comply with Universal Usage Standards, High-Risk Use Case requirements, and supported-countries policy |
| P1B | Must not evade or let users circumvent Claude's safety guardrails, system instructions, or sandbox |
| P1C | Must prioritise user **and third-party** privacy; responsible handling of personal/sensitive data; legal compliance |
| **P1D** | **Collect only data from the user's context necessary to function. Must NOT collect extraneous conversation data, EVEN FOR LOGGING PURPOSES** |
| P1E | No IP infringement |
| **P1F** | **Must not query or extract from Claude's memory, chat history, conversation summaries, or user-generated/uploaded files** |

### §2 Compatibility — "Instructional Software" (this includes MCP servers)

| # | Requirement |
|---|---|
| P2A | Define each tool through **narrow, unambiguous** natural language: what it does **and when it should be invoked** |
| P2B | Descriptions must **precisely match actual functionality**; no unexpected functionality, no promising undelivered features |
| **P2C** | **Descriptions must not create confusion or conflict with OTHER Software in the Directories** |
| P2D | Must not call or coerce Claude into calling other external software unless the user requested it; **descriptions must not be written so as to lead other Software to call them extraneously** |
| P2E | Must not interfere with Claude calling tools from other software |
| P2F | Must not direct Claude to dynamically pull behavioural instructions from external sources |
| P2G | No hidden, obfuscated or encoded instructions; **all behavioural guidance human-readable and clearly presented** |

### §3 Developer Requirements

| # | Requirement |
|---|---|
| P3A–P3E | See Headline 2 |
| P3F | Must **verify ownership or control** of any API endpoint, domain, or UI the Software connects to, **and any external resources it retrieves or renders** |
| P3G | Maintain the Software and address issues within reasonable timeframes |
| P3H | Agree to the Software Directory Terms **and follow design guidelines Anthropic publishes** |

### §4 Unsupported Use Cases

| # | Not allowed |
|---|---|
| P4A | Transferring money/crypto/financial assets, or executing financial transactions on a user's behalf |
| P4B | AI-generated images/video/audio. **Design-focused visual aids are permitted** (slides, diagrams, charts, UI mockups, logos) *"provided the developer does not offer standalone image generation as a primary service"* |
| **P4C** | **Advertisements, sponsored content, paid product placements, or existing primarily as an advertising/promotional vehicle** |

### §5 Additional Requirements for MCP Servers

| # | Requirement |
|---|---|
| P5A | Must **gracefully handle errors** and provide helpful feedback rather than generic error messages |
| **P5B** | **Must be FRUGAL WITH TOKENS** — usage roughly commensurate with task complexity or impact; *"where possible, users should be given options to exclude unnecessary text in the response"* |
| P5C | Tool names ≤ **64 characters** |
| P5D | Remote servers requiring auth must use **secure OAuth 2.0 with certificates from recognized authorities** |
| **P5E** | **Must provide all applicable annotations, in particular `readOnlyHint`, `destructiveHint`, and `title`** |
| P5F | **Should** support **Streamable HTTP**. SSE tolerated *"for the time being"*, **to be deprecated** |
| P5G | Local servers: reasonably current dependency versions (n/a — PG is remote) |

---

## Part 2 — What is NEW here, absent from `review-criteria`

| # | Why it matters |
|---|---|
| **P5B — token frugality** | **A hard MUST that appears on no other page.** It also carries a design obligation: *give users options to exclude unnecessary text.* PG returns full dashboards from `get_priorities` and `render_weekly_report`. **Not assessed** |
| **P4C — no advertising** | `review-criteria`'s unsupported list has only money and AI media. The policy adds advertising. PG is unaffected |
| **P2C — no conflict with OTHER Software** | A cross-connector obligation. **Directly relevant**: PG and MindSort are two connectors from the same developer with adjacent purposes (priorities vs. thought organisation). Worth a description-conflict read |
| **P5F — Streamable HTTP, SSE deprecating** | Forward-looking transport obligation, absent from every other page |
| **P3F — verify ownership of rendered external resources** | Broader than `review-criteria`'s R8: it covers what the Software **retrieves or renders**, not just APIs it calls. Touches `resourceDomains` and `ui/open-link` targets |
| **P3D — "sample data"** | `review-criteria` says "fully populated account"; the policy makes the data itself the obligation |
| **P1C — third-party privacy** | PG ingests **calendar events containing other people's names and meeting titles**. This is the clause that covers them, and no other page states it |
| **§3 ongoing review** | *"We conduct both initial and ongoing reviews… All Software must maintain compliance with these requirements, **including any future changes**"* — compliance is continuing, not a one-time gate |

---

## Part 3 — PG conformance: what is already answered, and what is not

### Already verified elsewhere in this audit

| # | PG | Evidence |
|---|---|---|
| P5C | ✅ | Longest served name 32 of 64 (`review_criteria_claude.md`) |
| P5E | ✅ | **This is the §5E the code comments cite.** `title` structurally guaranteed on the `ToolDefinition` dataclass; `create_priority` overridden to `destructiveHint: true` for Claude in `tools_list_dupl.py` |
| P5D | ✅ | OAuth 2.0 with PKCE S256, TLS on `mcp.priority-guard.com` and `www.priority-guard.com` |
| P1F | ✅ | PG queries no Claude memory, chat history, summaries or user files |
| P4A/P4B/P4C | ✅ | No financial transfer, no AI media generation, no advertising |
| P3A | ⚠️ | Privacy policy is published, **but still routes PG full deletion to `support@priority-guard.com`** — wrong once the deletion tool ships. Part D of the deletion increment |

### NOT assessed — stated rather than assumed

| # | What a real check requires |
|---|---|
| **P5B** | Measure token cost per tool against task complexity, and decide whether users can exclude unnecessary response text. **No such measurement exists** |
| **P2C** | Cross-connector conflict (PG vs MindSort) — **still not assessed** |

### ⚠️ §2B / §2D–§2G — FIRST PASS DONE 2026-08-04. Two concrete defects, one of them serious.

#### 1. `inspect_adapt` — a §2B violation, and the annotation is NOT the thing to change

| | |
|---|---|
| **Served description** | *"**Record** confirmed action steps from an inspect & adapt reflection."* |
| **Annotation** | `read_only_hint=True`, commented *"No persistence, pure conversational shaping"* |

**Resolved by reading the handler, not by guessing** — the `create_priority` retraction is why.
`mcp_server/priority_guardian/tools/inspect_adapt.py` is 332 lines and contains **zero**
`backend_post` / `backend_get` / `backend_put` / `backend_delete` calls. Its handler docstring
states outright: *"Single-call tool: validate provenance → return success."*

**Verdict: the annotation is correct and the DESCRIPTION is the defect.** The tool advertises that
it *records* action steps and persists nothing — §2B: *"descriptions must precisely match actual
functionality… must not include unexpected functionality or **promise undelivered features**."*
This is a promised undelivered feature, sitting next to a `readOnlyHint` that contradicts its own
verb. A reviewer checking annotations against descriptions hits it immediately, and annotations are
the largest rejection category.

**Fix: rewrite the description to say what it does** — validates and confirms reflection provenance,
shapes the conversation, persists nothing. **Do not touch the annotation.**

#### 2. THREE descriptions attempt to override Claude's default behaviour — §2D–§2G / R6

The enumerated rejection class includes descriptions that *"tell Claude to behave in ways unrelated
to the tool's function, **attempt to override system instructions**"*, and the page's summary rule
is blunt: ***"Describe what the tool does. Do not tell Claude how to behave."***

| Tool | chars | Override markers present |
|---|---|---|
| **`create_priority`** | 2057 | `BINDING RULES`, `SUSPENDED`, `default behavior`, `NEVER`, `DO NOT` |
| **`inspect_adapt`** | 1462 | `BINDING RULES`, `SUSPENDED`, `FORBIDDEN`, `Override`, `impulses`, `default behavior` |
| **`onboarding_calendar_setup`** | 1902 | `BINDING RULES`, `SUSPENDED`, `default behavior`, `ALWAYS`, `NEVER` |

Representative, from `inspect_adapt`:

> *"INSPECT & ADAPT BINDING RULES: … **your default behavior is SUSPENDED**, no advisory mode
> allowed. … **FORBIDDEN**: diagnosing root causes, teaching frameworks … **Override analytical
> coaching impulses**"*

*"Your default behavior is SUSPENDED"* and *"Override analytical coaching impulses"* are not
descriptions of a tool. They are instructions to the model about how to behave, which is the
rejection class stated verbatim.

**The other five are clean.** `delete_my_priority_guardian_data`, `get_patterns`, `get_priorities`,
`get_priority_events` and `render_weekly_report` carry only *"Do NOT call this tool: …"* — routing
guidance **about that tool**, which is exactly what §2A asks for (*"specifies what it does and when
it should be invoked"*). **The distinction is not the word "NOT" — it is whether the sentence
describes invocation conditions or reassigns the model's behaviour.**

⚠️ **This is the highest rejection risk found in the audit**, and it was invisible from the code
side because the annotations are all correct. **Not fixed — the descriptions are behavioural
product design and rewriting them is Nadja's call.** An `ASSISTANT_GUIDANCE` block was already
removed from the deletion tool on the same grounds, so the pattern is known.

#### 3. Cosmetic, but reviewer-visible

`get_priorities`: *"…and their progress.**C**all this tool…"* — missing space after the period,
from string concatenation in `DESCRIPTION`. It appears in the directory listing and the portal's
Tools step.
| **P1D** | Applies to `record_widget_diagnostic`'s open `data` object. Assessed as *no violation evidenced*; call-site enumeration still not done |
| **P1C** | Third-party calendar data. The retention model covers it, but the **three-versions problem** (open task #11) means it is unclear which model governs |
| **P3B** | Whether the published contact information meets *"verified"* |
| **P5F** | Whether PG serves Streamable HTTP or SSE — **not checked** |
