# Pre-submission checklist — what Anthropic reviewers test

**Source:** `https://claude.com/docs/connectors/building/review-criteria`
**Fetched:** 2026-08-04 — direct fetch.
**Raw source committed:** `sources_raw/review-criteria.raw.md` (78 lines, HTTP 200, 5,421 bytes).
**Feeds:** compliance master §4A/§4B/§5E and the submission checklist. Master **not** yet rewritten.

**Method:** read for obligations, not keywords. This page is short and almost entirely obligation —
the opposite of `instance-supersession`.

---

## The headline: this page **resolves A18's gating status**

**A18 is NOT an enumerated directory criterion.** Grep for `consent` and `redirect` across the raw
source returns **nothing**. The page never mentions consent screens, redirect URIs, or authorization
server UI.

So the label stands as written in §4C: **unmet spec-inherited MUST, not a directory gate.** It does
not have to ship before submission. It should still be fixed — it is a real security control — but
it is now correctly sized as post-submission work rather than a blocker.

## Second headline: Blocker 1 is smaller than we have been sizing it

The public-documentation requirement, verbatim (raw 72):

> **Public documentation** is required by your publish date — **a blog post or help-center article
> is sufficient**. You can share docs privately with Anthropic during review.

Two things follow. **"By your publish date"**, not by submission. And **"a blog post or help-center
article is sufficient"** — no section count, no worked-example count, no structure prescribed.

⚠️ **The "seven required sections, three usage examples" figure does not come from this page.** It
must originate on `submission` or `software_directory_policy`, both unfetched. **Do not size
Blocker 1 from that figure until one of those pages is confirmed as its source** — on current
evidence the reviewer-facing bar is a blog post.

---

## Part 1 — Requirements extracted (11)

### Framing (raw 9) — applies to everything below

Submission triggers an **automatic policy scan**. Default listing is as a **community connector**.
Anthropic **may** escalate listings flagged as highly useful to **verified review** (higher touch,
slower — *"reviewers run a functional test of each tool"*). Escalation is **automatic; you do not
need to take any action.**

> **"Every server in the directory must meet the criteria on this page, whichever label it
> carries."** The label is a quality signal to users; it does not change how the connector runs.

| # | Requirement | Language | Raw |
|---|---|---|---|
| R1 | **Separate read and write tools.** A single tool accepting both safe (GET/HEAD/OPTIONS) and unsafe (POST/PUT/PATCH/DELETE) methods is **rejected**. No catch-all `api_request` with a `method` parameter. Ideally split writes further by action type. **Documenting safe vs unsafe inside one description does NOT satisfy this — they must be separate tools** | "is rejected" | 15–17 |
| R2 | **Custom query tools must name their API.** If a tool accepts freeform endpoint paths, query strings or request bodies **constructed by the caller**, its description **must** link to or explicitly name the target API. *"Makes a request to the API"* fails. **Conditional** — purpose-built tools calling a fixed endpoint internally are exempt | "must include" | 19–23 |
| R3 | **Every tool must include a `title` and the applicable hint** — `readOnlyHint: true` for read-only, `destructiveHint: true` for tools that modify or delete data. These **determine auto-permissions**: read-only runs without per-call confirmation, destructive always prompts | "must include" | 25–27 |
| R4 | **Tool names ≤ 64 characters** | "must be" | 29–31 |
| R5 | **Descriptions must match actual behaviour** — state precisely what the tool does and when to invoke it | "must match" | 33–35 |
| R6 | **No prompt-injection patterns.** Descriptions are **rejected** if they: instruct Claude to call external software the user didn't request · interfere with Claude calling other tools · direct Claude to pull behavioural instructions from external sources · contain hidden/obfuscated/encoded instructions · tell Claude to behave in ways unrelated to the tool's function, override system instructions, or promote products. *"Describe what the tool does. Do not tell Claude how to behave."* | "are rejected" | 37–47 |
| R7 | **Functional quality (five parts).** Every tool must return a **successful response** with valid parameters — generic errors ("Internal Server Error", "Bad Request" with no detail) **fail review** · validate inputs and return **actionable** errors · keep responses reasonably sized · **do not collect conversation data beyond what the tool needs** · **do not query Claude's memory, chat history, conversation summaries, or user files** | "must" / "Do not" | 49–55 |
| R8 | **API ownership.** The server must call **your own first-party APIs**, or APIs you legitimately proxy. *"The MCP server domain should match your service."* | "must call" | 57–59 |
| R9 | **Unsupported use cases — not accepted:** transferring money, cryptocurrency or financial assets; generating images/video/audio via AI models (diagram/chart/UI-mockup design tools **are** allowed) | "are not accepted" | 61–66 |
| R10 | **Submission requirements.** Test credentials **required**, and must be a **fully populated account** · Allowed link URIs **recommended** if the server calls `ui/open-link` · Public documentation **required by publish date** (blog post or help-centre article sufficient; may be shared privately during review) · Plugins must link a **public** GitHub repo, closed-source not accepted · MCPB open-source and "spec will evolve" clauses **required and not waivable** | mixed — see cells | 68–74 |
| R11 | **Before you submit:** exercise **every** tool through the MCP Inspector **and** as a custom connector in Claude (`claude plugin validate` for plugins) | imperative | 76–78 |

---

## Part 2 — PG-Claude conformance

**PG exposes 20 tools in the registry, of which 8 are `public`** (LLM-visible); the other 12 are
`private` (widget-only, filtered at `tools_list_dupl.py:37`).

### R3 / R4 — verified by extracting every `ToolDefinition`

| Check | Result |
|---|---|
| Every tool has a `title` | ✅ **20/20** |
| Tool name ≤ 64 chars | ✅ **20/20** — longest is `delete_my_priority_guardian_data` at **32** |

`title` is **structurally guaranteed**: it is a **required positional field** on the
`ToolDefinition` dataclass (`tools/base.py`, `title: str` with no default), so a tool cannot be
constructed without one. The docstring already cites *"required by Anthropic §5E"*.

> ⚠️ **A near-miss worth recording.** A first pass scanned for `^TITLE = "…"` module constants,
> found none, and was about to report **"20 tools missing title."** That is the **exact claim
> `doc/README.md` records as a fabrication** (*"All 17 tools lack `title` — required code fix"*),
> caught only because the README documents it. The scan's pattern silently excluded the answer:
> titles are `title=` kwargs in the `ToolDefinition(...)` call, not module constants. **Third
> application of the negative-claim scope rule in one session** — and the first where the rule
> prevented re-publishing a known-false claim rather than catching one after the fact.

### R3 — two tools carry neither hint ⚠️

| Tool | Visibility | `readOnlyHint` | `destructiveHint` |
|---|---|---|---|
| `create_priority` | **public** | False | False |
| `record_widget_diagnostic` | private | False | False |

**Defensible, not clearly compliant.** R3 requires *"the applicable hint"* — `readOnlyHint` for
read-only, `destructiveHint` for tools that **"modify or delete data."** A pure create does
neither, so arguably neither hint applies and the requirement is satisfied vacuously.

**Risk if a reviewer reads it the other way:** `create_priority` is public and writes data. The
consequence of the current setting is only that it **prompts** (no hint ⇒ no auto-permission), so
there is **no security exposure** — the exposure is a reviewer judgement call.
`record_widget_diagnostic` is private and filtered from the public list, so it is unlikely to be
seen at all. **Flagged for Nadja's decision; no code change made.**

### R1, R2, R8, R9 — assessed

| # | PG | Basis |
|---|---|---|
| R1 | ✅ | PG ships **purpose-built** tools (`get_priorities`, `create_priority`, `delete_priority`, …). There is **no** catch-all tool with a `method` parameter. Reads and writes are already separate tools, and writes are already split by action type (create/update/delete) — the "ideally" case |
| R2 | ➖ n/a | No PG tool accepts caller-constructed endpoint paths, query strings or request bodies; every tool calls a fixed backend endpoint internally. The page exempts these explicitly |
| R8 | ✅ | PG calls its own first-party backend (`priority-guard.com`). The MCP server domain `mcp.priority-guard.com` matches the service |
| R9 | ✅ | PG transfers no money or crypto and generates no images, video or audio |

### R5, R6, R7 — **NOT verified, and deliberately not claimed**

These require reading all 20 descriptions and exercising all 20 tools. Neither was done in this
pass, and per the writing rule the summary must not quantify over what the check did not cover.

| # | Why not verified | Specific reason to look |
|---|---|---|
| R5 | 20 descriptions not read against 20 handlers | — |
| R6 | 20 descriptions not audited against the five rejection classes | **PG descriptions use a `Call this tool: … Do NOT call this tool: …` form** (e.g. `get_priorities`). That is *routing guidance about this tool*, which reads as legitimate — but R6 rejects descriptions that *"interfere with Claude calling other tools."* Some PG descriptions steer **away** from the tool toward other behaviour (*"when the user wants to plan, break down, or organize tasks"*). **This needs a description-by-description pass before submission.** Related: an `ASSISTANT_GUIDANCE` block was already removed from the deletion tool for being over-instructive |
| R7 | No functional pass run | R11 requires exercising **every** tool through the MCP Inspector **and** as a custom connector. Only the deletion tool has been exercised end-to-end in production |

**R11 is therefore also unmet as a process step**, independent of whether the tools pass.

---

## Part 3 — What this page adds that the master does not have

1. **The automatic-scan / community-vs-verified escalation model** (raw 9), including that
   escalation needs no action and that **the criteria bind regardless of label**.
2. **R1's explicit rejection of the documentation workaround** — describing safe vs unsafe
   operations inside one tool's description does *not* satisfy separation.
3. **R7's data-boundary clauses** — *"do not collect conversation data beyond what the tool needs"*
   and *"do not query Claude's memory, chat history, conversation summaries, or user files."*
   These are privacy obligations that belong next to the retention model.
4. **R9's carve-out** — diagram/chart/UI-mockup design tools are explicitly allowed, which matters
   for MindSort's board rendering.
5. **R10's actual documentation bar** — see the second headline above.
6. **R11 as a gating process step**, not advice.
