Anthropic/Claude: COMPLIANCE FOR CONNECTORS — SOURCE SYNTHESIS AND AUDIT RECORD

➡️ **SHIPPING OR SUBMITTING? READ `CLAUDE_COMPLIANCE_REQUIREMENTS_CANONICAL.md` INSTEAD.**
That file carries every requirement, one row each, with its obligation level, its source line and
PG's recorded status — and nothing else. **This file is the audit record**: provenance, changelog,
standing checks, the hardening sweep, round-1/round-2 status and implementation mechanism.
Requirements are roughly 15% of it, which is why it is the wrong thing to read before an increment.
**Last updated: 2026-08-05.** Compliance-Docs-01 — §4C/§4K/§4N bodies rewritten, §5 replaced,
§6 dated, §6b Terms added, §9 PG status recorded, §12 Post-publication added. **§4L and §4O are
deliberately not rewritten** — their sources have no artifact in the tree.

> **THIS HEADER STATES CURRENT STATE ONLY.** Superseded entries live in §11 under their dates.
> *Restructured 2026-08-05: a prior "Last updated" line had been preserved inline here, and it
> contradicted the lines around it — it claimed "7 of 10 pages", listed "the remaining three"
> followed by six items, and named `review-criteria`, `software_directory_policy` and
> `cross-compatibility` as BOTH captured and not-yet-checked. So the first screen told a reader
> that pages were two months stale which the same screen elsewhere said were current.*
>
> **The cause was structural, not careless: POSITION READS AS CURRENCY.** Leaving a superseded
> entry above the fold is the same defect as "Updated this week" — a marker that silently
> re-anchors to whenever the reader looks — and the same defect as the §5 field list left under a
> warning. **Supersession is a move, not an annotation.** See standing check #8.

**No page is "closed."** Round 1 catches omission — did the source get captured. Round 2 runs
*after* the master rewrite and checks the reverse direction: does every claim now in the master
trace to a line in a source dump, and does every PG status claim trace to a file and line?
Round 1 cannot catch invention, and invention is the failure mode this document actually has —
three fabrications survived round 1 on 2026-08-04 alone (the 500px provenance, a "new"
proactive-refresh item the master already documented, and *"nothing in §4C was stale"*).

⚠️ **THE OBLIGATION-LEVEL BIAS, AND IT HAS A DIRECTION. NINE instances found — see the sweep
below.** Soft language gets hardened; hard language is almost never softened. This bias produces
over-constrained increments and wasted work, and **it is the single most useful thing to check for
when reading any section of this file.** One instance ran the other way (A18, softened out of
existence on one page's silence), which is why standing check #1 is stated directionally neutral.

**Round 2 status: run on FOUR artifacts (design-guidelines, transparent-theming, authentication,
review-criteria). Source side clean — no fabricated requirement in any of them.** Defects found
were citation-quality plus one miscount, all fixed. **Round 2 has NOT been run on this master.**

**ELEVEN raw sources are committed** under `Claude_Compliance/sources_raw/` — append `.md` to a
`claude.com/docs` URL, and it works on `support.claude.com` articles too. Every quotation in this
file is therefore checkable against bytes in the tree. ⚠️ **But the `.md` endpoint strips the
publication date**, so a fetched raw cannot be dated from its own contents; see the provenance
table below for which sources carry a date and which do not.

**STATUS OF THIS FILE, 2026-08-04 — the six known-false claims are now CORRECTED, not merely
flagged:**

| Was | Now |
|---|---|
| §2 dead submission URL, no org prerequisite | ✅ portal URL + the Team/Enterprise access gate |
| §4C `static_bearer` line (flagged, uncorrected) | ✅ **corrected** to `static_headers`, beta, org-admin-entered |
| §4F "Required sections" | ✅ Recommended, with the binding §3A/B/C/E/D set stated |
| §4K `ui.domain` "mandatory" / "will not render" | ✅ optional; the decision recorded with its reason |
| §5 old submission form | ✅ superseded; portal content added; "do not fill the portal from §5" |
| Hardening bias recorded but never swept | ✅ **swept** — see below |

**THE HARDENING SWEEP HAS NOW BEEN RUN. Nine instances total**, six previously recorded plus three
found by the sweep itself, all in §4K:

1. 500px inline height "hard limit" — no pixel value is published anywhere
2. a fabricated "recommended" qualifier on the 4–5 data-point constraint
3. §4M — App class "required for production" (source: *recommended*)
4. §4F — "Required sections" (source: *Recommended sections*)
5. §4K — `ui.domain` "mandatory… will not render" (source: optional; host derives an origin)
6. A18 — softened *out* of existence on one page's silence **(the bias running in reverse)**
7. §4K — "Fullscreen constraints (mandatory)" — **settled by grep, pattern stated:**
   `grep -inw "must" design-guidelines.raw.md` returns **3 lines** (128, 204, 278); `grep -inw
   "required"` returns **0**. But only **2 are developer obligations** — raw 204 (light/dark
   themes) and raw 278 (usable by everyone). Raw 128 (*"connectors must be added via web or
   desktop before they appear on mobile"*) states **platform behaviour**, not a duty on the
   developer. **None concerns fullscreen**, so the conclusion holds on either count.
   ⚠️ *An earlier version of this line said "three must statements" without the predicate. Three
   is the token count; two is the obligation count. A number in a compliance document needs its
   PATTERN and its PREDICATE — "3 lines matching `\bmust\b`" and "2 developer obligations" are
   different facts, and only the second bears on compliance.*
8. §4K — "Styling requirements (mandatory)" — **mixed**: light/dark and never-hardcode-colors ARE
   musts (M1); the rest is guidance, and one item is a *permission* labelled a requirement
9. §4K — "CSP declaration (mandatory for MCP Apps)" — **conditional**: required only for servers
   that load external origins

**#8 is the instructive one, and it is a distinct failure mode — not a variant of hardening.**
A blanket "(mandatory)" over a mixed list does not overstate any single item. *"Brand accent
colors are permitted"* sits under the same header as a genuine MUST, and the header destroys the
reader's ability to tell which one binds. Inflation makes one claim wrong; **this makes every
claim in the list unreadable as to obligation level.** It has its own standing check below.

⚠️ **Round 2 has NOT been run on this master.** The artifacts are checked; the synthesis is not.
A green artifact tally does not transfer here. **What HAS been done is corrective**: every claim
known to be false has been fixed at the point where it is stated.

⚠️ **SOURCE COVERAGE — THIS FILE IS CURRENT AGAINST 11 SOURCES AND SILENT ON 9.**
Corrected 2026-08-05; an earlier version of this header said 13 captured.

**Provenance of every captured source — the category determines how far a claim can be trusted:**

| # | Source | Provenance | Publication date |
|---|---|---|---|
| 1 | `design-guidelines` | fetch, paste-corroborated | — |
| 2 | `authentication` | **fetch, paste-corroborated ×3** — three copies, no divergence | — |
| 3 | `transparent-theming` | fetch, paste-corroborated (60 lines, byte-identical) | — |
| 4 | `instance-supersession` | fetch | — |
| 5 | `cross-compatibility` | fetch | — |
| 6 | `submission` | fetch, **relay-corroborated (8 facts)** | ❌ none |
| 7 | `software-directory-policy` | fetch, paste-corroborated | **15 April 2026** (from the paste only) |
| 8 | `software-directory-terms` | fetch, content-corroborated | **16 March 2026** (from the paste only) |
| 9 | `review-criteria` | ⚠️ **FETCH ONLY** | ❌ none |
| 10 | `testing` | ⚠️ **FETCH ONLY** | ❌ none |
| 11 | `lazy-authentication` | ⚠️ **FETCH ONLY** | ❌ none |

**The `.md` fetch endpoint strips the publication date.** Both dates above exist only because the
page was pasted. A fetched raw file **cannot be dated from its own contents** — so the three
fetch-only rows are undated *and* uncorroborated. §4B and §7 draw on `review-criteria` and inherit
that limitation.

⚠️ **THE 9 THINGS THIS FILE IS SILENT ON:**

**Relay-only, no artifact (2)** — §4L and §4O rest on relayed facts with **no bytes in this tree**.
Weaker than fetch-only: a fetch at least leaves something to check against.
- `external-links` → §4L · `troubleshooting` → §4O

**Uncaptured but relevant (2)**
- `directory-vs-custom` — PG is a custom connector today and a directory connector after review
- `managing-your-listing` — holds the edit-vs-review boundary for published listings

**Binding documents outside `llms.txt` (5)** — `llms.txt` indexes `claude.com/docs` only, so a
clean read of it is **not** full coverage:
- Trademark Guidelines (made binding by **Terms T-10**)
- Usage Policy · Universal Usage Standards · High-Risk Use Case requirements ·
  supported-countries policy (all four made binding by **Policy §1A alone**)

**STANDING CHECKS — apply these when writing any claim in this file. IDs are stable; new checks
are APPENDED, never inserted, so references from briefings and increments stay valid.**

1. **State the obligation level the source states, and cite where it says so.** Silence is not
   evidence of absence; emphasis is not evidence of obligation. *(9 instances found in one pass —
   8 hardening, 1 the mirror.)*
2. **A negative claim must state the scope it was proved over.** *"No match for X in file Y"*, not
   *"nowhere"*. A search can be repo-complete and still answer a different question.
3. **Name the surface a claim describes.** The shared registry is not the Claude serving path; an
   audit of `tools/` answers a ChatGPT question.
4. **Never a bare hash.** Record the computation, or the hash together with the URL it derives
   from. A frozen hash is a claim with its premise deleted.
5. **Relative timestamps are worse than none.** In a committed file *"Updated this week"* silently
   re-anchors to whenever the reader looks.
6. **Do not put a single obligation label over a mixed list.** A blanket "(mandatory)" over items
   of differing force does not overstate any one of them — it destroys the reader's ability to tell
   which one binds. Label each item, or label none. Distinct from #1: inflation makes one claim
   wrong; this makes a whole list unreadable as to obligation level.
7. **A number needs its pattern and its predicate.** *"3 lines matching `\bmust\b`"* and *"2
   developer obligations"* are different facts about the same page; only the second bears on
   compliance. State which is meant.
8. **Supersession is a MOVE, not an annotation.** Relocate superseded content — do not leave it in
   place under a warning. **Position reads as currency**, and a reader who trusts the top of a file
   will not read to the caveat. Three instances in one session: a stale "Last updated" line at the
   top of this header, the old submission-form field list left under a notice in §5, and *"Updated
   this week"* in a committed file.

9. **Standing checks are APPEND-ONLY.** Inserting one renumbers every check below it and silently
   invalidates every outside reference — briefings, increments and commit messages all cite these
   by number. `fd71a68` inserted at #7 and broke a reference in an increment briefing written the
   same day.
10. **After any structural edit to this file, confirm the standing-checks block is still present
    and still numbered as referenced.** A block nobody reads until something points at it is a
    block that can vanish silently — and one did, surviving two commits.

> ⚠️ *Restored 2026-08-05. This entire block was DELETED by the header rewrite in `4d2a413` — a
> replacement span ran from the coverage heading to "SCOPE OF THIS FILE" and the checks sat between
> them. It went unnoticed across two commits. Recorded rather than silently restored, because a
> destructive edit that nobody catches is exactly what these checks exist to make visible.
> `fd71a68` had also INSERTED supersession as #7, renumbering pattern-and-predicate to #8 and
> invalidating outside references; it is now appended as #8 instead.*

⚠️ **SCOPE OF THIS FILE.** It records **what the sources require** and **what PG currently does**.
PG status is *recorded status*, not a work list. Where a discrepancy is noted, it is noted so it is
**known** — deciding whether to act on it is a separate, product decision made elsewhere.

⚠️ **Round 2 surfaced a requirement round 1 missed, and PG fails it — see §4C, A18** (redirect
URI hostname on the consent screen). **GATING STATUS RESOLVED (2026-08-04). A18 IS NOT A DIRECTORY
CRITERION.** Both authorities are now checked and both are silent. `review-criteria` (the
reviewer's checklist) never mentions consent screens or redirect URIs. `software_directory_policy`
(the binding legal text) contains exactly one authentication clause — §5D: *"Remote MCP servers
that connect to a remote service and require authentication must use secure OAuth 2.0 with
certificates from recognized authorities"* — which is **TLS certificates plus OAuth 2.0, not
consent-screen UI**, and does not incorporate the MCP spec's display requirement.

**Final label: unmet spec-inherited MUST, NOT a directory criterion, post-submission.** Still a
real security control worth fixing — the consent screen is the only place a user sees where their
authorization is going — but it blocks nothing.

⚠️ **The bias ran in reverse here.** An earlier draft of this line closed A18 on one page's
silence. Every other instance today inflated a recommendation into a MUST; this one softened a
requirement out of existence. A check watching only for inflation will miss it — the failure is
**unsupported confidence about obligation level, in either direction.**

⚠️ **BLOCKER 1 MAY BE MIS-SIZED.** `review-criteria` states the documentation bar as: *"Public
documentation is required by your publish date — a blog post or help-center article is
sufficient. You can share docs privately with Anthropic during review."* **By publish date, not
by submission**, and **no section or example count**. The "seven required sections, three usage
examples" figure is **not on this page** and must come from `submission` or
`software_directory_policy`, both unfetched. **Do not size Blocker 1 from that figure until its
source page is confirmed.**

⚠️ **Round 1 on `authentication` is REOPENED.** Round 2 returned six omissions, not one. The
cause was the extraction *method* — round 1 swept for obligation keywords ("must", "required",
"prohibits") and missed every requirement carried by a `<Note>`, a conditional, a cross-reference,
or prose attached to a number. **The remaining seven pages are read for obligations, not
keywords.** Round-1 ✅ on design-guidelines and transparent-theming was awarded under the same
defective method and is worth no more than the method that produced it.
Anthropic Software Directory Policy last updated: April 15, 2026
Submission guide: https://claude.com/docs/connectors/building/submission
Pre-submission checklist: https://claude.com/docs/connectors/building/review-criteria
Authentication reference: https://claude.com/docs/connectors/building/authentication
Building overview: https://claude.com/docs/connectors/building

⚠️ The old "Anthropic MCP Directory Policy" has been superseded by the Anthropic Software Directory Policy. The old support article now redirects to the new developer docs. All references should use: https://support.claude.com/en/articles/13145358-anthropic-software-directory-policy


1. Supported Claude Platforms
All major Claude platforms support remote MCP connectors:

Claude.ai (web) — Full support with OAuth
Claude Desktop — Full support with OAuth
Claude Code — Direct connection from user's machine (with OAuth support)
Claude API — Integration support
Claude Mobile apps — Connector support
Cowork — Connector support (uses same OAuth callback as Claude.ai)


2. Submission Types
Developers can submit:

Remote MCP servers — internet-hosted servers that provide tools and data to Claude
Desktop extensions — local MCP servers packaged as MCP Bundles (MCPB) for Claude Desktop
MCP Apps — MCP servers that surface interactive UI elements. Additional requirement: screenshots must be included for submission and directory listing.

Submission forms:

Remote MCPs (including MCP Apps): SUBMISSION PORTAL —
  https://claude.ai/admin-settings/directory/submissions/new

⚠️⚠️ BLOCKER — ACCESS GATE. ADDED 2026-08-04. READ BEFORE PLANNING ANY SUBMISSION WORK.

The old URL http://clau.de/mcp-directory-submission IS DEAD for remote MCPs. Submission is no
longer a form; it is an ELEVEN-STEP PORTAL INSIDE CLAUDE.AI ADMIN SETTINGS. Verbatim from
sources_raw/submission.raw.md:21-24:

  "Remote MCP server submissions happen inside Claude.ai, in the submission portal. The portal is
   part of your organization's admin settings, so you need:
   * A TEAM OR ENTERPRISE ORGANIZATION. Admin settings aren't available on individual plans.
   * Directory management access. By default, only organization Owners and Primary owners can
     submit and manage directory listings."

CONSEQUENCE FOR PG: a solo operator on an INDIVIDUAL PLAN CANNOT SUBMIT AT ALL. This requires a
Team organisation, a paid seat, billing setup, and Owner status. Enterprise can delegate via a
custom role with the "Directory management" or "Libraries" permission; TEAM PLANS HAVE NO CUSTOM
ROLES, so on Team it stays with Owners — which is fine for a solo owner.

THIS IS ALMOST CERTAINLY WHAT "USE THE NEWER SUBMISSION FORM" MEANT. The form became a portal and
the portal moved behind an org plan.

IT OUTRANKS EVERYTHING IN THIS FILE. It is ahead of the documentation page, ahead of screenshots,
ahead of every finding in the 2026-08-04 audit. It is also NOT AN ENGINEERING TASK — it is a
purchase decision. ⚠️ CHECK CURRENT TEAM PRICING AND ANY MINIMUM-SEAT REQUIREMENT FIRST; if a
seat minimum exists, that number is the real cost of submitting. NOT VERIFIED HERE — pricing was
not checked and must not be assumed.
Desktop extensions (MCPB): http://clau.de/desktop-extention-submission

Review times vary with queue volume. Anthropic reviews submissions manually and cannot promise to accept or respond to every submission individually. Do not assume a fixed timeline. A self-serve status dashboard is rolling out in Claude.ai — until then you may not receive proactive notification on every status change. Email mcp-review@anthropic.com for escalations.


3. Technical Limits
Constraint
Limit
Claude.ai / Desktop max tool result size
~150,000 characters
Claude Code max tool result size
25,000 tokens (configurable via MAX_MCP_OUTPUT_TOKENS)
Claude.ai / Desktop timeout
300 seconds (5 minutes)
Claude Code timeout
Configurable via MCP_TOOL_TIMEOUT
Tool name max length
64 characters
Transport protocol
Streamable HTTP (legacy HTTP+SSE being deprecated)


⚠️ UPDATE May 2026: Token/size limits differ by surface. Claude.ai and Desktop use a character limit (~150k), not a token limit. The 25,000 token policy limit applies to Claude Code. Previous versions of this document stated 25,000 tokens universally — incorrect.


4. Mandatory Requirements
All requirements in this section are mandatory for directory approval. Missing any of these will result in rejection or revision requests.
4A. Safety Annotations — title plus the applicable hint
Every tool MUST have:

title — human-readable tool name (mandatory on all tools)
The applicable safety hint — readOnlyHint: true for read-only tools OR destructiveHint: true for tools with side effects. Not both — one or the other depending on what the tool does.

Annotation
When to use
readOnlyHint: true
Tool only reads data — search, get, list, fetch, read
destructiveHint: true
Tool modifies data or has side effects — create, update, delete, send
title
Mandatory on every tool — human-readable name for UI display


⚠️ UPDATE May 2026: title is now explicitly mandatory per policy §5E: "MCP servers must provide all applicable annotations for their tools, in particular readOnlyHint, destructiveHint, and title." Previous versions of this document listed title as "additional recommended." Incorrect — it is required. Missing tool annotations account for ~30% of all rejections.

Annotation behavior in Claude:

readOnlyHint: true tools can run without per-call confirmation
destructiveHint: true tools always prompt the user

Decision table:

Tool Behavior
Annotation
Examples
Only reads data
readOnlyHint: true, destructiveHint: false
search, get, list, fetch, read
Writes/modifies data
destructiveHint: true, readOnlyHint: false
create, update, delete, send
Creates temp files
destructiveHint: true
Even temporary writes count
Sends external requests
destructiveHint: true
Emails, notifications, webhooks
Caches internally only
readOnlyHint: true
Internal optimization OK


✅ RESOLVED — verified in code 2026-08-04. `ToolDefinition` declares `title: str` as a REQUIRED field (`mcp_server/priority_guardian/tools/base.py:39`), every tool in TOOL_REGISTRY supplies one, and every tool carries a title in the served `tools/list` payload on BOTH platforms. See §9 Blocker 0.

  *This note previously read "PG's ToolDefinition dataclass has no title field. All 17 tools lack title… required code fix before submission." That was false, and it survived here after §9 was corrected — the same claim lived in two sections and only one was fixed. `structural_guideline_claude_vs_openai.md` had already recorded "title present on all 17 tools", so the repo contradicted itself in three places.*
4B. Tool Design — Read/Write Split Required
NEW explicit rejection criterion:

A single tool that accepts both safe HTTP methods (GET, HEAD, OPTIONS) and unsafe methods (POST, PUT, PATCH, DELETE) is rejected. Catch-all api_request tools with a method parameter fail review.

Requirements:

Split read-only tools and write tools into separate tools
Ideally split write operations further by action type (create, update, delete)
Documenting safe vs. unsafe operations within one tool's description does NOT satisfy this — they must be separate tools

Custom query tools: If a tool accepts freeform endpoint paths, query strings, or request bodies, its description must include a link to or explicit name of the target API (e.g., "Queries the Slack Web API — see https://api.slack.com/methods"). A description like "Makes a request to the API" with no further context fails.
4C. OAuth Authentication
YES — Required if your server requires authentication.

⚠️ UPDATE May 2026: The policy text says "OAuth 2.0." However, Claude's implementation and the MCP authorization spec require PKCE S256, which aligns with OAuth 2.1 behavior. Correct framing: "OAuth 2.0 authorization code flow with PKCE S256 support, as required by Claude's auth implementation and the MCP authorization spec." Advertising "code_challenge_methods_supported": ["S256"] in your authorization server metadata is mandatory — if absent, Claude will refuse to proceed.

Supported authentication types — complete list, verified against
sources_raw/authentication.raw.md:15-22 (2026-08-04):

| Type | Description | Availability |
|---|---|---|
| `oauth_dcr` | OAuth 2.0 + Dynamic Client Registration (RFC 7591) | Supported out of the box |
| `oauth_cimd` | OAuth 2.0 + Client ID Metadata Document | Supported out of the box |
| `oauth_anthropic_creds` | OAuth 2.0 with Anthropic-held client credentials | Contact `mcp-review@anthropic.com` |
| `custom_connection` | Custom URL or credentials supplied at connection time | Contact `mcp-review@anthropic.com` |
| `static_headers` | Fixed credential (API key or bearer token) entered by an **organization administrator** as a request header when adding the connector. **Shared by the organization rather than pasted per user** (raw 24) | **Beta** |
| `none` | No authentication (authless server) | Supported. Optional partial-auth mode is experimental |

*[Changelog 2026-08-04: this table previously carried a line reading "static_bearer (user-pasted
tokens) is not yet supported." That was false on all three counts — wrong name, wrong actor, wrong
availability — and is replaced by the `static_headers` row above. The interim "KNOWN FALSE" flag
that stood here has been removed with the claim it flagged; keeping a warning about a deleted
sentence is its own kind of stale.]*

**No machine-to-machine grant.** A pure `client_credentials` grant — a server-to-server token with
no user in the loop — is **not supported**. Every connection requires user consent (raw 30).
`oauth_anthropic_creds` is the consent-gated alternative: you create the client credentials on your
own AS and send them to Anthropic, which stores them and completes the token exchange on behalf of
consenting users after a standard OAuth consent screen (raw 32-37).

⚠️ **`oauth_anthropic_creds` credentials are bound to the authorization server that issued them**
(raw 41). Migrating to a new AS requires emailing `mcp-review@anthropic.com` with the new
`client_id` and `client_secret` **before cutting over**. CIMD has no such constraint — a CIMD
`client_id` is a self-hosted URL that works against any AS that fetches it.

**CIMD selection requires BOTH conditions** (raw 50). Claude selects CIMD only when the AS metadata
advertises **`"client_id_metadata_document_supported": true`** *and* **`"none"` in
`token_endpoint_auth_methods_supported`** — the second because Claude's CIMD client authenticates
as a **public client** at the token endpoint. **If either is missing, Claude falls back to DCR.**

**DCR at scale** (raw 53): *"For servers expecting high traffic from the directory, prefer CIMD or
`oauth_anthropic_creds` over DCR."* DCR causes Claude to register a **new client on every fresh
connection**, which can produce very large numbers of registered clients. CIMD and Anthropic-held
credentials avoid the registration call entirely.

**Endpoint latency** (raw 135, 137). Claude waits up to **10 seconds** for discovery, registration
and token endpoints, and **30 seconds** for refresh. Past that the flow is treated as failed **even
if the server later completes**. The operational half, which is easy to miss: *return the response
headers and body without buffering behind upstream work*, and check that no reverse proxy, API
gateway or WAF in front of the endpoint is holding the response.

**Parser split** (raw 115). `/token` **must accept** `Content-Type: application/x-www-form-urlencoded`
per RFC 6749 §4.1.3 — Claude sends both the initial exchange and refresh with that content type,
and a framework defaulting to JSON-only body parsing returns `415`. `/register` uses
`application/json` per RFC 7591 §3.1. **Do not assume one parser serves both.**

**Scope control and `offline_access`** (raw 57). Include a `scope` parameter in the
`WWW-Authenticate` header on the 401 to control which scopes Claude requests. Without it, Claude
requests everything the PRM advertises in `scopes_supported`. Claude **appends `offline_access`
automatically** when the AS metadata lists it in `scopes_supported`, to obtain a refresh token.

**Enterprise Managed Auth** (raw 120) — ⚠️ **SOURCE UNCAPTURED.** SSO organizations can connect
their users **without an interactive OAuth consent step**, using an identity assertion signed by
their identity provider. The linked page (`building/enterprise-managed-auth`) describes what the
authorization server must support and **has not been captured**. Recorded as a known gap, not
omitted.

**Microsoft Entra ID — a conditional MUST** (raw 81). If the authorization server is Entra ID, the
MCP server URL **must** also be registered as an **Application ID URI** on the Entra app
registration, or the token request fails with `AADSTS9010010`. Not PG-affecting — PG runs its own
AS — but it is a literal "must" carried in a `<Note>`, which a keyword sweep misses.

**Claude Managed Agents uses a separate credential set** (raw 39), and **Claude Code does not use
Anthropic-held credentials at all** — it runs its own OAuth flow with its own CIMD. ⚠️ **§1 of this
file lists six platforms and does not mention Managed Agents.** Recorded as an inventory gap.

**Claude Code's CIMD is published and fetchable** at `https://claude.ai/oauth/claude-code-client-metadata`
(raw 104). It declares `redirect_uris: ["http://localhost/callback", "http://127.0.0.1/callback"]`
and `token_endpoint_auth_method: "none"`. Loopback support can therefore be tested against the
artifact rather than argued from prose.

**`resource_metadata` need not be on the MCP server's origin** (raw 70) — *"it can be any HTTPS
location that serves the JSON document."* A permission, not an obligation. It is the documented
escape hatch for platforms that cannot serve `/.well-known/*` at the root (Supabase Edge Functions,
Cloudflare Workers without a `/.well-known/*` route, Lambda function URLs routing only a prefix).

**Fallback discovery** (raw 72). If the 401 carries no `resource_metadata`, Claude probes
`/.well-known/oauth-protected-resource/<path>` then `/.well-known/oauth-protected-resource`. Treat
as fallback: it adds round-trips and only works if the platform serves `/.well-known/*`.

**A18 — consent-screen display. Spec-inherited; NOT a directory gate.** (raw 106.) The MCP
authorization spec **requires** authorization servers to display the **redirect URI hostname**
clearly on the consent screen, and **recommends** an extra warning when the only registered
redirect URIs are loopback addresses. Rationale given upstream: a CIMD *"can't prevent loopback
impersonation on its own — any local process can bind a port and claim to be the legitimate
client."*

⚠️ **Obligation level, stated precisely.** The **display** requirement is unconditional; only the
**warning** carries the loopback condition. But it is the **MCP spec** requiring it, surfaced on
Anthropic's page — **not** an Anthropic-enumerated directory criterion. Checked against both
authorities: `review-criteria` never mentions consent screens or redirect URIs, and
`software-directory-policy` contains exactly one authentication clause (§5D, *"secure OAuth 2.0
with certificates from recognized authorities"*), which does not incorporate the spec's display
requirement. **Open security item, post-submission. Not a submission gate.**

**Do NOT re-add "proactive refresh 5 minutes before expiry" as a new finding.** It is already
documented in this section and in the May 2026 changelog. It was listed as new once, in error.


LAZY-AUTHENTICATION — read 2026-08-04, raw at sources_raw/lazy-authentication.raw.md.
Referenced four times from the authentication page and never read until now.

CANONICAL 401 SHAPE (raw 26-27):
  WWW-Authenticate: Bearer error="invalid_token", resource_metadata="…/.well-known/
                    oauth-protected-resource/mcp", scope="orders:read"

PG LIVE, measured 2026-08-04 against https://mcp.priority-guard.com/mcp:
  HTTP/2 401
  www-authenticate: Bearer resource_metadata="https://mcp.priority-guard.com/.well-known/
                    oauth-protected-resource/mcp", scope="pg.access"

DELTA: PG omits error="invalid_token". NOT A VIOLATION — A3 requires only the 401 plus a
resource_metadata pointer, RFC 6750 §3 makes the error parameter optional, and PG's flow works in
production. Recorded as a DELTA FROM THE CANONICAL EXAMPLE, deliberately NOT inflated into a MUST.

THREE FACTS §4C DID NOT HAVE:
- A 200 WITH isError: true IS NOT AN AUTH SIGNAL. "Claude passes the error text to the model as the
  tool result and moves on — there is no auth prompt. Only a transport-level 401 causes Claude to
  pause the call, run the OAuth flow, and retry." If users see "please sign in" TEXT instead of a
  Connect BUTTON, the server is returning the wrong one.
- 403 TRIGGERS RE-AUTHENTICATION ONLY with WWW-Authenticate: Bearer error="insufficient_scope".
  ANY OTHER 403 IS SURFACED AS A TERMINAL ERROR. That is the scope step-up path.
- OMITTING scope IN THE 401 is not neutral: Claude then requests everything in PRM
  scopes_supported plus offline_access, "which can produce an OVER-BROAD CONSENT PROMPT."
  PG already sends scope="pg.access" ✅ — the good case, now with a stated reason.

Under Enterprise Managed Auth the 401 triggers a SILENT TOKEN EXCHANGE instead of the Connect card:
the tool call is retried automatically and the user sees no prompt.

⚠️ **A18 — REDIRECT URI HOSTNAME ON THE CONSENT SCREEN. PG DOES NOT SATISFY THIS.**
**Unmet spec-inherited MUST — directory-gating status UNKNOWN.**
(Found in round 2, 2026-08-04; missed by round 1. Raw source line 106. Code fix NOT applied.)

The **MCP authorization spec** requires the authorization server to display the redirect URI
hostname clearly on the consent screen, and separately **recommends** an additional warning when
the only registered redirect URIs are loopback addresses. Upstream rationale: a Client ID Metadata
Document *"can't prevent loopback impersonation on its own — any local process can bind a port and
claim to be the legitimate client."*

**Provenance matters here.** This is the MCP spec surfaced on Anthropic's page — **not** an
Anthropic-enumerated directory criterion. Whether reviewers gate on it is unknown until
`review-criteria` is fetched. Do not push it against Blocker 1 as though that were settled.

**Scope: the display obligation is unconditional.** Only the extra *warning* is conditioned on
loopback-only registration. An earlier draft of this block said A18 binds PG "because PG accepts
loopback redirects for Claude Code" — that read the paragraph's context as the obligation's scope.
It applies to the hosted `claude.ai` consent screens too, which makes the gap wider and the fix
cheaper: one change covers every flow rather than a Claude-Code-only branch.

**PG's position.** None of the eight `backend/templates/oauth_consent_*.html` templates render the
redirect URI, hostname or host — grep returns nothing in any of them. The render site is
`oauth_provider/authorize.py` (`TemplateResponse`, `:788`), whose context passes only `request`,
`auth_context_id`, `client_name`, `scopes`, `scope_descriptions`.

⚠️ An earlier draft said the value sat *"one line away"* and called this *"display, not plumbing."*
**Both oversold it.** The existing `urlparse(redirect_uri).netloc` lives in `consent_ui.py` on the
**post-consent redirect path**, feeding a log line — a different module and a different request
phase, with nothing reusable. `redirect_uri` *is* in scope at the render site (`authorize.py:770`),
but nothing computes its `netloc` and nothing passes it. The fix is **an add, not a move**: one
computation plus one context entry in `authorize.py`, plus markup in all eight templates.

Bounded, not dismissed: the *impersonation* scenario needs a hostile local process during an active
Claude Code authorization. The *display* gap applies to every flow, including hosted surfaces,
where it is a transparency failure rather than an exploitable one.

For high-traffic directory servers: Prefer CIMD or oauth_anthropic_creds over DCR. DCR causes Claude to register a new client on every fresh connection, potentially creating very large numbers of registered clients. CIMD and Anthropic-held credentials avoid the registration call entirely.

Enterprise limitation: Claude uses a single shared OAuth application per connector. Tenant-level isolation and enterprise-specific OAuth clients are not supported. Users connect to the same OAuth app; access is scoped by the user's own permissions on your service.

PKCE requirements:

S256 challenge method mandatory
Authorization server must advertise "code_challenge_methods_supported": ["S256"] in metadata
If not advertised, Claude will refuse to proceed

Protected Resource Metadata — required for discovery:

Server must return 401 Unauthorized with a WWW-Authenticate header:

WWW-Authenticate: Bearer resource_metadata="https://your-mcp-server/.well-known/oauth-protected-resource"

Metadata document at that URL must include:

{

  "resource": "https://your-mcp-server",

  "authorization_servers": ["https://your-auth-server"],

  "scopes_supported": ["your.scope"],

  "bearer_methods_supported": ["header"]

}

Token refresh behavior:

Claude refreshes reactively on a 401 response
Proactive refresh up to 5 minutes before stored expiry
Must return RFC 6749-compliant error codes: invalid_grant (not custom codes) when refresh token is no longer valid
Honor refresh-token rotation correctly if you rotate tokens

Callback URLs:

Hosted Claude surfaces (Claude.ai web, Desktop, mobile, Cowork):

https://claude.ai/api/mcp/auth_callback

Note: https://claude.com/api/mcp/auth_callback appears in some older documentation. The current official auth reference lists only the .ai URL for hosted surfaces. Register both to be safe during the transition period.

Claude Code (local development and MCP Inspector):

http://localhost:6274/oauth/callback

http://localhost:6274/oauth/callback/debug

Claude Code also uses RFC 8252 loopback redirects on ephemeral ports. Your authorization server must accept http://localhost/callback and http://127.0.0.1/callback with port-agnostic matching.

Common OAuth errors:

Missing callback URLs — most common OAuth rejection reason
Not returning invalid_grant on expired refresh tokens (Claude requires RFC 6749-compliant error codes)
HEAD requests without tokens — handle gracefully after OAuth flow
4D. Test Account
YES — Required if your server requires authentication.

Must be a fully populated account (not empty)
Must NOT require MFA, SMS verification, or additional sign-up steps for the reviewer
Step-by-step setup instructions for a reviewer unfamiliar with your service
Must remain active throughout review period and beyond (for periodic post-admission reviews)
Provide via secure method (e.g., 1Password link)
4E. Firewall and IP Allowlist
For servers behind firewalls, allowlist Anthropic's outbound IP range: 160.79.104.0/21

⚠️ UPDATE May 2026: The actual CIDR range 160.79.104.0/21 is now documented in the official authentication page. Previous versions of this document only said "see docs.claude.com/en/api/ip-addresses" without the actual range.

Required for: Claude.ai and Claude Desktop
Not required for: Claude Code (connects directly from user's machine)
IP allowlisting alone is not recommended as a security measure — use OAuth 2.1

> ⚠️ NEW — Origin-header validation: Your MCP server must also validate the `Origin` header on incoming requests. This is listed as a technical requirement in the submission form policy checklist alongside OAuth, HTTPS, and annotations. Servers that accept requests without validating the `Origin` header fail the security review.

4F. Documentation
Comprehensive documentation required — published at a stable HTTPS URL before your publish date (a blog post or help-center article is sufficient; can share privately with Anthropic during review).

RECOMMENDED sections (corrected 2026-08-04 — this list read "Required sections"):

THE ACTUAL BINDING OBLIGATION SET, from Software Directory Policy §3 — this is what must be true,
and the seven-item list below is a helpful structure, not a requirement:
  §3A  privacy policy link — clear, accessible, covering collection, usage AND RETENTION
  §3B  VERIFIED contact information and support channels (product AND security concerns)
  §3C  document how the Software works, its intended purpose, and how users troubleshoot issues
  §3E  AT LEAST THREE working examples of prompts or use cases demonstrating core functionality
  §3D  a standard testing account WITH SAMPLE DATA
Plus review-criteria: a public page BY PUBLISH DATE; a blog post or help-centre article suffices;
may be shared privately with Anthropic during review.
There is NO seven-section requirement in the binding policy. Confirmed against the policy text.

⚠️ FOURTH INSTANCE OF THE HARDENING BIAS TODAY, AND THE MOST COSTLY. The source
(remote_server_submission_guide.md:256) says "RECOMMENDED sections". This file said "Required
sections". The source is careful: the SECTIONS are recommended, and the THREE EXAMPLES are marked
required inline. Policy §3E backs the examples: "Developers must provide at least three working
examples of prompts or use cases."

THIS IS WHAT INFLATED BLOCKER 1. The actual obligation set is: a public page by PUBLISH DATE
(review-criteria raw 72), documenting how it works, its purpose and troubleshooting (policy §3C),
with >=3 working examples (§3E), plus a privacy-policy link (§3A) and a support channel (§3B).
A blog post is explicitly sufficient. That is a fraction of "seven sections, three worked
examples, before submission."

Server Description — what your server does
Features — key capabilities and use cases
Setup Instructions — how users connect and configure
Authentication — OAuth setup and requirements (if applicable)
Usage Examples — minimum 3 working examples (see format below)
Privacy Policy — link to full privacy policy (mandatory for remote MCP servers that collect user data or connect to a remote service)
Support — how users get help or report issues

Note: The submission page also lists README + manifest privacy_policies field requirements — these apply specifically to local connectors (MCPB desktop extensions), not remote MCP servers. For PG as a remote MCP, a privacy policy URL is the requirement.

Minimum 3 usage examples format:

### Example 1: [Action]

**User prompt:** "[realistic user prompt]"

**What happens:**

- [step 1]

- [step 2]

**Expected output:** [description]
4G. Production Readiness
Server must be in General Availability (GA) status.

Not marked as "beta," "alpha," or "development"
All features fully implemented and tested
Proper error handling — every tool must return a successful response with valid parameters; generic errors ("Internal Server Error" with no detail) fail review
Actionable error messages — validate inputs and return actionable messages, not silent failures
Scalable infrastructure and monitoring
4I. First-Party API Requirement
Your MCP server must call your own first-party APIs or APIs you legitimately proxy. The MCP server domain should match your service. Reviewers verify this during the functional review. This applies to all tools — a server that wraps arbitrary third-party APIs without owning or proxying them will fail review.
4K. MCP Apps Design Guidelines (Interactive Connectors)
Source: https://claude.com/docs/connectors/building/mcp-apps/design-guidelines
Required per policy §3H: developers must follow design guidelines Anthropic publishes.

Inline card constraints:
- **Height:** Auto-fits to content, no nested scrolling. Host caps and clips overflow. No published px limit. If a scroll viewport is needed, escalate to fullscreen via `ui/request-display-mode`
  *[Changelog 2026-08-04: a hedging paragraph stood here explaining that "500px" was an
  implementation budget rather than a platform limit. It is removed — the constraint is stated
  correctly on the line above, and repeating a retracted figure in order to disown it keeps the
  figure in circulation. The source constraint is: auto-fits to content, NO NESTED VERTICAL
  SCROLL (design-guidelines.raw.md:39, :62); the host caps and clips overflow; NO PIXEL VALUE IS
  PUBLISHED ANYWHERE. The mechanism is described in the source's "Scrolling and gestures" section
  (raw 186). PG-Claude and MindSort-Claude target ~500px as an internal engineering budget; that
  is a local implementation choice with no standing in this document.]*
- **Width:** **No documented width limit and no fixed breakpoints.** Official guidance: *"Apps always
  fill the container width—there are no fixed breakpoints. Design responsively from 320px up to
  fullscreen."* Also: *"Full-width layouts — don't add side margins that waste screen real estate"*
  and *"avoid fixed-width layouts; content must reflow gracefully."*
  ⚠️ **The `max-width: 600px` cap — re-argued 2026-08-04 against M10, not inherited.**
  This section previously called the cap *"a product/design choice, not compliance."* That hedge
  was written **before** M10 was extracted from the live design-guidelines page as a Constraint:
  *"No fixed-width layouts; responsive from 320px; no side margins."* It has to be re-argued
  against the requirement, and the answer changes with display mode.

  PG's rule is unconditional (`widget-react/src/main.css:32-35`):
      #root { width: 100%; max-width: 600px; margin: 0 auto; }

  - **Inline: compliant.** `max-width` is not a *fixed* width — with `width: 100%` the layout
    reflows freely from 320px up to 600px, so "no fixed-width layouts" and "responsive from
    320px" are both satisfied. Below the cap, `margin: 0 auto` computes to zero. Nothing binds.
  - **Fullscreen: NOT compliant.** Above 600px the cap binds and `margin: 0 auto` produces
    exactly the artifact M10 names — side margins, on a surface *"meant to use the full
    viewport."* PG declares fullscreen itself (`App.tsx:83`,
    `availableDisplayModes: ['inline','fullscreen']`).

  ⚠️ **CORRECTION 2026-08-04 — the earlier claim here was true and misleading, and the remedy
  it implied does not work.** This block previously read: *"grep confirms no fullscreen-scoped
  override of the cap exists anywhere in the widget's CSS."* Literally true. Substantively wrong:
  **there is a fullscreen-scoped override — it is a JSX inline style object, and the grep scope
  was `.css` files.** Same shape as the `resourceDomains` third block and the §4A `title` claim:
  checked where I was looking.

  **PG has FOUR width caps across two files, and the outermost is the smallest:**

  | Where | Cap | Binds? |
  |---|---|---|
  | `main.css` `#root` | **600px** + `margin: 0 auto` | **YES** — outermost, unconditional |
  | `App.tsx:625` inline `<main>` | 560px desktop / 100% mobile, auto margins | yes (560 < 600) |
  | `App.tsx:727` fullscreen `<main>` | **672px** + auto margins + 16px h-padding | **NO — DEAD** |
  | `App.tsx:585` pie-chart section | **672px** + auto margins, fullscreen only | **NO — DEAD** |

  React mounts into `#root`, so it is the ancestor of every one of them. **A 672px cap inside a
  600px-capped parent never binds.** Someone wrote 672 for fullscreen and gets 600. That is an
  **unintentional state, not a design choice** — and "document the cap as a product decision"
  would have papered over it.

  **The remedy is NOT "scope `#root`'s cap to inline."** Scoping it leaves `App.tsx:727`'s own
  672px cap **plus explicit `marginLeft/marginRight: 'auto'`** — M10's "side margins", generated
  independently of `#root`. The fix must **reconcile all four declarations**, not scope one.

  **Corrected verdict:** the cap is a legitimate product choice *in inline*, a live M10 violation
  *in fullscreen*, and the fullscreen intent is currently **dead code**.
  **Code fix NOT applied** — the fix decision is Nadja's.

  **Related, same block:** `App.tsx:724-725` hardcodes `paddingLeft/paddingRight: '16px'` in the
  fullscreen branch while `paddingTop`/`paddingBottom` *do* consume safe-area values. So
  `safeAreaInsets.left`/`.right` are unused in **the one mode where mobile fullscreen makes them
  matter most** — confirming the §4N `safeAreaInsets` finding from the opposite direction.
- **Max actions:** 2, placed at the bottom of the card
- **Max data points:** 4–5 (stated constraint — no "recommended" qualifier in official docs)
- No drill-ins, breadcrumbs, or multiple views
- No menus or popovers — use visible controls (segmented buttons, toggles, inline options)
- Touch targets minimum 44×44pt on mobile
- WCAG AA accessibility required: maintain high contrast (AA minimum), support keyboard navigation, provide text alternatives for visual content, test with assistive technologies

**Source verified (June 2026):** Official design-guidelines page at https://claude.com/docs/connectors/building/mcp-apps/design-guidelines

Fullscreen constraints (DESIGN GUIDANCE — not mandatory. Corrected 2026-08-04):
⚠️ 7th hardening instance. Labelled "(mandatory)" with no basis. The design-guidelines source
contains exactly THREE "must" statements in the whole page — mobile WebView constraints (raw 128),
light/dark theming (raw 204) and WCAG AA accessibility (raw 278). NONE concerns fullscreen. These
are design recommendations.
- No floating panels — use collapsible sidebars, tabs, or pagination
- App provides its own fullscreen button; close button appears in native header
- Composer always visible — design UX to work with it

Mobile constraints:
- **Fullscreen IS supported on mobile** (verified June 2026): App fills the entire screen with chat input and navigation bar overlaid on top. Keep critical UI within the safe area.
- Renders in WKWebView (iOS) / WebView (Android), not sandboxed iframe
- No camera/mic/location access on mobile
- Connectors must be added via web or desktop before appearing on mobile
- **Safe areas — NOT mobile-specific.** Corrected 2026-08-05; this line read "Honor safeAreaInsets
  for notches and home indicator", which implied a mobile-only concern. Source
  design-guidelines.raw.md:134, verbatim: *"Safe areas are not mobile-specific: on web and desktop
  the composer can overlay the bottom of an inline app, so avoid placing interactive controls
  flush against any edge."*
  Read `hostContext.safeAreaInsets.{top, right, bottom, left}` (pixels) and apply as padding on the
  root container, **or as `scroll-padding` on scroll-snap containers** so items come to rest inside
  the visible region. *"The user won't be able to interact with anything rendered outside the safe
  area"* — e.g. buttons obscured by a mobile navigation bar.

- **`prefersBorder` — set it explicitly, and know what the default costs** (raw 138). Set
  `_meta.ui.prefersBorder` to **true or false explicitly**. **If no value is specified: borderless
  on web, BORDERED ON MOBILE.** In borderless mode content runs **edge-to-edge with no host
  padding**, so *"honoring `safeAreaInsets` becomes essential; the bordered card's built-in padding
  otherwise absorbs most of them."*
  ⚠️ **This is one decision with two consequences, not two independent recommendations.**
  transparent-theming recommends `false` for portability and is silent on the mobile consequence;
  design-guidelines states the consequence. The pages are consistent — one is incomplete alone.
  Choosing `false` buys portability and **costs the mobile card padding**, after which honouring
  `safeAreaInsets` is no longer optional.
  For carousels: apply `safeAreaInsets.left`/`.right` as **`scroll-padding-inline`** on the scroll
  container, so items at rest sit clear of the device edges but can scroll underneath them.

- **Inline carousel** (raw 72-95) — added 2026-08-05, absent from this section before.
  Maintain **consistent card dimensions** within a carousel. On mobile, cards are optimised for
  **horizontal swipe**: design for thumb reach, keep primary actions in the **lower portion** of
  cards, and **peek the next card** to signal scrollability.
- Design responsively from 320px minimum width up to fullscreen — no fixed breakpoints
- Full-width layouts — do not add side margins that waste mobile screen real estate
- Avoid fixed-width layouts; content must reflow gracefully

Styling requirements (MIXED — two are MUSTs, the rest are guidance. Corrected 2026-08-04):
⚠️ 8th hardening instance, and the most instructive kind: the heading is NOT simply wrong. Source
raw 204 IS a must — "All views MUST support both light and dark themes… NEVER hardcode colors."
So the theming items below are genuine obligations (M1). The others — token use for all structural
elements, brand-accent permission — are guidance, and one of them ("brand accent colors are
permitted") is a PERMISSION labelled as a requirement. A blanket "(mandatory)" over a mixed list
makes the real MUST indistinguishable from the advice around it, which is the same defect as
inflating a single line.
- Use host CSS variable tokens for ALL structural elements: backgrounds, text, borders, icons
- NEVER hardcode colors for structural UI — use var(--color-*) tokens
- Brand accent colors are permitted for identity, but core UI must use host palette
- All views must support both light and dark themes — tokens adapt automatically
- Test both light and dark mode before submitting
- Icons: use monochromatic, outlined icons matching host icon color tokens. Icons must SUPPORT understanding — never be the sole means of conveying information (provide aria-label or text alternative)
- Typography: follow three-level size scale (heading, body, caption) and two weights (regular=400, emphasized=600). Avoid arbitrary font sizes outside the token scale.
- Loading states: prefer skeleton screens over spinners for inline content — skeletons match the layout structure of the final content for seamless transition

CSP declaration (CONDITIONAL — required only if you load external origins. Corrected 2026-08-04):
⚠️ 9th hardening instance. The source says "Declare external origins per ui:// resource via
_meta.ui.csp" — an instruction for servers that HAVE external origins, not a blanket obligation on
every MCP App. transparent-theming's only literal "must" on resourceDomains is likewise
conditional: it applies if you want applyHostFonts to load Anthropic Sans. A widget loading nothing
external declares nothing.
Declare external origins per ui:// resource via _meta.ui.csp:
{
  "_meta": {
    "ui": {
      "csp": {
        "connectDomains": ["https://api.example.com"],
        "resourceDomains": ["https://cdn.example.com"],
        "baseUriDomains": []
      }
    }
  }
}
By default, all external origins are blocked. connectDomains = API endpoints the widget calls.
resourceDomains = CDN/asset origins. baseUriDomains = origins permitted in a <base href> (added
2026-08-04 — present in the source example at design-guidelines.raw.md:159 and previously absent
here). frameDomains (third-party iframes) is currently restricted pending security review.

⚠️ resourceDomains ALSO ADDS THE LISTED ORIGINS TO script-src AND style-src, so keep it to origins
trusted to serve executable code; prefer bundling third-party fonts into the widget over
allowlisting public CDNs (transparent-theming.raw.md:52-54).

Display modes:
Declare supported modes via appCapabilities.availableDisplayModes in ui/initialize. Modes: inline, fullscreen, pip. Host responds with supported modes. Request a switch with ui/request-display-mode.

Widget App Domain (_meta.ui.domain) — OPTIONAL. Corrected 2026-08-04.
Source: https://claude.com/docs/connectors/building/mcp-apps/cross-compatibility
(raw source committed at sources_raw/cross-compatibility.raw.md)

⚠️ THIS BLOCK PREVIOUSLY READ "mandatory for MCP Apps" AND "required on every ui:// resource.
Without it the widget will not render." BOTH CLAIMS ARE FALSE. The page never says the field is
required; it says the format and validation rules "are determined by each host platform" and then
gives Claude's formula. That is a conditional: IF you set it, here is the value.

The "will not render" claim is contradicted by a source already in this tree —
sources_raw/instance-supersession.raw.md:179: "Without ui.domain (the default), Claude derives the
iframe origin from the conversation and connector, so the broadcast is scoped to a single
conversation." Widgets render fine without it. That is the DOCUMENTED DEFAULT, not a failure mode.

⚠️ FIFTH HARDENING INSTANCE IN ONE SESSION, AND THE FIRST WITH A DESIGN CONSEQUENCE. PG's FIXED
ui.domain is exactly what widens BroadcastChannel scope ACROSS CONVERSATIONS, which is why §4M
records S5 (a server-minted per-conversation scope key) as a PRE-CONDITION for supersession. If
ui.domain is optional, DROPPING IT GIVES PER-CONVERSATION SCOPING FOR FREE AND DELETES S5. The
false "mandatory" framing removed that option from consideration without anyone deciding against
it. The other four inflations produced wasted effort; this one silently foreclosed a design choice.

THE DECISION, WITH ITS REASON — recorded 2026-08-04 so it stops being an inherited constraint:

  KEEP ui.domain, because PG's widget RUNS ITS OWN OAUTH FLOW and therefore needs a stable
  sandbox origin. Verified: ConnectionStatus.tsx calls connect_google_calendar (:52), extracts
  connect_url (:59), and calls app.openLink({url: connectUrl}) (:63) — a widget-initiated Google
  Calendar OAuth round trip.

  Per the troubleshooting page: "Setting _meta.ui.domain opts your app into a stable sandbox
  origin, which you need if your app runs its own OAuth flow."
  ⚠️ That page is NOT yet in sources_raw/ — the quotation comes from Nadja's read, not from a
  committed source. Confirm it when troubleshooting is pasted.

  ACCEPTED COST: cross-conversation BroadcastChannel scope. CONSEQUENCE: S5 (a server-minted
  per-conversation scope key) is a PRECONDITION if supersession is ever built. See §4M.

⚠️ AN EARLIER VERSION OF THIS BLOCK GAVE A WEAKER REASON — that a fixed domain keeps the origin
stable "for anything relying on localStorage". That argument FAILS TWICE for PG: the supersession
page's localStorage caching is keyed on hostContext.toolInfo.id and exists to survive REMOUNT
WITHIN a conversation, for which per-conversation origin stability is already sufficient; and PG
implements neither supersession nor localStorage caching, so it does not reach PG at all. The
correct reason had already been surfaced in the same session and was passed over. Substituting a
weaker justification for a stronger one already in hand is its own failure mode — the answer was
in the conversation, not only in the tree.
For Claude, compute the value by hashing your full MCP resource URL (including /mcp path):

  node -e 'const url = "https://your-server.com/mcp"; console.log(require("crypto").createHash("sha256").update(url).digest("hex").slice(0,32) + ".claudemcpcontent.com")'

Formula: sha256(MCP_RESOURCE_URL)[:32] + ".claudemcpcontent.com"
The URL is the FULL MCP endpoint including /mcp path — NOT just the origin.
Example: sha256("https://example.com/mcp")[:32] = c3d80a4ed901ee05b21755a88273b4a4
Result: c3d80a4ed901ee05b21755a88273b4a4.claudemcpcontent.com

PG status: domain computed from https://mcp.priority-guard.com/mcp → a7b31ccb44096357600a7460eb0a78e9.claudemcpcontent.com. Confirmed working ✅ (hash recomputed locally 2026-08-04 — CORRECT for the canonical URL.)

⚠️ A SECOND, DIFFERENT PG HASH EXISTS IN THIS REPO: e524d9efa639471cac7431657ac08f2c, at
remote_server_submission_guide.md:445 and structural_guideline_claude_vs_openai.md:388-389. It is
arithmetically correct for the LEGACY URL https://priority-guardian-claude-mcp.onrender.com/mcp and
is therefore STALE. Neither doc did bad arithmetic; one names a superseded URL.

Operationally PG is safe — resources_dupl.py:74 computes the hash AT IMPORT TIME from
MCP_RESOURCE_URL, so the served value always matches the configured URL. The risk is documentary:
at submission the domain must correspond to the URL THE REVIEWER ENTERS, and the repo asserts two
answers.

RULE: record the COMPUTATION, or record a hash TOGETHER WITH THE URL IT DERIVES FROM. Never a bare
hash — a frozen hash is a claim with its premise deleted.

⚠️ AND THE URL MUST BE EXACT. Recomputed 2026-08-04 — three trivially-confusable spellings of PG's
own URL produce three values sharing NOTHING:

  a7b31ccb44096357600a7460eb0a78e9   https://mcp.priority-guard.com/mcp    <- CANONICAL
  4c08ba210ef30c57e400ae94d8b49e97   https://mcp.priority-guard.com/mcp/   <- trailing slash
  6a52566e8cef0070d2481bfab80f0c82   https://mcp.priority-guard.com        <- bare origin

⚠️ LOCAL stdio CONNECTORS HAVE NO URL, so there is nothing to hash — OMIT the _meta.ui.domain
field entirely rather than inventing a value. Added 2026-08-05. (PG is remote and unaffected;
recorded because the formula reads as universal.)

There is NO WAY TO SPOT THIS BY EYE — a wrong domain looks exactly as plausible as a right one.
The troubleshooting page's trailing-slash warning is not theoretical. Always recompute from the
configured MCP_RESOURCE_URL rather than transcribing.

Cross-platform note (source: https://claude.com/docs/connectors/building/mcp-apps/cross-compatibility):
MCP Apps can run in both Claude and ChatGPT from a single codebase. The SDK auto-detects the host
environment via App.connect() (no explicit transport parameter needed). registerAppTool() and
registerAppResource() automatically generate platform-specific metadata.

Host CSS token reference — PARTIAL. Corrected 2026-08-05; this heading previously read
"Complete host CSS token reference" and the list below omits four whole groups.

⚠️ MISSING FROM THE LIST BELOW, present in design-guidelines.raw.md:
  ghost variants     — color-background-ghost (raw 293), color-text-ghost (304),
                       color-border-ghost (315)
  disabled variants  — color-background-disabled (298), color-text-disabled (309),
                       color-border-disabled (320)
  color-border-inverse (raw 314)
  the FULL RING GROUP — color-ring-primary, -secondary, -inverse, -info, -danger (raw 322-326)
  the heading size scale with line-heights

Per standing check #1 the honest options were to enumerate them or drop the word "Complete".
Both are done: the word is dropped AND the gaps are named, so a reader knows what to go and look
up rather than assuming the list below is exhaustive. The values that ARE listed were verified
against the source and are correct.
IMPORTANT: Hardcoded fallback hex values MUST match official values below. Mismatches cause incorrect rendering when host tokens fail to load.

Background tokens (Light / Dark):
--color-background-primary:    #FFFFFF        / #30302E
--color-background-secondary:  #F5F4ED        / #262624
--color-background-tertiary:   #FAF9F5        / #141413
--color-background-inverse:    #141413        / #FAF9F5
--color-background-info:       #D6E4F6        / #253E5F
--color-background-danger:     #F7ECEC        / #602A28
--color-background-success:    #E9F1DC        / #1B4614
--color-background-warning:    #F6EEDF        / #483A0F

Text tokens (Light / Dark):
--color-text-primary:          #141413        / #FAF9F5
--color-text-secondary:        #3D3D3A        / #C2C0B6
--color-text-tertiary:         #73726C        / #9C9A92
--color-text-inverse:          #FFFFFF        / #141413
--color-text-info:             #3266AD        / #80AADD
--color-text-danger:           #7F2C28        / #EE8884
--color-text-success:          #265B19        / #7AB948
--color-text-warning:          #5A4815        / #D1A041

Border tokens (Light / Dark):
--color-border-primary:        #1F1E1D (40%)  / #DEDCD1 (40%)
--color-border-secondary:      #1F1E1D (30%)  / #DEDCD1 (30%)
--color-border-tertiary:       #1F1E1D (15%)  / #DEDCD1 (15%)
--color-border-info:           #4682D5        / #4682D5
--color-border-danger:         #A73D39        / #CD5C58
--color-border-success:        #437426        / #599130
--color-border-warning:        #805C1F        / #A87829

Typography tokens:
--font-sans: "Anthropic Sans, sans-serif" | --font-mono: "ui-monospace, monospace"
Weights: normal=400, medium=500, semibold=600, bold=700
Sizes: xs=12px, sm=14px, md=16px, lg=20px
Line heights: xs/sm/md=1.4, lg=1.25

Radius tokens:
--border-radius-xs: 4px | --border-radius-sm: 6px | --border-radius-md: 8px
--border-radius-lg: 10px | --border-radius-xl: 12px | --border-radius-full: 9999px

Border width: --border-width-regular: 0.5px

Shadow tokens:
--shadow-hairline: 0 1px 2px 0 rgba(0,0,0,0.05)
--shadow-sm: 0 1px 3px 0 rgba(0,0,0,0.1), 0 1px 2px -1px rgba(0,0,0,0.1)
--shadow-md: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -2px rgba(0,0,0,0.1)
--shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.1), 0 4px 6px -4px rgba(0,0,0,0.1)

⚠️ NOTE: The -solid suffix tokens (e.g. --color-background-success-solid, --color-background-info-solid)
are NOT in the official token table. These appear to be internal/undocumented tokens. Use with caution.
Consider using the official non-solid equivalents as fallbacks.

✅ PG FALLBACK VALUES — corrected (verified 2025-05-30):
- color-text-tertiary:         #73726C ✓
- color-text-secondary:        #3D3D3A ✓
- color-background-secondary:  #F5F4ED ✓
All PG fallbacks now match official values.

PG widget pre-submission checklist (MCP Apps specific):
[x] All structural colors use var(--color-*) tokens with hex fallbacks — verified 2025-05-30
[x] Widget tested in both light and dark mode — useHostStyles hook active
[x] _meta.ui.csp declared on ui:// resource (connectDomains, resourceDomains) — resources_dupl.py
[x] Inline card: auto-fit height (no nested scroll), ≤2 actions, no popovers — App.tsx inline mode
[x] All touch targets ≥44×44pt — verified across all components
[x] safeAreaInsets honored for mobile layout — App.tsx line 52
[x] html, body { background: transparent; margin: 0; } — main.css
[x] <meta name="color-scheme" content="light dark" /> in document head — pg-dashboard-claude.html
[x] prefersBorder: false set in _meta.ui — resources_dupl.py
[x] openLink() only called from user gesture handlers — ConnectionStatus.tsx onClick
[ ] Allowed link URIs declared in submission portal — SATISFIABLE (see §4L; PG owns the origin)

⚠️ THE PROCEDURE FOR THE TOOL-EXERCISE ATTESTATION IS DOCUMENTED. building/testing is CAPTURED at
sources_raw/testing.raw.md (fetch-only, undated). It states that ANY Claude account — Free, Pro,
Max, Team or Enterprise — can add a custom connector, and that custom connectors use THE EXACT SAME
RUNTIME as directory connectors. So the attestation work is NOT gated behind the Team/Enterprise
requirement in §2; only the portal itself is. There is no staging environment: testing happens in
production as a custom connector, or through a tunnel for a local server.

✅ B7 IS NOT GATED BY THE TEAM PLAN. FOUND 2026-08-04 on building/testing, raw line 13:
  "ANY CLAUDE ACCOUNT (Free, Pro, Max, Team, or Enterprise) CAN ADD A CUSTOM CONNECTOR... CUSTOM
   CONNECTORS USE THE EXACT SAME RUNTIME AS DIRECTORY CONNECTORS, so what works here will work
   after publication."

THE TEAM/ENTERPRISE ORG IS REQUIRED FOR THE SUBMISSION PORTAL ONLY — NOT FOR TESTING. The
eight-tool exercise that B7 attests to CAN BE DONE TODAY, FREE, ON THE EXISTING INDIVIDUAL PLAN,
in parallel with the pricing decision. It is no longer blocked behind item 1.

There is NO STAGING ENVIRONMENT — "you test in production using a custom connector". Local servers
are tested by exposing them through a tunnel (Cloudflare Tunnel, ngrok) and adding the tunnel URL
as a custom connector; keep auth enabled while tunnelling and shut the tunnel down afterwards.

⚠️ TEST CREDENTIALS — AN OBLIGATION NOBODY HAD RECORDED. Beyond "fully populated account, not an
empty shell" so reviewers can "list real records, search real data, exercise write tools on real
resources", the page requires: "INCLUDE STEP-BY-STEP SETUP INSTRUCTIONS FOR SOMEONE UNFAMILIAR
WITH YOUR SERVICE." A written deliverable, not just an account.

✅ clientInfo — PG IS CLEAN, verified 2026-08-04. Claude's clientInfo name varies ("claude-ai",
"Anthropic" sometimes with a service suffix, "claude-code"); behaviour must NOT be gated on an
exact name or version; and it is UNAUTHENTICATED — "any client can claim any name, so IT MUST
NEVER FEED AN AUTHORIZATION DECISION." grep across mcp_server/ and backend/ finds no use of
clientInfo; the only match is a URL in a comment. NOTE: this is the SAME CLASS as open task #10
(client-controlled _meta["openai/subject"]) — unauthenticated client-supplied data reaching an
authorization decision. PG is clean here and NOT clean there.

⚠️ B7 IS AN ATTESTATION, NOT A PROCESS STEP. ADDED 2026-08-04.
The portal states: "You also confirm you've run every tool yourself, either via MCP Inspector or
as a custom connector in Claude." That is a CHECKBOX YOU TICK, and Software Directory Terms T-3
warrants that "any information you give us will be accurate and up-to-date."

CURRENT STATE: only delete_my_priority_guardian_data has been exercised end to end (production,
2026-08-04). The other SEVEN public tools have not.

TICKING B7 TODAY WOULD BE A WARRANTY DEFECT, not a process shortcut. This reclassifies R11 from
"unmet process step" to a PRE-SUBMISSION BLOCKER: all 8 public tools through MCP Inspector or as a
custom connector, BEFORE the portal. The 8 are create_priority, delete_my_priority_guardian_data,
get_patterns, get_priorities, get_priority_events, inspect_adapt, onboarding_calendar_setup,
render_weekly_report.
[ ] Widget handles multiple instances gracefully — NOT IMPLEMENTED (non-blocking, enhancement)
[x] Loading states use appropriate indicators — inline uses shimmer, fullscreen uses spinners
[x] Icons have text alternatives (aria-label) — verified across all components
[x] No fixed-width layouts — flex layouts reflow at narrow widths

4L. External Links Behavior (MCP Apps)
Source: https://claude.com/docs/connectors/building/mcp-apps/external-links

Default behavior: ui/open-link always shows a confirmation modal before navigating. Directory connectors can allowlist destinations to skip the modal.

Allowlisting (declare in submission form Allowed link URIs field):
- HTTPS origin format: https://example.com (exact hostname match, no subdomains implied)
- Custom URI scheme format: example-app or example-app:
- Entries must be URLs/schemes your organization owns
- Generic schemes (http, file, mailto, javascript, etc.) are rejected

User-activation requirement (hard requirement):
ui/open-link MUST be triggered by a real user gesture (button click). Programmatic calls or timer-triggered calls always show the confirmation modal regardless of allowlist. Design your app so openLink is always in an event handler.

Reserved/rejected URI schemes (full list from official docs):
http, https, file, data, javascript, blob, mailto, tel, sms, intent, android-app, browser-extension schemes, Windows shell schemes (search-ms, shell). Any entry matching these is rejected during review.

PG status: compliant — ConnectionStatus.tsx triggers openLink only on button click user gesture.

4M. Widget Instance Supersession (MCP Apps)
Source: https://claude.com/docs/connectors/building/mcp-apps/instance-supersession

Each time Claude calls a tool that renders an MCP App, a new iframe is mounted. There is no host API to unmount earlier instances. If the tool is called multiple times in a conversation, multiple live widget copies exist simultaneously, each independently able to push model-context updates and messages.

For stateful single-instance widgets (dashboards, carts): implement BroadcastChannel-based supersession — older instances detect a newer sibling and disable themselves (grey out UI, disable buttons, stop sending model-context updates).

Why BroadcastChannel works:
All widget iframes from a single connector are served from the same sandbox origin on *.claudemcpcontent.com (iframe sandbox includes allow-same-origin). A BroadcastChannel opened in one instance reaches every other instance from the same connector in the current conversation.

Pattern: server stamps each tool result with an election key (createdAt + seq) in structuredContent. Widget reads key via toolresult event, broadcasts on BroadcastChannel. Older instances compare keys and mark themselves superseded.

⚠️ THIS ENTIRE SECTION DESCRIBES A PATTERN, NOT AN OBLIGATION. Verified 2026-08-04 against the
committed raw source: the page contains NO directory-compliance requirement. Its language is
uniformly optional — "should remain interactive", "You can use BroadcastChannel", "should also
handle", "recommended for production". Everything below is binding only IF the pattern is
implemented. Do not brief an increment from this section as though it were gating.

PG status: get_priorities, render_weekly_report, create_priority can all be called multiple times. PG does not currently implement instance supersession. Multiple live dashboard instances will coexist. This is not a submission blocker but is a known UX degradation. Track as post-submission improvement.

⚠️ THE VERDICT ABOVE IS RIGHT AND ITS SCOPE IS WRONG. Corrected 2026-08-04.

Verified across the whole of App.tsx (933 lines): updateModelContext = 0 occurrences,
sendMessage = 0, callServerTool = 28, isBridgeStale = 28. PG NEVER CALLS EITHER API THIS PAGE'S
GUARDS PROTECT, so the pattern's core requirement — gate updateModelContext and sendMessage on
!superseded — is inapplicable to PG as written.

The page's concern is CONTEXT POLLUTION: several live instances each pushing model-context
updates and injected messages into Claude's next turn. PG's exposure is different IN KIND:
several live dashboards can each callServerTool to CREATE AND DELETE priorities, which is a
DATA-MUTATION concern this page does not address anywhere. Filing it as an instance of
supersession mis-files it. It is a PG-specific risk sitting OUTSIDE this page and needs tracking
on its own terms.

Also: PG already has isBridgeStale 3-second staleness detection, and it ALREADY GATES EVERY
callServerTool SITE — 12 guards of the form
  if (isBridgeStale || !appRef.current?.callServerTool) throw new Error('Tool calls not available')
at :266, :287, :309, :333, :353, :373, :393, :415, :435, :455, :475, :497.

That is the same data-mutation surface named above, so PG is not unprotected there. What
isBridgeStale does NOT do is instance election: it answers "is this bridge dead?", not "is this
the newest instance?", so it does nothing to stop SEVERAL SIMULTANEOUSLY-LIVE dashboards from
each mutating. The gap is narrower than "no protection" and it is real.

Counts re-verified 2026-08-04 by two methods (grep -c and grep -o | wc -l), which agree:
updateModelContext 0, sendMessage 0, callServerTool 28, isBridgeStale 28. The identical 28/28 was
challenged as a copy-paste artifact — reasonable suspicion, but it is structural: 12 lines contain
BOTH symbols because the guard names both. All 28 isBridgeStale occurrences fall between :48 and
:554.

⚠️ PG HAS A FIXED ui.domain, AND THE SCOPE RULE BELOW APPLIES TO PG DIRECTLY.
resources_dupl.py:75 defines WIDGET_APP_DOMAIN = f"{_hash}.claudemcpcontent.com" and sets it on
ALL THREE _meta.ui blocks (:90, :114, :148). Per the source: with a fixed ui.domain "the origin
is shared across every conversation and tab for your connector. A fixed channel name would let a
widget in one conversation supersede a widget in another." Neither hostContext nor the tool-call
arguments carry a Claude-provided conversation ID.

CONSEQUENCE: if supersession is ever implemented from this section as written, CROSS-CONVERSATION
SUPERSESSION IS THE DEFAULT OUTCOME. The server-minted scope key is a PRE-CONDITION for PG, not a
footnote. See also cross-compatibility#domain-handling for how ui.domain is computed on Claude —
an adjacent requirements surface this section does not cross-reference.

Implementation details (from official docs):
- Election key MUST use server wall-clock time (createdAt) — NOT client-side Date.now(). Client mount time does not reflect tool-call order; stored conversations remount widgets as they scroll into view.
- seq should be monotonic counter or derived from durable state (database row ID, version number)
- Channel scope: without fixed ui.domain, BroadcastChannel is scoped per-conversation automatically. With fixed ui.domain, scope widens — include a server-minted conversation scope key to prevent cross-conversation interference.
- Election key is read from the SDK toolresult event (params.structuredContent), NOT from initial widget props.

  ADDED 2026-08-04 — five items this list omitted (raw source cited):
- Comparison is a THREE-LEVEL chain: createdAt, tie-broken by seq, tie-broken by
  String(instanceId). This section previously said only "compare keys". The third level exists
  FOR DETERMINISM, which is precisely the part that fails silently. (raw 101, 107-112)
- Ignore inbound messages until your own key is finalized (keyFinalized), or you reply with an
  undefined key. (raw 122)
- Announce is a TWO-MESSAGE HANDSHAKE, not a broadcast: send "hello", and reply "born" to any
  "hello" you hear. Without the reply, late-mounting siblings never learn about existing peers.
  (raw 119-133)
- Guard sendMessage TOO, not only updateModelContext. This section named only model-context
  updates. "The election only matters if superseded instances actually stop talking to Claude."
  (raw 136-138)
- POST-TIMEOUT ADOPTION PATH: if the server key arrives after the fallback timeout, adopt it,
  recompute superseded against the peers already heard from, and RE-ANNOUNCE so siblings update
  their view. "The recomputed result may flip the instance back to live." The fallback notes
  below previously stopped at the keySource caveat. (raw 213)

localStorage caching across remounts:
- On Claude.ai web: hostContext.toolInfo.id is the stable tool-use ID. Persist the resolved server key to localStorage keyed by toolInfo.id to reuse on remount without waiting for toolresult event again.
- On Claude iOS: toolInfo.id is undefined when a stored conversation is rehydrated. Detect this case (toolInfo?.id == null) and skip the cache — fall back to waiting for the toolresult event. This is the only ordering source that works on every platform.
- Treat localStorage as an optimization, not a correctness guarantee.

Fallback if server key is delayed:
- Race the toolresult event against a 1-second timeout after connect()
- If timeout fires first: fall back to client-side Date.now() as orderKey
- CRITICAL: if mixing server and client timestamps, tag with keySource ('server' | 'client') and refuse to compare a client value against a server value — a server createdAt from hours ago will always be smaller than a fresh client timestamp, wrongly handing 'live' to the wrong instance

SDK App class — RECOMMENDED, not required:
- Use the SDK App class (new App() / useApp() in React), not a hand-rolled postMessage bridge
- Hand-rolled bridges silently drop ping (liveness check) and ui/resource-teardown (host asking widget to clean up before unmount)
- Claude.ai web does not currently send ping or resource-teardown to widgets; Claude iOS sends resource-teardown only when user navigates away from the conversation
- The App class handles the full request surface and is RECOMMENDED for production
- PG status: uses useApp() React hook — correct. ✅

  ⚠️ CORRECTED 2026-08-04. This line read "required for production" and the heading read
  "SDK App class requirement". The source says "recommended for production" (raw line 240).
  Harmless in effect — PG uses useApp() — but the line would mislead anyone reading §4M for
  what is mandatory.

  ⚠️ THIRD INSTANCE OF THE SAME FAILURE IN ONE DAY, after the 500px "hard limit" and the
  fabricated "recommended" qualifier on the 4-5 data-point constraint. Two inflated a
  recommendation into a MUST; this one does too. THE BIAS HAS A DIRECTION: soft language gets
  hardened, hard language never gets softened. Recorded as a bias, not three corrections,
  because the direction is what produces over-constrained increments and wasted work.

4N. Transparency and Theming (MCP Apps)

⚠️ THIS SECTION IS NOT OPTIONAL POLISH. It is the MECHANISM FOR DISCHARGING M1 — "All views must
support both light and dark themes. Use the host's style tokens — they automatically adapt. NEVER
HARDCODE COLORS." (design-guidelines.raw.md:204.) That is one of only TWO developer obligations
stated with "must" on the entire design-guidelines page, and it is recorded in §4K. The techniques
below — applyDocumentTheme, applyHostStyleVariables, the useHostStyles hook, token-based CSS with
light-dark() fallbacks — are how M1 is satisfied. Read this section as compliance, not styling.
Source: https://claude.com/docs/connectors/building/mcp-apps/transparent-theming

For widgets to blend with Claude's conversation UI (strongly recommended for directory apps):

Required CSS:
  html, body { margin: 0; background: transparent; }
  (any opaque background on <html> or <body> hides the chat surface)

Required HTML head tag:
  <meta name="color-scheme" content="light dark" />
  CRITICAL: Keep this tag even though applyDocumentTheme() also sets color-scheme at runtime.
  The tag covers the FIRST PAINT before your script runs and prevents an opaque-backdrop flash.
  Both are needed — the static tag and the runtime API serve different purposes.

Recommended resource meta:
  _meta.ui.prefersBorder: false — removes host card border; Claude web defaults to borderless
  but other hosts differ; being explicit keeps app portable

Host font loading (optional but expected):
  Add https://assets.claude.ai to CSP resourceDomains to enable Anthropic Sans loading
  _meta.ui.csp: { resourceDomains: ["https://assets.claude.ai"] }
  SECURITY NOTE: resourceDomains also adds listed origins to script-src and style-src.
  Only allowlist origins you trust to serve executable code. Prefer bundling third-party
  fonts into your widget rather than allowlisting public CDNs.

hostContext theming fields (passed by Claude on connect and on hostcontextchanged):
  theme:               "light" or "dark"
  styles.variables:    --color-background-*, --color-text-*, --color-border-*,
                       --color-ring-*, --font-*, --border-radius-*, --border-width-*
                       (complete list, verified 2026-08-04 — this line previously ended
                       "etc.", which hid four of the seven categories)
  styles.css.fonts:    @font-face rules for Anthropic Sans, served from https://assets.claude.ai
  Updates carry only the changed fields — guard with existence checks before applying.

Listener ordering (T4 — ADDED 2026-08-04, absent from this section before):
  "Register the listener before you connect so you don't miss an early update."
  PG assigns onhostcontextchanged at App.tsx:144, inside the onAppCreated callback (:85).
  Whether onAppCreated fires before connect() is SDK internals and is NOT verified. PG
  also uses useHostStyles, which re-applies on the event, so the React path likely covers
  it regardless. ⚠️ unverified, low risk.

SDK helpers (import from @modelcontextprotocol/ext-apps):
  applyDocumentTheme(theme)          — sets <html data-theme> and root color-scheme
  applyHostStyleVariables(variables) — writes all style tokens onto :root as CSS custom properties
  applyHostFonts(fontCss)            — injects @font-face rules once

React pattern (preferred):
  useHostStyles(app, app?.getHostContext()) — applies all three helpers and re-applies
  automatically on hostcontextchanged. This is the correct React hook for theming.
  PG status: ✅ correct — App.tsx:166 is `useHostStyles(app, app?.getHostContext())`,
  TWO args, with the comment "must pass hostContext for dark mode".
  ⚠️ This line previously read "uses useHostStyles(app)" — the ONE-ARG form this very
  section warns against. The verdict was right and the evidence was false; an audit line
  whose supporting evidence is wrong is worse than no line. Corrected 2026-08-04.

CSS fallback pattern (preferred — uses light-dark() for dual-mode fallbacks):
  Once applyDocumentTheme sets color-scheme, light-dark() resolves correctly:
  color: var(--color-text-primary, light-dark(#141413, #faf9f5));
  border: var(--border-width-regular, 0.5px) solid var(--color-border-primary);
  This is better than single-value fallbacks — handles both light and dark correctly
  even when host tokens are not yet loaded.

⚠️ HOST FONTS ARE PAID FOR AND NEVER USED (found 2026-08-04, code fix NOT applied)

  resourceDomains: ["https://assets.claude.ai"] is set (resources_dupl.py:94, :118) so that
  applyHostFonts can inject Anthropic Sans, and useHostStyles does inject it. The @font-face
  rules load. Nothing consumes them:

    main.css:25  font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI',
                              Roboto, sans-serif;      <- hardcoded, no var(--font-sans, …)
    main.css:40  font-family: inherit;                 <- inherits the hardcoded stack

  VERIFIED TOTAL, not partial: grep for "--font-" across the whole of widget-react/src/
  returns nothing. Those two lines are the only font-family declarations in the widget.

  So T3 ✅ is TRUE AND HOLLOW. The CSP allowance is granted and the security surface widened
  (resourceDomains also feeds script-src and style-src — the page's own caveat), and the widget
  renders in system-ui regardless. PG pays the cost and takes none of the benefit.

  The page's canonical form closes it in one edit:
    font-family: var(--font-sans, system-ui, sans-serif);
  NOT APPLIED — this is a widget code change requiring a rebuild and deploy; the fix decision
  is Nadja's. The alternative (drop assets.claude.ai from resourceDomains and narrow the CSP)
  is equally valid and cheaper to ship. Either closes it; doing neither is the only wrong answer.

PG status:
  useHostStyles(app, app?.getHostContext()) hook: ✅ correct (App.tsx:166 — two args)
  color-scheme meta tag: verified in pg-dashboard-claude.html ✅ (both the Vite input and the
    built widgets/pg-dashboard-claude.html:6 that is actually served)
  prefersBorder: false: set in resources_dupl.py ✅
  host fonts consumed: ❌ injected, never referenced — see above
  html/body background: transparent in main.css ✅
  CSS fallbacks: single-value, not light-dark() — verified at main.css:29
    `color: var(--color-text-primary, #141413)`.
    SCOPE: a fallback applies only when the custom property is ABSENT, i.e. when the
    widget renders OUTSIDE a Claude host. Inside Claude, applyHostStyleVariables sets the
    variables and the fallback is never used — so in-host light/dark correctness is
    UNAFFECTED. The gap is that out-of-host rendering shows the light value in dark mode.
    "Suboptimal" is the right severity; scoped 2026-08-04 so it is not read as an M1 risk.

4J. Token Efficiency Response size should be reasonable for the task (~150k character ceiling is a hard limit, but reviewers will reject responses far below this if they're unnecessarily verbose)
Claude Code: Max 25,000 tokens per tool result (configurable)
Do not return full database dumps when summaries were requested
When possible, give users options to exclude unnecessary text

⚠️ MCP Apps specific: If a tool result exceeds ~150,000 characters AND Claude's code execution sandbox is active,
the result is written to the sandbox filesystem instead of passed inline. Your app receives a pointer to the
stored file rather than the structured content it needs — the widget never hydrates.
Mitigation strategies:
- Paginate large results — return summary/first page, let user request more via follow-up interactions
- Fetch details on demand — use app-initiated tool calls to load additional data as user explores
- Defer heavy content — return identifiers/previews in initial result, provide separate tool for full content
PG status: get_priorities returns ~1-6KB, render_weekly_report returns ~2-4KB — well within limit. ✅

4O. MCP Apps Technical Requirements (from troubleshooting docs)
Source: https://claude.com/docs/connectors/building/mcp-apps/troubleshooting

app.connect() is mandatory:
  Your widget MUST call app.connect() (Vanilla JS) or useApp() (React) to establish communication
  with the host. Event handlers (ontoolinput, ontoolresult) are NOT invoked until connected.
  Without app.connect(), the tool call appears in Claude but the widget is invisible.
  PG status: uses useApp() React hook — correct. ✅

Non-zero height required:
  The widget iframe must have a non-zero height. Zero height causes the app to be invisible even
  when fully connected. Ensure root element has explicit dimensions or content that gives it height.
  Do NOT call sendSizeChanged({ width, height: 0 }) except to explicitly hide.
  PG status: autoResize: true is set — height is driven by content. ✅

Debugging in Claude Desktop:
  Enable Developer Mode: Help > Troubleshooting > Enable Developer Mode
  Open DevTools: Cmd+Option+I (Mac) or Ctrl+Shift+I (Windows)
  Your app loads as content of the inner iframe (iframe nested inside another iframe)
  After editing claude_desktop_config.json: Developer > Reload MCP Configuration


5. SUBMISSION PORTAL — eleven steps
Source: sources_raw/submission.raw.md (fetch, relay-corroborated on 8 facts; UNDATED).

*[Changelog 2026-08-05: this section previously listed the fields of the OLD SUBMISSION FORM, with
a supersession notice bolted on top. The form does not exist for remote MCPs. The old field list is
REPLACED, not annotated — a superseded list under a warning is still a list people fill in.]*

ACCESS GATE FIRST — see §2. The portal lives in Claude.ai admin settings and requires a TEAM OR
ENTERPRISE ORGANISATION; admin settings are unavailable on individual plans.

THE ELEVEN STEPS:
  1. Introduction     2. Connection     3. Tools         4. Listing
  5. Use cases        6. Company        7. Authentication  8. Data handling
  9. Test & launch   10. Compliance    11. Review

Progress SAVES IN-BROWSER between steps within a session.

STEP 2 — CONNECTION. Server URL must be https://. ⚠️ The exact string entered here is one of the
three that must agree; see the three-way URL match in §8.

STEP 3 — TOOLS. The portal SYNCS ANNOTATIONS AUTOMATICALLY from the served tool list and GROUPS
UN-ANNOTATED TOOLS SEPARATELY. Violations are flagged with an instruction to "fix them on your
server before submitting" — every tool needs a title plus the applicable readOnlyHint or
destructiveHint (Policy §5E).

STEP 4 — LISTING. Hard limits:
  name          <= 100 characters
  tagline       <=  55 characters
  description   <= 2000 characters
  categories    1-5
  URL SLUG      ⚠️ PERMANENT ONCE PUBLISHED. See §12 — it becomes
                https://claude.ai/directory/connectors/SLUG, a public URL used in marketing and in
                any "Connect to Claude" button. Display names can change; the slug cannot.

STEP 8 — DATA HANDLING. Asks whether the server reads data, writes data, or both; whether it calls
your own API, an API you proxy with permission, or a third party you do not control; whether it
handles personal health data; and whether it carries sponsored content.

STEP 9 — TEST & LAUNCH. Test credentials are required and must be a FULLY POPULATED ACCOUNT with
SAMPLE DATA (Policy §3D), plus STEP-BY-STEP SETUP INSTRUCTIONS FOR SOMEONE UNFAMILIAR WITH THE
SERVICE (testing.raw.md:39).

  ⚠️ THIS STEP CARRIES AN ATTESTATION, NOT A SUGGESTION: "You also confirm you've run every tool
  yourself, either via MCP Inspector or as a custom connector in Claude." Terms T-3 warrants that
  all information given to Anthropic is accurate, so ticking it without having exercised every
  public tool is a WARRANTY DEFECT. See §8.

STEP 10 — COMPLIANCE. SEVEN ACKNOWLEDGMENTS, ALL REQUIRED. Under Terms T-3 each is a WARRANTY, not
a checkbox, so each is mapped to the obligation it acknowledges:

  1. directory guidelines          -> Policy §3H (and the published design guidelines)
  2. first-party API usage         -> Policy §3F
  3. financial transactions        -> Policy §4A
  4. AI media generation           -> Policy §4B
  5. prompt injection              -> Policy §2D-§2G
  6. conversation data collection  -> Policy §1D and §1F
  7. public documentation          -> Policy §3A / §3B / §3C / §3E

SCREENSHOTS (MCP Apps): PNG only, 3-5 images, at least 1000px wide, cropped to the app response
area, THE PROMPT MUST NOT APPEAR IN THE IMAGE (supply prompt text separately for each). ASPECT
RATIO IS UNCONSTRAINED. VIDEO AND GIF ARE REJECTED. ONE BATCH COVERS ALL SURFACES — no separate
mobile assets. A carousel template is available in the Figma community file.

SKILLS ARE NOT A STANDALONE SUBMISSION TYPE — bundle them in a plugin. *[Changelog 2026-08-04: an
"Optional: Skills & Plugins" entry stood here and was wrong.]*

BEFORE SUBMITTING: exercise every tool through the MCP Inspector AND as a custom connector in
Claude (`claude plugin validate` for plugins). See §8 and building/testing.

6. Anthropic Software Directory Policy (Full Text)
Published 15 APRIL 2026. Captured 2026-08-04 to sources_raw/software-directory-policy.raw.md.
Text below verified identical to the captured source across all five sections.
⚠️ The publication date comes from Nadja's PASTE of the rendered page. The .md fetch carries NO
date, so this date cannot be recovered from the raw file — see the provenance table in the header.
1. Safety and Security
A. Software must not violate or facilitate violation of Anthropic's Usage Policy. Must comply with Universal Usage Standards, High-Risk Use Case requirements, and supported countries policy.

B. Software must not evade or enable users to circumvent Claude's safety guardrails, system instructions, or sandbox environments.

C. Software must prioritize protecting user privacy and the privacy interests of third parties. Responsibly handle personal and sensitive data, follow privacy best practices, ensure compliance with applicable laws.

D. Software must only collect data from the user's context that is necessary to perform their function. Must not collect extraneous conversation data, even for logging purposes.

E. Software must not infringe on the intellectual property rights of others.

F. Software must not query or extract data from Claude's memory, chat history, conversation summaries, or user-generated or uploaded files. (NEW vs old policy)
2. Compatibility
Applies to Software that provides Claude with tools or capabilities through natural language descriptions ("Instructional Software").

A. Must define each tool through narrow, unambiguous natural language specifying what it does and when to invoke it.

B. Tool descriptions must precisely match actual functionality. Must not include unexpected functionality or promise undelivered features.

C. Tool descriptions must not create confusion or conflict with other Software in the Directories.

D. Must not intentionally call or coerce Claude into calling other external software unless requested and intended by a user.

E. Must not attempt to interfere with Claude calling tools from other software, tools, databases, or resources.

F. Must not direct Claude to dynamically pull behavioral instructions from external sources.

G. Must not contain hidden, obfuscated, or encoded instructions. All behavioral guidance must be human-readable and clearly presented. (NEW vs old policy)

Prompt injection patterns that are rejected:

Tool descriptions that instruct Claude to call external software the user didn't request
Instructions that interfere with Claude calling other tools
Directions to pull behavioral instructions from external sources
Hidden, obfuscated, or encoded instructions
Instructions that tell Claude to behave in ways unrelated to the tool's function, attempt to override system instructions, or promote products/services
3. Developer Requirements
A. Must provide a clear, accessible privacy policy link explaining data collection, usage, and retention. Provide Anthropic with links to all applicable privacy policies.

B. Must provide verified contact information and support channels.

C. Must document how Software works, its intended purpose, and how users can troubleshoot issues.

D. Must provide a standard testing account with sample data for Anthropic to verify full functionality.

E. Must provide at least three working examples of prompts or use cases.

F. Must verify ownership/control of any API endpoint, domain, or user interface Software connects to. (Plugins are an exception.)

G. Must maintain Software and address issues within reasonable timeframes.

H. Must agree to Software Directory Terms and follow design guidelines Anthropic publishes.
4. Unsupported Use Cases
A. Software that transfers money, cryptocurrency, or other financial assets, or executes financial transactions.

B. Software that uses AI models to generate images, video, or audio content. (Exception: design-focused software creating visual aids — slides, diagrams, charts, UI mockups, logos — permitted if not offered as standalone image generation.)

C. Software that serves advertisements, sponsored content, paid product placements, or exists primarily as an advertising vehicle.
5. Additional Requirements for MCP Servers
A. Must gracefully handle errors and provide helpful feedback rather than generic error messages.

B. Must be frugal with tokens. Amount of tokens a tool call uses should be commensurate with complexity of the task. Give users options to exclude unnecessary text when possible.

C. Tool names must not exceed 64 characters.

D. Remote MCP servers requiring authentication must use secure OAuth 2.0 (with certificates from recognized authorities). In practice: OAuth 2.1 with PKCE S256 per MCP authorization spec.

E. Must provide all applicable annotations for tools, in particular readOnlyHint, destructiveHint, and title.

F. Should support Streamable HTTP transport. SSE may be supported for now but will be deprecated.

G. Local MCP servers must be built with reasonably current versions of all dependencies, including node_modules.


6b. ANTHROPIC SOFTWARE DIRECTORY TERMS — THE BINDING CONTRACT
Published 16 MARCH 2026. Captured 2026-08-04 to sources_raw/software-directory-terms.raw.md.
⚠️ Date from Nadja's PASTE; the .md fetch carries none.
*[Moved 2026-08-05 from "4F-bis", where it had been appended for convenience. It sits after §6
because the Policy and the Terms are the two binding documents and belong together — §6 is what
the Software must do, §6b is what you WARRANT when you submit.]*
Source: https://support.claude.com/en/articles/13145338-anthropic-software-directory-terms
Dated 16 March 2026. Raw: sources_raw/software-directory-terms.raw.md
Full extraction: software_directory_terms_claude.md

⚠️ THIS DOCUMENT HAD NO REPO COPY OF ANY KIND UNTIL 2026-08-04. §6 reproduces the POLICY in full
and never mentioned the TERMS — while Policy §3H makes agreeing to them MANDATORY. The Policy says
what the Software must do; the TERMS are what you WARRANT when you submit.

T-3  ACCURACY WARRANTY: "any information you give us will be accurate and up-to-date."
     This covers EVERY FIELD ON THE SUBMISSION FORM. A wrong URL, a stale domain hash or an
     inflated capability claim is a WARRANTY DEFECT, not a typo. It is what makes this entire
     documentation audit contractually load-bearing rather than merely tidy.

T-4  PRIVACY WARRANTY INCLUDING THIRD PARTIES: provide and adhere to a privacy policy, "provide
     all applicable THIRD-PARTY privacy policies", and ensure all such policies "clearly and
     accurately describe to users what user information you AND THIRD PARTIES collect and how you
     and third parties use and share such information."
     PG connects to Google Calendar, so Google's policy must be PROVIDED and its collection/use/
     sharing accurately described. Disclosure existing is NOT the same as providing the link.

T-9  SECURITY VULNERABILITY REPORTING: "implement and maintain a mechanism for receiving reports
     of security vulnerabilities from Anthropic AND FROM THIRD PARTIES and to investigate such
     reports with a reasonable standard of care."
     DISTINCT FROM §3B, which is a user support channel. T-9 names Anthropic and third parties and
     adds a DUTY OF CARE. Nothing in this audit shows such a mechanism exists. APPEARS UNIMPLEMENTED.

T-10 NO PARTNERSHIP/SPONSORSHIP/ENDORSEMENT statements without prior written approval; comply at
     all times with Anthropic's Trademark Guidelines. Constrains fulfilling-productivity.com launch
     copy. ⚠️ The Trademark Guidelines are a SECOND referenced binding document and are NOT in the
     repo — .md returns 404 and the HTML is a Next.js bundle. NEEDS A PASTE. Recorded as an
     obligation whose CONTENT IS UNKNOWN.

T-8  Ongoing duty to maintain quality and security standards consistent with the Policy AS UPDATED.
     This is why the doc pass must be repeatable, not one-off.
T-1/2/5/6/7  Rights warranty; legal compliance; indemnification; licences over descriptions, docs,
     name and logos; authorisation to test and to collect AND SHARE functional metadata. Recorded
     as accepted, not actionable.

Also: Anthropic has NO obligation to include the Software and may remove it at any time for any
reason without liability. Terms may be modified WITHOUT PRIOR NOTICE; continued maintenance
constitutes acceptance.

⚠️ THE ART. 28 ERROR IS NOW A WARRANTY DEFECT, NOT LEGAL HYGIENE. Privacy policy v3.2
characterises Anthropic as an Art. 28 data processor, which is incorrect. Under T-3 it is
inaccurate information given to Anthropic; under T-4 it is a policy that does not "clearly and
accurately describe" the third-party relationship. It moves from "should fix" to FIX BEFORE THE
FORM GOES IN. It is cheap, and it is the one document Anthropic is guaranteed to read closely.


7. Common Rejection Reasons (ranked by frequency)
Missing tool annotations (~30% of rejections) — Every tool must have readOnlyHint OR destructiveHint AND title. Fix all tools before submitting.

OAuth callback URL errors — Missing https://claude.ai/api/mcp/auth_callback. Also ensure Claude Code loopback URIs support port-agnostic matching.

Catch-all API tools — A single tool with method parameter accepting GET and POST is rejected. Split read/write into separate tools.

Incomplete documentation — Missing examples, unclear setup, missing required sections. Minimum 3 detailed examples with user prompt + what happens + expected output.

Production readiness — Server marked as "beta" or shows instability. Must be GA status.

Missing or inaccessible privacy policy — Immediate rejection. Verify URL is live before submitting.

Generic error messages — "Internal Server Error" or "Bad Request" with no detail fails functional review. Reviewers call every tool with valid parameters.


8. Pre-Submission Checklist
Code requirements
All tools have readOnlyHint OR destructiveHint annotation
All tools have title annotation (human-readable name)
MCP tool names ≤ 64 characters
Read and write operations are in separate tools (no catch-all api_request with method parameter)
Custom query tools link to target API in description
OAuth 2.1 with PKCE S256 implemented
PKCE S256 advertised in authorization server metadata
Protected Resource Metadata hosted at /.well-known/oauth-protected-resource
resource field in metadata exactly matches submission URL
https://claude.ai/api/mcp/auth_callback allowlisted in OAuth provider
Claude Code loopback URIs registered (port-agnostic matching for localhost and 127.0.0.1)
Server returns 401 with WWW-Authenticate header for unauthenticated requests
Server returns invalid_grant (not custom codes) when refresh token is invalid
HTTPS/TLS with valid certificates
Origin header validation — server validates Origin header on all incoming requests
Anthropic IP range 160.79.104.0/21 allowlisted (if behind firewall)
Token-efficient responses — no verbose dumps; users given options to exclude unnecessary text
Error handling — actionable messages, not generic errors
Streamable HTTP transport supported
Operational requirements
Server is production-ready (GA status, not beta)
THREE-WAY URL MATCH — corrected 2026-08-04. This item named only TWO consumers; there are THREE,
and the third is the one that fails silently. The EXACT string is:

    https://mcp.priority-guard.com/mcp        (no trailing slash, /mcp present)

  1. PRM `resource` field at /.well-known/oauth-protected-resource
       must match the URL AS THE USER ENTERS IT IN CLAUDE, including path (A4)
  2. SUBMISSION FORM URL — what the reviewer pastes into Settings > Connectors
  3. _meta.ui.domain = sha256(<that exact string>)[:32] + ".claudemcpcontent.com"
       = a7b31ccb44096357600a7460eb0a78e9.claudemcpcontent.com

⚠️ WHY THE THIRD MATTERS AND WHY IT IS DANGEROUS: a trailing slash anywhere in the chain yields
4c08ba210ef30c57e400ae94d8b49e97 — sharing NOTHING with the canonical value. The result is a
ui.domain mismatch and THE WIDGET DOES NOT RENDER, while OAuth CONTINUES TO WORK — so the failure
presents as a widget bug with no apparent connection to the URL. PG is internally consistent
(resources_dupl.py:74 derives the hash from MCP_RESOURCE_URL at import), so the entire risk sits
at the BOUNDARY: what gets typed into the submission form. FILL THE FORM FROM THIS LINE, NOT FROM
MEMORY.
Tested from Claude.ai
Tested from Claude Desktop
OAuth flow completes successfully end-to-end
Every tool returns successful response with valid parameters (reviewers call all tools)
Performance acceptable under load
Documentation requirements
Documentation page published at stable HTTPS URL
All required sections present (description, features, setup, auth, examples, privacy, support)
Minimum 3 working usage examples with user prompt + what happens + expected output
Privacy policy published and accessible
Support channel documented
Submission form materials
Test account fully populated (no MFA/SMS required for reviewer)
Server logo (URL or SVG) ready
Favicon verified
Screenshots of widget in use (MCP Apps only — mandatory)
Allowed link URIs declared (if connector uses ui/open-link)


9. PG-Specific Compliance Blockers (Claude Submission)
This section tracks Priority Guardian-specific gaps. Items already satisfied for OpenAI are not re-listed here — see compliance_master_1.3.26.md.
🟢 Blocker 0 — title Annotation — RESOLVED (verified in code 2026-08-04)
`ToolDefinition` declares `title: str` as a REQUIRED field (mcp_server/priority_guardian/tools/base.py), and every tool in TOOL_REGISTRY supplies one. Verified live in the served `tools/list` payload on BOTH platforms — every tool carries a title in its ToolAnnotations. This entry described code work that was already done and told a reader to redeploy for it. A false 🔴 is worse than a missing one: it spends a submission cycle on nothing.

🔴 Blocker 1 — Documentation Page
No Claude-specific documentation page exists.

⚠️ CORRECTED 2026-08-05 — this entry read "before submission, containing ALL REQUIRED SECTIONS
including minimum 3 usage examples." Both halves were wrong, and the first is the "Required
sections" inflation that §4F now corrects. THE SAME FALSE CLAIM WAS LIVE IN TWO SECTIONS AND ONLY
ONE WAS FIXED — the exact failure the corollary in doc/README.md exists to prevent, and a reader
planning this page reads §9, not §4F.

THE ACTUAL OBLIGATION:
  - Due BY PUBLISH DATE, not by submission (review-criteria raw 72)
  - A BLOG POST OR HELP-CENTRE ARTICLE IS SUFFICIENT. No section count, no structure prescribed.
    Docs may be shared PRIVATELY with Anthropic during review
  - Content required by Policy §3C: how it works, its intended purpose, how users troubleshoot
  - Policy §3E: AT LEAST THREE WORKING EXAMPLES of prompts or use cases — this half WAS right
  - Policy §3A: privacy policy link · §3B: verified contact and support channels
There is NO seven-section requirement anywhere in the binding policy. The "Recommended sections"
list in remote_server_submission_guide.md is a helpful structure, not an obligation.
RECORDED STATUS — 2026-08-05. Findings from the documentation pass. These are STATUS, NOT WORK
ITEMS; deciding whether to act on any of them is a separate product decision.

A18 — consent screen does not display the redirect URI hostname. None of the eight
backend/templates/oauth_consent_*.html render it; authorize.py's TemplateResponse context passes
request, auth_context_id, client_name, scopes, scope_descriptions. OPEN, SPEC-INHERITED, NOT A
DIRECTORY GATE — absent from both review-criteria and the binding policy. Post-submission.

TOOL COUNTS — 20 IN THE REGISTRY, 8 PUBLIC ON CLAUDE'S SERVED SURFACE. list_tools_for_claude()
filters to visibility == "public" (tools_list_dupl.py:37). All 8 carry a title and at least one
hint. ⚠️ create_priority carries destructive_hint=False in the SHARED registry to preserve ChatGPT
UX and is overridden to True for Claude in tools_list_dupl.py per Policy §5E. AUDIT THE CLAUDE
SERVING PATH, NOT THE SHARED REGISTRY — a check against tools/ answers a ChatGPT question.

_meta.ui.domain — KEPT, and the reason is now recorded rather than inherited. PG's widget runs its
own OAuth flow (ConnectionStatus.tsx calls connect_google_calendar, extracts connect_url, then
app.openLink), which needs a STABLE SANDBOX ORIGIN. ACCEPTED COST: the origin is shared across
conversations, so BroadcastChannel scope spans them — making a server-minted per-conversation scope
key a PRECONDITION if instance supersession is ever built (§4M). The field is optional (§4K); this
is a decision, not a constraint.

inspect_adapt — DESCRIPTION/HANDLER MISMATCH. The served description says it RECORDS confirmed
action steps; the handler persists nothing (332 lines, zero backend calls, docstring "validate
provenance -> return success") and read_only_hint=True is correct. Policy §2B requires descriptions
to precisely match actual functionality. RECORDED AS A FINDING. NOT FIXED. TOOL DESCRIPTIONS ARE
SHARED WITH THE LIVE CHATGPT APP AND ARE NOT TOUCHED.

🟢 Blocker 2 — MCP App Screenshots (Submission Prep) — RESOLVED
Screenshots of the widget rendering in Claude.ai are mandatory for MCP App directory listing.
**Status (June 2026):** Widget rendering for third-party connectors is now working. Issue #61 resolved. Screenshots can be collected once widget increment ships.
✅ Resolved — OAuth Callback URLs (Fixed in Increment Claude-03)
https://claude.ai/api/mcp/auth_callback and https://claude.com/api/mcp/auth_callback both added to backend/core/config.py allowlist. PKCE S256 already implemented. No further code change needed.
🟡 Item — CORS Origins (Operational Verify)
Confirm whether Claude's browser client hits the MCP server directly. If yes, https://claude.ai must be in CORS_ALLOWED_ORIGINS on the Claude Render service.
🟡 Item — /.well-known/oauth-protected-resource URL Match (Operational Verify)
Verify before submission:

# Use the URL your 401 actually advertises — Claude probes the PATH-SUFFIXED document
# FIRST and falls back to the bare one. Checking only the bare path tests a document
# Claude may not use, so the check can pass while the real one is wrong.
curl https://<CLAUDE_MCP_SERVER_URL>/.well-known/oauth-protected-resource/mcp
curl https://<CLAUDE_MCP_SERVER_URL>/.well-known/oauth-protected-resource   # fallback
# For PG-Claude both currently serve an identical document (verified 2026-08-04) — that is
# what makes the bare-path-only check misleading rather than obviously broken.

# → the "resource" field must match your MCP server URL EXACTLY AS THE USER ENTERS IT IN
#   CLAUDE, INCLUDING ANY PATH COMPONENT (authentication page, A4). For PG-Claude that is
#   https://mcp.priority-guard.com/mcp — WITH /mcp. Do NOT compare against the bare origin.
#   This line previously read 'must equal <CLAUDE_MCP_SERVER_URL>', which is ambiguous and
#   FALSE if read as the origin: resources_dupl.py deliberately distinguishes MCP_SERVER_URL
#   (passed to _extract_origin for the widget domain) from MCP_RESOURCE_URL (the /mcp
#   endpoint). A correct server would have failed this check. Corrected 2026-08-04.
🟢 Item — MCP App Widget Rendering — RESOLVED (June 2026)
**Previous status:** Widget rendering for third-party custom connectors was silently failing (anthropics/claude-ai-mcp GitHub issue #61, filed February 17, 2026).
**Current status (June 2026):** Issue #61 resolved. Widgets now render correctly for third-party custom connectors. resources/read is called as expected. No longer a blocker.


10. Items That Do NOT Need Changes for Claude
Backend API endpoints — unchanged
Google OAuth integration — unchanged
Inbound OAuth provider (DCR, PKCE S256, JWT issuance, JWKS) — unchanged; PKCE S256 already implemented and tested
Token verification logic (mcp_auth.py) — unchanged
Safety annotations (readOnlyHint, destructiveHint, openWorldHint) — 100% coverage across all 20 registry tools (8 of which are public and therefore on Claude's served surface)

  ⚠️ COUNT CORRECTED 2026-08-04: this read "all 17 tools". The registry now holds 20 ToolDefinitions.
  17 was stale. A reviewer can check this against the served tools/list, so the number matters.
  Other locations on the old count: structural_guideline_claude_vs_openai.md:8. The instances in
  doc/README.md and §9 are HISTORICAL QUOTES of a corrected claim and must NOT be renumbered.
Privacy policy — already discloses Google Calendar data handling per Google and GDPR requirements
Test account — review@priority-guard.com with seed data already exists
Transport — FastMCP Streamable HTTP already in use; SSE deprecated path not used
Error handling — implemented with structured error messages


12. POST-PUBLICATION (new section, 2026-08-05)
Source: building/after-publishing. ⚠️ RELAY-ONLY, NO ARTIFACT — this page has no raw file in
sources_raw/. Recorded because it materially changes how reversible submission decisions are, but
it is the weakest provenance category in this document. See sources_raw/PROVENANCE.md.

TOOL CHANGES DO NOT REQUIRE RESUBMISSION. To add, change or remove tools, deploy the change to the
server. There is no resubmission to Anthropic and NO SCHEDULED RE-REVIEW; Claude picks up the new
tool surface on the next connection.

⚠️ CAVEAT, AND IT IS NOT SMALL. Software Directory Policy states Anthropic conducts "both initial
and ONGOING reviews", and Terms T-8 obliges continued maintenance of standards consistent with the
policy AS UPDATED. "No scheduled re-review" is NOT "never reviewed again". This is latitude for
iteration, not a gap to ship through.

WHAT IS IRREVERSIBLE: the URL SLUG. Once published it cannot be changed, and it is a permanent
public URL — https://claude.ai/directory/connectors/SLUG — that will appear on marketing pages and
in any "Connect to Claude" button. Display names can change; the slug cannot. Choose it at the
portal deliberately.

LISTING EDITS go through the submissions dashboard. The page building/managing-your-listing covers
which changes can be made directly and which require review. ⚠️ UNCAPTURED — not fetched, not
pasted. It is a separate page, not a rename of after-publishing.

DELISTING: email mcp-review@anthropic.com. (§7 says removal is requestable "through support
channels"; this is the specific address.)

11. What Changed From Previous Version

### 2026-08-05 (c) — Header restructured: current state only

The header had accumulated superseded entries **in place**, and they contradicted the current
material above and below them. Moved here, verbatim, so the record survives without misleading
anyone reading the first screen:

> *Superseded, from the 2026-08-04 header:* **"round 1 (re-fetch + extract) run on 7 of 10 source
> pages: design-guidelines, authentication, transparent-theming, instance-supersession,
> review-criteria, cross-compatibility, software_directory_policy. Partially refreshed: the
> remaining three (review-criteria, submission, software_directory_policy, troubleshooting,
> external-links, cross-compatibility) were last verified 2026-06-23 and are NOT yet re-checked."**

**Three errors in that one sentence**, all live at the top of the file until today: *"the remaining
three"* is followed by **six** items; `review-criteria`, `software_directory_policy` and
`cross-compatibility` appear in **both** the captured list and the not-yet-checked list; and
*"7 of 10"* had stopped describing anything, the inventory being 11 committed + 2 relay-only +
2 outstanding.

Two further stale counts fixed in place: *"Round 2 … run on all three round-1 artifacts"* (**four**)
and *"The raw upstream markdown for all three pages is now committed"* (**eleven**).

**The cause was structural.** Prior entries were preserved by *leaving them where they were*.
**Position reads as currency** — the identical failure diagnosed two rounds earlier in *"Updated
this week"*, and the one §5 had just been rewritten to fix. Now **standing check #7: supersession
is a move, not an annotation.**

### 2026-08-05 (b) — Compliance-Docs-01 completion pass

The first pass covered roughly two-thirds of the briefing. An audit against it found seven gaps,
all now closed:

- **Header** now carries **per-file provenance** (paste-corroborated / relay-corroborated /
  fetch-only) with publication dates, and states plainly that the file is **current against 11
  sources and silent on 9** — the 9 enumerated by name, not counted.
- **§5 REPLACED, not annotated.** The old form's field list is gone. A superseded list under a
  warning is still a list people fill in. The eleven steps are named, with the listing character
  limits, the permanent slug, the data-handling questions, the Test & launch attestation, and the
  seven compliance acknowledgments **each mapped to the obligation it warrants**.
- **§6** dated 15 April 2026 with its capture date, and flagged that the date exists only because
  the page was pasted.
- **§6b** — the Terms **moved** from the interim "4F-bis" to sit after §6, where the two binding
  documents belong together: §6 is what the Software must do, §6b is what you warrant.
- **§4K** — local stdio connectors have no URL, so `_meta.ui.domain` is **omitted**, not invented.
- **§8** — the tool-exercise attestation now records that `building/testing` **is captured**, and
  that the work is **not** gated behind the §2 org requirement: any account can add a custom
  connector, and custom connectors use the same runtime as directory connectors.
- **§9** — the four PG status items recorded, and **Blocker 1 corrected.** It still read
  *"containing all required sections"* — the same inflation §4F had already fixed. **The identical
  false claim was live in two sections and only one was corrected**, which is precisely the failure
  the fix-the-claim-not-the-instance corollary exists to prevent. Someone planning the
  documentation page reads §9, not §4F.

**§4L and §4O remain unrewritten** — `external-links` and `troubleshooting` still have no artifact.

### 2026-08-05 — Compliance-Docs-01: body rewrite of §4C, §4K, §4N; new §12

**Documentation only.** No code, no tool descriptions, no PG remediation. PG findings appear as
recorded status, not work items.

**§4C** rewritten against `authentication.raw.md` and `lazy-authentication.raw.md`. The
`static_headers` row replaces the false `static_bearer` line **and the interim "KNOWN FALSE" flag
was removed with it** — a warning about a deleted sentence is its own kind of stale. Added: the
CIMD dual condition and why the second half exists; DCR-at-scale; the latency budgets **with their
operational half** (no buffering behind upstream work; check proxy/gateway/WAF); the
`/token` vs `/register` parser split; `offline_access` auto-append; the `oauth_anthropic_creds`
AS-binding migration constraint; the Entra `AADSTS9010010` conditional MUST; Claude Managed Agents
as an eighth surface; Claude Code's published CIMD URL; `resource_metadata` not needing the MCP
origin; fallback discovery. **A18** recorded with its obligation level stated precisely —
spec-inherited, display requirement unconditional, **not a directory gate** on either authority.
**Enterprise Managed Auth** recorded as a known gap, source uncaptured.

**§4K** — the 500px hedging paragraph is **deleted**, not rewritten: repeating a retracted figure
to disown it keeps it in circulation. `baseUriDomains` added to the CSP example with the
`script-src`/`style-src` caveat. *"Complete host CSS token reference"* → **"PARTIAL"**, with the
four missing groups named (ghost, disabled, `border-inverse`, the full ring group, the heading
scale) so a reader knows what to look up. Safe areas corrected — **not mobile-specific**; the
composer overlays inline apps on web and desktop too. `prefersBorder` recorded as **one decision
with two consequences**. Inline carousel constraints added.

**§4N** now states at the top that it is **the mechanism for discharging M1** — one of only two
developer obligations stated with "must" on the whole design-guidelines page — rather than reading
as optional polish.

**§12 Post-publication** (new). Tool changes need no resubmission and there is no scheduled
re-review, **but** the policy's "ongoing reviews" and Terms T-8 mean that is latitude, not a gap.
The **slug is irreversible**. Delisting is `mcp-review@anthropic.com`.

**Not done, and why:** **§4L and §4O were not rewritten.** `external-links` and `troubleshooting`
have **no raw file in the tree and never have** — their current content rests on relayed facts with
no bytes behind it. Rewriting those bodies would have converted unverifiable claims into
authoritative-looking prose. They keep their **relay-only, no artifact** marking until the pastes
are committed.

**Source count corrected 13 → 11.** Provenance gained a fifth category (**relay-only, no
artifact**). The **hardening sweep was run** for the first time — nine instances, three of them new
and all in §4K. Standing checks **#6** (do not put one obligation label over a mixed list) and
**#7** (a number needs its pattern and its predicate) added.

### 2026-08-04 Update (round 1 on 3 of 10 pages — design guidelines, authentication, transparent theming)

**Sources re-fetched:** `mcp-apps/design-guidelines`, `building/authentication`,
`mcp-apps/transparent-theming`. Seven source pages remain on the 2026-06-23 verification and are
flagged in the header. Round 2 (reverse trace) has not started on any page.

- **The 500px inline height limit does not exist and never did as a published requirement.**
  Removed from `design guidelines_mcpapps_claude.md` (3 assertions),
  `remote_server_submission_guide.md` (1) and `structural_guideline_claude_vs_openai.md` (1).
  The live page states "Height: auto-fits to content"; the *Scrolling and gestures* section
  (new, not in any previous repo copy) explains the mechanism — the host caps and clips, with
  no published pixel value. This false constraint shaped at least two increments.
- **Mobile fullscreen IS supported.** Two repo docs said otherwise.
- **§9 Blocker 0 (title annotation) → RESOLVED**, and the duplicate false claim in §4A
  corrected. Verified in code and in the served `tools/list` on both platforms.
- **New in the source, now captured:** *Scrolling and gestures*; safe areas apply on web and
  desktop, not only mobile; `prefersBorder` defaults changed (unspecified = borderless on web,
  bordered on mobile) with a stated safe-area consequence; `baseUriDomains` in the CSP example.
- **Design guidelines duplication removed** from the submission guide — it is now a pointer.
  Duplicating a living upstream page into a second file is what produced the drift.

**Authentication page (§4C) — findings:**

- **§4C:141 is KNOWN FALSE and flagged inline.** *"static_bearer (user-pasted tokens) is
  not yet supported"* — the live page has no `static_bearer`; it has `static_headers`,
  org-admin-entered, **Beta**. Renamed + actor changed + promoted, or removed. Not
  PG-affecting (PG uses `oauth_dcr`), but it is a live false claim in this file.
- **§4C's obligations did NOT drift.** PKCE, the 401 handshake, resource matching,
  callbacks and refresh semantics all still match. The drift was in the capability
  inventory, not the requirement set — a distinction worth keeping, because an earlier
  draft of the artifact concluded "nothing in §4C was stale" and that was false.
- **§9's operational PRM check was fixed twice**: it fetched the pathless document (Claude
  probes the path-suffixed one first), and its trailing assertion compared `resource`
  against the bare origin rather than the full URL including path.
- **New artifact:** `authentication_claude_connectors.md` — 17 MUST requirements, 11
  verified against PG live and from source, 4 explicitly not verified.
- **Six items queued for the §4C rewrite**, including that CIMD selection needs `"none"`
  in `token_endpoint_auth_methods_supported` alongside the CIMD flag, and the DCR-at-scale
  warning. **PG is one metadata flag from CIMD** — it already advertises `"none"`.

### June 2026 Update (final — verified against official docs)
| Item | Previous | Correct (per official docs) |
|------|----------|----------------------------|
| Inline height | "Max 500px (mandatory)" | "Auto-fits to content, no nested scrolling. Host caps and clips overflow. No published px limit." |
| 4-5 data points | Listed as mandatory | Listed as "Constraint" — no "recommended" qualifier (earlier edit fabricating "recommended" was wrong) |
| Mobile fullscreen | "not yet available" | **Supported** — "App fills the entire screen with chat input and navigation bar overlaid" |
| Issue #61 widget rendering | "silently failing" | **RESOLVED** per owner confirmation |

**Correction notes:**
- The "500px hard limit" was from a stale/cached fetch; current official docs show "auto-fits to content" with no px value
- The "recommended" qualifier for 4-5 data points was fabricated and has been removed
- Mobile fullscreen IS supported per current official docs

### May 2026 Update
Item
Previous
Updated
OAuth spec
OAuth 2.0
OAuth 2.1 with PKCE S256; three registration options documented; DCR scaling warning added
title annotation
"Additional recommended"
Mandatory — listed in policy §5E alongside readOnlyHint and destructiveHint
Tool result size
"25,000 tokens" (all surfaces)
Claude.ai/Desktop: ~150,000 characters; Claude Code: 25,000 tokens
Timeout
Not documented
Claude.ai/Desktop: 300 seconds; Claude Code: configurable
IP range
"See docs.claude.com"
160.79.104.0/21 (documented explicitly)
Read/write split
Not documented
Catch-all tools rejected; must split read/write into separate tools
Custom query tools
Not documented
Must link to target API in description
Token refresh
Not documented
Reactive on 401 + proactive 5min before expiry; must return invalid_grant
Enterprise auth
Not documented
Single shared OAuth app per connector; no tenant isolation
static_bearer
Not documented
Not supported
Callback URL
Both .ai and .com listed
Official docs list only .ai; register both during transition
MCP Apps screenshots
Not documented
Mandatory for listing
Submission form fields
Partial
Full field list including branding, Skills/Plugins, allowed link URIs
Policy document name
"Anthropic MCP Directory Policy"
"Anthropic Software Directory Policy" (broader scope)
Hidden instructions
Not in policy
Policy §2G — explicitly prohibited
Claude memory access
Not in policy
Policy §1F — explicitly prohibited
ui/open-link URIs
Not documented
Must declare in submission form
Prompt injection patterns
Listed generically
Explicit list of rejected patterns from review-criteria page
Cross-service automation
Old policy item 30 — prohibited
Removed entirely from new policy — no longer an unsupported use case


