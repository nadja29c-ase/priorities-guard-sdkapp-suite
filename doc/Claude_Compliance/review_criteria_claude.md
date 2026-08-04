# Pre-submission checklist — what Anthropic reviewers test

**Source:** `https://claude.com/docs/connectors/building/review-criteria`
**Fetched:** 2026-08-04 — direct fetch.
**Raw source committed:** `sources_raw/review-criteria.raw.md` (78 lines, HTTP 200, 5,421 bytes).
**Feeds:** compliance master §4A/§4B/§5E and the submission checklist. Master **not** yet rewritten.

> ⚠️ **PROVENANCE: FETCH-ONLY, NOT YET PASTE-VERIFIED.** The raw source for this page was
> obtained by `curl` of the `.md` endpoint, **never pasted from the rendered page**. That
> endpoint returns no `Last-Modified` and no `ETag`, so the fetch carries no publication date
> and cannot be shown to track the page a human reads. Everything below — including the
> findings this page is cited for — is **checkable but not currency-verified**. See
> `sources_raw/PROVENANCE.md`. **Replace with a paste before treating as settled.**


**Method:** read for obligations, not keywords. This page is short and almost entirely obligation —
the opposite of `instance-supersession`.

---

## The headline: this page narrows A18 — it does **not** close it

**What was proved:** grep for `consent` and `redirect` across `review-criteria.raw.md` returns
**no match**. The page never mentions consent screens, redirect URIs, or authorization-server UI.

**What that licenses:** *A18 is not on the reviewer's pre-submission checklist.*

⚠️ **What it does NOT license — and what an earlier draft of this line claimed:** *"A18 is not a
directory criterion."* **`software_directory_policy` is the actual policy document and it is
unfetched**, and its **§5D** (*"must use secure OAuth 2.0"*) is precisely where an inherited spec
requirement would land. One page's silence is not the directory's position.

> **This is the hardening bias running in reverse, and that is worth recording separately.** Every
> other instance today inflated a recommendation into a MUST. This one **softened a requirement out
> of existence on one page's silence.** A check that only watches for inflation will not catch it —
> the failure is *unsupported confidence about obligation level*, in whichever direction the
> evidence happens to point.

**Practical effect is unchanged:** A18 is post-submission either way. **But it stays open until
`software_directory_policy` is in.**

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

⚠️ **Which surface is being audited.** The shared registry holds **20** `ToolDefinition`s. The
**Claude reviewer's surface is 8** — `list_tools_for_claude()` filters to `visibility == "public"`
(`tools_list_dupl.py:37`). Every conformance number below states which set it covers, because
"20/20" is a fact about the registry and the reviewer never sees 12 of them.

**The 8 public tools:** `create_priority`, `delete_my_priority_guardian_data`, `get_patterns`,
`get_priorities`, `get_priority_events`, `inspect_adapt`, `onboarding_calendar_setup`,
`render_weekly_report`.

### R3 / R4 — verified by extracting every `ToolDefinition`

| Check | Registry (20) | **Claude surface (8)** |
|---|---|---|
| Every tool has a `title` | ✅ 20/20 | ✅ **8/8** |
| Tool name ≤ 64 chars | ✅ 20/20 | ✅ **8/8** — longest served is `delete_my_priority_guardian_data` at **32** |

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

### R3 hints — ❌ **RETRACTED. The finding was void; PG-Claude is compliant.**

An earlier version of this section flagged `create_priority` (public) and
`record_widget_diagnostic` as carrying **neither** hint, and called it a reviewer judgement call.
**Both halves were wrong for the Claude submission.**

**`create_priority` — Claude's reviewer sees `destructiveHint: true`.**
`tools/create_priority.py:696` does set `destructive_hint=False`, and **the comment on that very
line says where to look next**: *"Reverted: ChatGPT acts on destructiveHint for public tools —
keep False for published app. **Claude override handled in tools_list_dupl.py.**"* Following it:

```python
# Claude-specific destructiveHint overrides.
# create_priority has destructive_hint=False in shared ToolDefinition to preserve
# ChatGPT UX — ChatGPT shows confirmation UI for destructiveHint=True on public tools.
# Anthropic policy §5E requires True for any tool that writes data.
_CLAUDE_DESTRUCTIVE_HINT_OVERRIDES: dict[str, bool] = {"create_priority": True}
```

applied in the `ToolAnnotations` construction. **Someone had already reasoned this through and
documented it against §5E.** No gap, no judgement call.

**`record_widget_diagnostic` — never in Claude's tool list.** `visibility="private"`, and
`list_tools_for_claude()` skips every non-public tool (`tools_list_dupl.py:37`). It cannot be an
annotation defect for this submission because it is never served.

> ⚠️ **The error, named precisely: I audited the wrong surface.** The extraction proved something
> over `mcp_server/priority_guardian/tools/` and stated it about **PG-Claude**. `tools/` is the
> **shared registry and the ChatGPT source of truth**; `priority_guardian_claude/` is the **Claude
> serving path**, and it diverges in **three** ways — public-only filtering, the `destructiveHint`
> override, and `_meta` handling.
>
> This is the **negative-claim scope rule one layer up**: not "which files did the grep cover"
> but **"which surface does this claim describe."** A search can be repo-complete and still
> answer a different question than the one asked.

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

### R7 / policy §1D — `record_widget_diagnostic`, raised and partly answered

R7 forbids collecting *"conversation data beyond what the tool needs"*; policy §1D is stricter
still — *"must not collect extraneous conversation data, even for logging purposes."* Private and
unlisted does not exempt a tool, because it still runs.

**What it accepts** (`widget_tools/record_widget_diagnostic.py`, `INPUT_SCHEMA`): `event`
(≤100 chars), `data` (**object, `additionalProperties: True`**, ≤2048 bytes serialized), `ts`
(int), `ua` (≤500 chars). Only `event` is required.

**What is actually sent** — and this corrects the framing: **no PG-Claude code calls it.** The
only caller repo-wide is `mcp_server/priority_guardian/widget-react/src/widgetErrorReporter.ts`
(the **ChatGPT** widget), via `window.openai.callTool`, sending `event`, `data ?? {}`, `ts`, and
`navigator.userAgent`. Diagnostic event names (`mount`, `displayMode.change`, `set_globals`), not
conversation content.

**Assessment: no §1D violation evidenced, and the schema is not the guarantee.**
`additionalProperties: True` means the tool accepts arbitrary structure — compliance rests on
**call sites**, not on the tool. Today those call sites are ChatGPT-side and benign. ⚠️ **What was
NOT done:** enumerating every `reportWidgetDiagnostic(...)` call to confirm nothing user-authored
is passed in `data`. Worth doing before the ChatGPT submission; **not on the Claude critical
path**, since the Claude surface never calls it.

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
