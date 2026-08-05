# Claude Compliance — AUDIT RECORD

**What this is.** How we know what the requirements are, what has been wrong before, and what is
still unverified. **It contains no requirements.** Those live in
`CLAUDE_COMPLIANCE_REQUIREMENTS_CANONICAL.md` — 121 rows, each with an obligation level and a
source line. The bytes those rows cite live in `sources_raw/`.

**Three files, no overlap:**

| File | Answers |
|---|---|
| `CLAUDE_COMPLIANCE_REQUIREMENTS_CANONICAL.md` | **What must be true.** Read before shipping or submitting |
| `sources_raw/` | **What the sources say.** The bytes every claim cites |
| **this file** | **How we know, and what was wrong before.** Read when something looks off, or at the next source refresh |

*Renamed and reduced from `COMPLIANCE_AUDIT_RECORD.md`, 2026-08-05: **128.9 KB → 81 KB**.
Removed: the requirement statements now in the canonical file, and the mechanism paraphrases of
`sources_raw/` (CSS token tables, the BroadcastChannel election protocol, SDK helper lists, the
full policy reproduction). Prior file recoverable from git at `65eab52`.*

⚠️ **On the size: this is deliberately over-retained.** A first extraction pass produced 61 KB and
**demonstrably lost content** — the `clientInfo` verification in §4C, because the pattern matched
blocks opening with `⚠️` but not with `✅`. Caught by a marker check against the old file. The
second pass used a wider net, which certainly re-captures some material that is duplicated
elsewhere. **Given that burying a block once already cost us the standing checks, and a narrow
pattern just cost us a second block, over-retention is the correct error.** Trimming further is a
task for someone reading it, not for a regex.

---

## Citation sweep of THIS file — run 2026-08-05

After the canonical file's X4–X8 rows were found citing **T-numbers from a deleted per-page
artifact** (standing check #15), this file was swept for the same hazard: it was built from those
same artifacts and carries raw line numbers throughout.

**14 distinct citations. 12 point at real content. 2 flagged, both false positives:**
- `design-guidelines` raw 186 — cites the *"Scrolling and gestures"* **section** by name. Citing a
  heading *as a heading* is correct.
- `(raw 41)` in the §4C `oauth_anthropic_creds` block — correct (`authentication`:41). **The
  sweep's own "nearest preceding filename" heuristic mis-attributed it**, which is a limitation of
  bare `(raw N)` citations: they depend on surrounding prose to resolve.

⚠️ **The hazard did not propagate here, and the reason is worth knowing:** this file's citations
were written **while reading the raw sources** during the correction work. The canonical file's
X-rows were **transcribed from an artifact's internal numbering**. Same source material, different
provenance, different failure rate — 0/14 here against 10/91 there.

---

# 1. STANDING CHECKS — first, because burying them once cost us the block

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
13. **When verifying a row against its source, mark it narrower / equal / BROADER — and only
    BROADER is a defect.** *(New 2026-08-05.)* A citation resolving proves the line exists; content
    verification proves the line says what the row claims; **neither catches the row saying MORE
    than the line does.** A row sharpened for readability — a "should" tightened, a qualifier
    dropped, a scope widened — passes both mechanical checks and is still wrong. Run on the 42
    `POLICY`/`TERMS` rows it found **four**, each dropping a qualifier or an exception: P2D
    ("intentionally"), P2E ("unless requested and intended by a user"), P3A (the
    collects-data-or-connects-remotely condition), P3F (the plugin exemption). **All nine hardening
    instances are the same failure at section level.** ⚠️ **Qualifiers live in the last clause of a
    sentence, which is what gets trimmed when a requirement is condensed into a row.**

17. **An obligation-level taxonomy answers "who requires this", never "what breaks if you don't."**
    *(New 2026-08-05.)* Those diverge, and the divergence is where readers mis-prioritise. M3 is
    correctly `RECOMMENDED` — the source says *"should"* — while the same paragraph says *"the user
    won't be able to interact with anything rendered outside the safe area."* **Soft language, hard
    consequence.** Nine rows carry `⚠️SILENT` in the canonical file: their violation produces **no
    error, no rejection and no log line** — the software simply does the wrong thing. Seven of the
    nine are NOT `POLICY` or `TERMS`. **A compliance document that grades only by who requires a
    rule will systematically under-rank the rules that fail quietly.**

16. **Any COUNT that changes is stated with what changed it, in the same commit.** *(New
    2026-08-05.)* Standing check #11 covers files; counts move independently of file sizes. A row
    total went 129 → "133" with no explanation, and the cause was **the counter, not the file** —
    a looser ID pattern swept in 7 defect-table rows and reported documentation as requirements.
    **State the pattern with the number (check #7) AND state what moved it (this one).**

15. **A resolving citation proves only that the file is long enough.** *(New 2026-08-05.)* Ten of
    91 rows cited a line that exists and says something else. **X4–X8 cited `transparent-theming`
    lines 16–19 and 52-54 — those were T-numbers from a DELETED per-page artifact**, carried across
    as if they were raw line numbers, pointing at blank lines, a heading and a code fence. They
    passed the citation check (the lines exist) and passed a reading of the row against "the
    source" — **because the source consulted was the row's own prose, not the line it names.**
    ⚠️ **Open the cited line. Every time.** When a row is built from an intermediate artifact, its
    numbering is the artifact's, not the source's, and nothing downstream can tell the difference.

14. **A reviewer reading files cannot tell which commit they correspond to.** *(New 2026-08-05,
    recorded at the reviewer's own request.)* A filesystem read returns bytes with no commit and no
    mtime, so every "verified" from a reading party is a claim about a byte state at an unknown
    point in the commit sequence. **Where the two disagree about a file's current contents,
    `git show <hash>:<path>` wins by construction.** This is not a rule so much as an honest
    statement of what each side's verification is worth — and it already produced one false defect
    report (the round-2 block reported stale after it had been fixed).

12. **A verification result is scoped to the version it ran against.** *(New 2026-08-05.)* Re-run
    the check, or restate its scope, **in the same commit as any content change.** A block reading
    *"121 rows, 0 unresolvable"* sitting above a file of 129 rows is not slightly stale — it is a
    **clean bill of health for eight rows that were never checked**, and it reads as current
    because it is specific. Fourth instance of a verification claim and its content moving in
    different commits: the master header, the §11 changelog, the currency metadata, and the
    canonical file's round-2 block.
11. **Every structural edit reports before/after BYTE AND LINE COUNTS FOR EVERY FILE IN THE WORKING
    TREE — not just the file being edited.** *(New 2026-08-05.)* Three structural edits produced
    three losses: the standing-checks block (deleted, survived two commits), the `clientInfo`
    verification (caught only because a marker check happened to be wider than the editing
    pattern), and `structural_guideline_claude_vs_openai.md` (deleted by a `git add -A` staging a
    working-tree removal nobody made — **mechanism still unknown**). **All three would have been
    one line of output.** A regex-driven edit on a large file loses content by default and only
    catches it when the checking pattern is wider than the editing pattern — which is luck, not
    method. This check does not depend on guessing the right pattern, and it catches the case where
    **the wrong file changes.**
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

---

# 2. UNSOURCED CLAIMS — real, load-bearing, and traceable to nothing

⚠️ **Found by the pre-shrink cross-check, 2026-08-05**, which is the reason that check was worth
running before deleting anything.

**COUNT CORRECTED — three genuinely unsourced, not six.** An earlier version of this note listed
six items. Two of them are **`[relay-only]`, not unsourced**: the **~150,000-character result
ceiling** and the **25,000-token `MAX_MCP_OUTPUT_TOKENS` limit** are stated verbatim on the
**`troubleshooting`** page — pasted but never committed. The **MCP Apps sandbox-spillover finding**
most likely belongs with them. **One paste converts all three from unsourced to captured**, which
is the clearest argument yet for getting those pastes committed.

**Genuinely unsourced — three:**

| Claim | Why it worries |
|---|---|
| **300-second timeout** (Claude.ai/Desktop) | A hard number with no source |
| **GA status required** — not beta, alpha or development | Stated as a gate; appears in no captured source |
| **"~30% of rejections are missing tool annotations"** | ⚠️ **The most quotable and least verifiable of the three** — a precise statistic with no provenance is the exact profile that produced the 500px myth, and a frequency figure invites planning decisions |

*(Attribution: the `troubleshooting` identification comes from the review chat's read of that page,
which is not in this tree. Confirm when it is pasted.)*

They almost certainly came from the June 2026 verification against pages never re-captured, or from
`remote_server_submission_guide.md` (deleted 2026-08-05, recoverable at `e9d0777`).

**Preserved verbatim rather than deleted.** Per the canonical file's own rule — *if it cannot be
traced to a line in `sources_raw/`, it does not go in* — they cannot become rows until a source is
captured. ⚠️ **Do not cite them as requirements until then.** Several are specific enough to be
believed on sight, which is exactly the shape of the 500px myth.

**To resolve:** capture a limits/technical-constraints page (result sizes, timeouts), whatever
states GA status, and the source of the rejection-frequency figures.

1. Supported Claude Platforms
All major Claude platforms support remote MCP connectors:

Claude.ai (web) — Full support with OAuth
Claude Desktop — Full support with OAuth
Claude Code — Direct connection from user's machine (with OAuth support)
Claude API — Integration support
Claude Mobile apps — Connector support
Cowork — Connector support (uses same OAuth callback as Claude.ai)

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

4E. Firewall and IP Allowlist
For servers behind firewalls, allowlist Anthropic's outbound IP range: 160.79.104.0/21

⚠️ UPDATE May 2026: The actual CIDR range 160.79.104.0/21 is now documented in the official authentication page. Previous versions of this document only said "see docs.claude.com/en/api/ip-addresses" without the actual range.

Required for: Claude.ai and Claude Desktop
Not required for: Claude Code (connects directly from user's machine)
IP allowlisting alone is not recommended as a security measure — use OAuth 2.1

> ⚠️ NEW — Origin-header validation: Your MCP server must also validate the `Origin` header on incoming requests. This is listed as a technical requirement in the submission form policy checklist alongside OAuth, HTTPS, and annotations. Servers that accept requests without validating the `Origin` header fail the security review.

4G. Production Readiness
Server must be in General Availability (GA) status.

Not marked as "beta," "alpha," or "development"
All features fully implemented and tested
Proper error handling — every tool must return a successful response with valid parameters; generic errors ("Internal Server Error" with no detail) fail review
Actionable error messages — validate inputs and return actionable messages, not silent failures
Scalable infrastructure and monitoring

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

7. Common Rejection Reasons (ranked by frequency)
Missing tool annotations (~30% of rejections) — Every tool must have readOnlyHint OR destructiveHint AND title. Fix all tools before submitting.

OAuth callback URL errors — Missing https://claude.ai/api/mcp/auth_callback. Also ensure Claude Code loopback URIs support port-agnostic matching.

Catch-all API tools — A single tool with method parameter accepting GET and POST is rejected. Split read/write into separate tools.

Incomplete documentation — Missing examples, unclear setup, missing required sections. Minimum 3 detailed examples with user prompt + what happens + expected output.

Production readiness — Server marked as "beta" or shows instability. Must be GA status.

Missing or inaccessible privacy policy — Immediate rejection. Verify URL is live before submitting.

Generic error messages — "Internal Server Error" or "Bad Request" with no detail fails functional review. Reviewers call every tool with valid parameters.

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

---

# 3. CORRECTION HISTORY EMBEDDED IN THE REQUIREMENT SECTIONS

These blocks lived inside sections that were otherwise duplicates of the canonical file. **A
section-level delete would have destroyed them** — which is exactly how the standing-checks block
vanished and survived two commits. Extracted block by block, 65 of them.

**From §2 (Submission Types):**

⚠️⚠️ BLOCKER — ACCESS GATE. ADDED 2026-08-04. READ BEFORE PLANNING ANY SUBMISSION WORK.

---

**From §2 (Submission Types):**

purchase decision. ⚠️ CHECK CURRENT TEAM PRICING AND ANY MINIMUM-SEAT REQUIREMENT FIRST; if a
seat minimum exists, that number is the real cost of submitting. NOT VERIFIED HERE — pricing was
not checked and must not be assumed.
Desktop extensions (MCPB): http://clau.de/desktop-extention-submission

---

**From §4A (Safety):**

⚠️ UPDATE May 2026: title is now explicitly mandatory per policy §5E: "MCP servers must provide all applicable annotations for their tools, in particular readOnlyHint, destructiveHint, and title." Previous versions of this document listed title as "additional recommended." Incorrect — it is required. Missing tool annotations account for ~30% of all rejections.

---

**From §4A (Safety):**

✅ RESOLVED — verified in code 2026-08-04. `ToolDefinition` declares `title: str` as a REQUIRED field (`mcp_server/priority_guardian/tools/base.py:39`), every tool in TOOL_REGISTRY supplies one, and every tool carries a title in the served `tools/list` payload on BOTH platforms. See §9 Blocker 0.

---

**From §4C (OAuth):**

⚠️ UPDATE May 2026: The policy text says "OAuth 2.0." However, Claude's implementation and the MCP authorization spec require PKCE S256, which aligns with OAuth 2.1 behavior. Correct framing: "OAuth 2.0 authorization code flow with PKCE S256 support, as required by Claude's auth implementation and the MCP authorization spec." Advertising "code_challenge_methods_supported": ["S256"] in your authorization server metadata is mandatory — if absent, Claude will refuse to proceed.

---

**From §4C (OAuth):**

*[Changelog 2026-08-04: this table previously carried a line reading "static_bearer (user-pasted
tokens) is not yet supported." That was false on all three counts — wrong name, wrong actor, wrong
availability — and is replaced by the `static_headers` row above. The interim "KNOWN FALSE" flag
that stood here has been removed with the claim it flagged; keeping a warning about a deleted
sentence is its own kind of stale.]*

---

**From §4C (OAuth):**

⚠️ **`oauth_anthropic_creds` credentials are bound to the authorization server that issued them**
(raw 41). Migrating to a new AS requires emailing `mcp-review@anthropic.com` with the new
`client_id` and `client_secret` **before cutting over**. CIMD has no such constraint — a CIMD
`client_id` is a self-hosted URL that works against any AS that fetches it.

---

**From §4C (OAuth):**

**Enterprise Managed Auth** (raw 120) — ⚠️ **SOURCE UNCAPTURED.** SSO organizations can connect
their users **without an interactive OAuth consent step**, using an identity assertion signed by
their identity provider. The linked page (`building/enterprise-managed-auth`) describes what the
authorization server must support and **has not been captured**. Recorded as a known gap, not
omitted.

---

**From §4C (OAuth):**

Anthropic-held credentials at all** — it runs its own OAuth flow with its own CIMD. ⚠️ **§1 of this
file lists six platforms and does not mention Managed Agents.** Recorded as an inventory gap.

---

**From §4C (OAuth):**

⚠️ **Obligation level, stated precisely.** The **display** requirement is unconditional; only the
**warning** carries the loopback condition. But it is the **MCP spec** requiring it, surfaced on
Anthropic's page — **not** an Anthropic-enumerated directory criterion. Checked against both
authorities: `review-criteria` never mentions consent screens or redirect URIs, and
`software-directory-policy` contains exactly one authentication clause (§5D, *"secure OAuth 2.0
with certificates from recognized authorities"*), which does not incorporate the spec's display
requirement. **Open security item, post-submission. Not a submission gate.**

---

**From §4C (OAuth):**

  PG already sends scope="pg.access" ✅ — the good case, now with a stated reason.

---

**From §4C (OAuth):**

⚠️ **A18 — REDIRECT URI HOSTNAME ON THE CONSENT SCREEN. PG DOES NOT SATISFY THIS.**
**Unmet spec-inherited MUST — directory-gating status UNKNOWN.**
(Found in round 2, 2026-08-04; missed by round 1. Raw source line 106. Code fix NOT applied.)

---

**From §4C (OAuth):**

⚠️ An earlier draft said the value sat *"one line away"* and called this *"display, not plumbing."*
**Both oversold it.** The existing `urlparse(redirect_uri).netloc` lives in `consent_ui.py` on the
**post-consent redirect path**, feeding a log line — a different module and a different request
phase, with nothing reusable. `redirect_uri` *is* in scope at the render site (`authorize.py:770`),
but nothing computes its `netloc` and nothing passes it. The fix is **an add, not a move**: one
computation plus one context entry in `authorize.py`, plus markup in all eight templates.

---

**From §4F (Documentation):**

⚠️ FOURTH INSTANCE OF THE HARDENING BIAS TODAY, AND THE MOST COSTLY. This file said "Required
sections". The source said "RECOMMENDED sections", and carried its own proof inline.

---

**From §4K (MCP Apps Design):**

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

---

**From §4K (MCP Apps Design):**

  ⚠️ **CORRECTION 2026-08-04 — the earlier claim here was true and misleading, and the remedy
  it implied does not work.** This block previously read: *"grep confirms no fullscreen-scoped
  override of the cap exists anywhere in the widget's CSS."* Literally true. Substantively wrong:
  **there is a fullscreen-scoped override — it is a JSX inline style object, and the grep scope
  was `.css` files.** Same shape as the `resourceDomains` third block and the §4A `title` claim:
  checked where I was looking.

---

**From §4K (MCP Apps Design):**

⚠️ 7th hardening instance. Labelled "(mandatory)" with no basis. The design-guidelines source
contains exactly THREE "must" statements in the whole page — mobile WebView constraints (raw 128),
light/dark theming (raw 204) and WCAG AA accessibility (raw 278). NONE concerns fullscreen. These
are design recommendations.
- No floating panels — use collapsible sidebars, tabs, or pagination
- App provides its own fullscreen button; close button appears in native header
- Composer always visible — design UX to work with it

---

**From §4K (MCP Apps Design):**

  ⚠️ **This is one decision with two consequences, not two independent recommendations.**
  transparent-theming recommends `false` for portability and is silent on the mobile consequence;
  design-guidelines states the consequence. The pages are consistent — one is incomplete alone.
  Choosing `false` buys portability and **costs the mobile card padding**, after which honouring
  `safeAreaInsets` is no longer optional.
  For carousels: apply `safeAreaInsets.left`/`.right` as **`scroll-padding-inline`** on the scroll
  container, so items at rest sit clear of the device edges but can scroll underneath them.

---

**From §4K (MCP Apps Design):**

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

---

**From §4K (MCP Apps Design):**

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

---

**From §4K (MCP Apps Design):**

⚠️ resourceDomains ALSO ADDS THE LISTED ORIGINS TO script-src AND style-src, so keep it to origins
trusted to serve executable code; prefer bundling third-party fonts into the widget over
allowlisting public CDNs (transparent-theming.raw.md:52-54).

---

**From §4K (MCP Apps Design):**

⚠️ THIS BLOCK PREVIOUSLY READ "mandatory for MCP Apps" AND "required on every ui:// resource.
Without it the widget will not render." BOTH CLAIMS ARE FALSE. The page never says the field is
required; it says the format and validation rules "are determined by each host platform" and then
gives Claude's formula. That is a conditional: IF you set it, here is the value.

---

**From §4K (MCP Apps Design):**

⚠️ FIFTH HARDENING INSTANCE IN ONE SESSION, AND THE FIRST WITH A DESIGN CONSEQUENCE. PG's FIXED
ui.domain is exactly what widens BroadcastChannel scope ACROSS CONVERSATIONS, which is why §4M
records S5 (a server-minted per-conversation scope key) as a PRE-CONDITION for supersession. If
ui.domain is optional, DROPPING IT GIVES PER-CONVERSATION SCOPING FOR FREE AND DELETES S5. The
false "mandatory" framing removed that option from consideration without anyone deciding against
it. The other four inflations produced wasted effort; this one silently foreclosed a design choice.

---

**From §4K (MCP Apps Design):**

  ⚠️ That page is NOT yet in sources_raw/ — the quotation comes from Nadja's read, not from a
  committed source. Confirm it when troubleshooting is pasted.

---

**From §4K (MCP Apps Design):**

⚠️ AN EARLIER VERSION OF THIS BLOCK GAVE A WEAKER REASON — that a fixed domain keeps the origin
stable "for anything relying on localStorage". That argument FAILS TWICE for PG: the supersession
page's localStorage caching is keyed on hostContext.toolInfo.id and exists to survive REMOUNT
WITHIN a conversation, for which per-conversation origin stability is already sufficient; and PG
implements neither supersession nor localStorage caching, so it does not reach PG at all. The
correct reason had already been surfaced in the same session and was passed over. Substituting a
weaker justification for a stronger one already in hand is its own failure mode — the answer was
in the conversation, not only in the tree.
For Claude, compute the value by hashing your full MCP resource URL (including /mcp path):

---

**From §4K (MCP Apps Design):**

PG status: domain computed from https://mcp.priority-guard.com/mcp → a7b31ccb44096357600a7460eb0a78e9.claudemcpcontent.com. Confirmed working ✅ (hash recomputed locally 2026-08-04 — CORRECT for the canonical URL.)

---

**From §4K (MCP Apps Design):**

⚠️ A SECOND, DIFFERENT PG HASH EXISTS IN THIS REPO: e524d9efa639471cac7431657ac08f2c, at
remote_server_submission_guide.md:445 and structural_guideline_claude_vs_openai.md:388-389. It is
arithmetically correct for the LEGACY URL https://priority-guardian-claude-mcp.onrender.com/mcp and
is therefore STALE. Neither doc did bad arithmetic; one names a superseded URL.

---

**From §4K (MCP Apps Design):**

⚠️ AND THE URL MUST BE EXACT. Recomputed 2026-08-04 — three trivially-confusable spellings of PG's
own URL produce three values sharing NOTHING:

---

**From §4K (MCP Apps Design):**

⚠️ LOCAL stdio CONNECTORS HAVE NO URL, so there is nothing to hash — OMIT the _meta.ui.domain
field entirely rather than inventing a value. Added 2026-08-05. (PG is remote and unaffected;
recorded because the formula reads as universal.)

---

**From §4K (MCP Apps Design):**

⚠️ MISSING FROM THE LIST BELOW, present in design-guidelines.raw.md:
  ghost variants     — color-background-ghost (raw 293), color-text-ghost (304),
                       color-border-ghost (315)
  disabled variants  — color-background-disabled (298), color-text-disabled (309),
                       color-border-disabled (320)
  color-border-inverse (raw 314)
  the FULL RING GROUP — color-ring-primary, -secondary, -inverse, -info, -danger (raw 322-326)
  the heading size scale with line-heights

---

**From §4K (MCP Apps Design):**

⚠️ NOTE: The -solid suffix tokens (e.g. --color-background-success-solid, --color-background-info-solid)
are NOT in the official token table. These appear to be internal/undocumented tokens. Use with caution.
Consider using the official non-solid equivalents as fallbacks.

---

**From §4K (MCP Apps Design):**

✅ PG FALLBACK VALUES — corrected (verified 2025-05-30):
- color-text-tertiary:         #73726C ✓
- color-text-secondary:        #3D3D3A ✓
- color-background-secondary:  #F5F4ED ✓
All PG fallbacks now match official values.

---

**From §4K (MCP Apps Design):**

⚠️ THE PROCEDURE FOR THE TOOL-EXERCISE ATTESTATION IS DOCUMENTED. building/testing is CAPTURED at
sources_raw/testing.raw.md (fetch-only, undated). It states that ANY Claude account — Free, Pro,
Max, Team or Enterprise — can add a custom connector, and that custom connectors use THE EXACT SAME
RUNTIME as directory connectors. So the attestation work is NOT gated behind the Team/Enterprise
requirement in §2; only the portal itself is. There is no staging environment: testing happens in
production as a custom connector, or through a tunnel for a local server.

---

**From §4K (MCP Apps Design):**

✅ B7 IS NOT GATED BY THE TEAM PLAN. FOUND 2026-08-04 on building/testing, raw line 13:
  "ANY CLAUDE ACCOUNT (Free, Pro, Max, Team, or Enterprise) CAN ADD A CUSTOM CONNECTOR... CUSTOM
   CONNECTORS USE THE EXACT SAME RUNTIME AS DIRECTORY CONNECTORS, so what works here will work
   after publication."

---

**From §4K (MCP Apps Design):**

⚠️ TEST CREDENTIALS — AN OBLIGATION NOBODY HAD RECORDED. Beyond "fully populated account, not an
empty shell" so reviewers can "list real records, search real data, exercise write tools on real
resources", the page requires: "INCLUDE STEP-BY-STEP SETUP INSTRUCTIONS FOR SOMEONE UNFAMILIAR
WITH YOUR SERVICE." A written deliverable, not just an account.

---

**From §4K (MCP Apps Design):**

✅ clientInfo — PG IS CLEAN, verified 2026-08-04. Claude's clientInfo name varies ("claude-ai",
"Anthropic" sometimes with a service suffix, "claude-code"); behaviour must NOT be gated on an
exact name or version; and it is UNAUTHENTICATED — "any client can claim any name, so IT MUST
NEVER FEED AN AUTHORIZATION DECISION." grep across mcp_server/ and backend/ finds no use of
clientInfo; the only match is a URL in a comment. NOTE: this is the SAME CLASS as open task #10
(client-controlled _meta["openai/subject"]) — unauthenticated client-supplied data reaching an
authorization decision. PG is clean here and NOT clean there.

---

**From §4K (MCP Apps Design):**

⚠️ B7 IS AN ATTESTATION, NOT A PROCESS STEP. ADDED 2026-08-04.
The portal states: "You also confirm you've run every tool yourself, either via MCP Inspector or
as a custom connector in Claude." That is a CHECKBOX YOU TICK, and Software Directory Terms T-3
warrants that "any information you give us will be accurate and up-to-date."

---

**From §4M (Widget Instance):**

⚠️ THIS ENTIRE SECTION DESCRIBES A PATTERN, NOT AN OBLIGATION. Verified 2026-08-04 against the
committed raw source: the page contains NO directory-compliance requirement. Its language is
uniformly optional — "should remain interactive", "You can use BroadcastChannel", "should also
handle", "recommended for production". Everything below is binding only IF the pattern is
implemented. Do not brief an increment from this section as though it were gating.

---

**From §4M (Widget Instance):**

⚠️ THE VERDICT ABOVE IS RIGHT AND ITS SCOPE IS WRONG. Corrected 2026-08-04.

---

**From §4M (Widget Instance):**

⚠️ PG HAS A FIXED ui.domain, AND THE SCOPE RULE BELOW APPLIES TO PG DIRECTLY.
resources_dupl.py:75 defines WIDGET_APP_DOMAIN = f"{_hash}.claudemcpcontent.com" and sets it on
ALL THREE _meta.ui blocks (:90, :114, :148). Per the source: with a fixed ui.domain "the origin
is shared across every conversation and tab for your connector. A fixed channel name would let a
widget in one conversation supersede a widget in another." Neither hostContext nor the tool-call
arguments carry a Claude-provided conversation ID.

---

**From §4M (Widget Instance):**

- PG status: uses useApp() React hook — correct. ✅

---

**From §4M (Widget Instance):**

  ⚠️ CORRECTED 2026-08-04. This line read "required for production" and the heading read
  "SDK App class requirement". The source says "recommended for production" (raw line 240).
  Harmless in effect — PG uses useApp() — but the line would mislead anyone reading §4M for
  what is mandatory.

---

**From §4M (Widget Instance):**

  ⚠️ THIRD INSTANCE OF THE SAME FAILURE IN ONE DAY, after the 500px "hard limit" and the
  fabricated "recommended" qualifier on the 4-5 data-point constraint. Two inflated a
  recommendation into a MUST; this one does too. THE BIAS HAS A DIRECTION: soft language gets
  hardened, hard language never gets softened. Recorded as a bias, not three corrections,
  because the direction is what produces over-constrained increments and wasted work.

---

**From §4N (Transparency):**

⚠️ THIS SECTION IS NOT OPTIONAL POLISH. It is the MECHANISM FOR DISCHARGING M1 — "All views must
support both light and dark themes. Use the host's style tokens — they automatically adapt. NEVER
HARDCODE COLORS." (design-guidelines.raw.md:204.) That is one of only TWO developer obligations
stated with "must" on the entire design-guidelines page, and it is recorded in §4K. The techniques
below — applyDocumentTheme, applyHostStyleVariables, the useHostStyles hook, token-based CSS with
light-dark() fallbacks — are how M1 is satisfied. Read this section as compliance, not styling.
Source: https://claude.com/docs/connectors/building/mcp-apps/transparent-theming

---

**From §4N (Transparency):**

  it regardless. ⚠️ unverified, low risk.

---

**From §4N (Transparency):**

  PG status: ✅ correct — App.tsx:166 is `useHostStyles(app, app?.getHostContext())`,
  TWO args, with the comment "must pass hostContext for dark mode".
  ⚠️ This line previously read "uses useHostStyles(app)" — the ONE-ARG form this very
  section warns against. The verdict was right and the evidence was false; an audit line
  whose supporting evidence is wrong is worse than no line. Corrected 2026-08-04.

---

**From §4N (Transparency):**

⚠️ HOST FONTS ARE PAID FOR AND NEVER USED (found 2026-08-04, code fix NOT applied)

---

**From §4N (Transparency):**

  So T3 ✅ is TRUE AND HOLLOW. The CSP allowance is granted and the security surface widened
  (resourceDomains also feeds script-src and style-src — the page's own caveat), and the widget
  renders in system-ui regardless. PG pays the cost and takes none of the benefit.

---

**From §4N (Transparency):**

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

---

**From §4O (MCP Apps Technical):**

  PG status: uses useApp() React hook — correct. ✅

---

**From §4O (MCP Apps Technical):**

  PG status: autoResize: true is set — height is driven by content. ✅

---

**From §5 (SUBMISSION PORTAL):**

*[Changelog 2026-08-05: this section previously listed the fields of the OLD SUBMISSION FORM, with
a supersession notice bolted on top. The form does not exist for remote MCPs. The old field list is
REPLACED, not annotated — a superseded list under a warning is still a list people fill in.]*

---

**From §5 (SUBMISSION PORTAL):**

STEP 2 — CONNECTION. Server URL must be https://. ⚠️ The exact string entered here is one of the
three that must agree; see the three-way URL match in §8.

---

**From §5 (SUBMISSION PORTAL):**

  URL SLUG      ⚠️ PERMANENT ONCE PUBLISHED. See §12 — it becomes
                https://claude.ai/directory/connectors/SLUG, a public URL used in marketing and in
                any "Connect to Claude" button. Display names can change; the slug cannot.

---

**From §5 (SUBMISSION PORTAL):**

  ⚠️ THIS STEP CARRIES AN ATTESTATION, NOT A SUGGESTION: "You also confirm you've run every tool
  yourself, either via MCP Inspector or as a custom connector in Claude." Terms T-3 warrants that
  all information given to Anthropic is accurate, so ticking it without having exercised every
  public tool is a WARRANTY DEFECT. See §8.

---

**From §5 (SUBMISSION PORTAL):**

SKILLS ARE NOT A STANDALONE SUBMISSION TYPE — bundle them in a plugin. *[Changelog 2026-08-04: an
"Optional: Skills & Plugins" entry stood here and was wrong.]*

---

**From §6 (Anthropic Software Directory Policy):**

⚠️ The publication date comes from Nadja's PASTE of the rendered page. The .md fetch carries NO
date, so this date cannot be recovered from the raw file — see the provenance table in the header.

---

**From §6b (ANTHROPIC):**

⚠️ Date from Nadja's PASTE; the .md fetch carries none.
*[Moved 2026-08-05 from "4F-bis", where it had been appended for convenience. It sits after §6
because the Policy and the Terms are the two binding documents and belong together — §6 is what
the Software must do, §6b is what you WARRANT when you submit.]*
Source: https://support.claude.com/en/articles/13145338-anthropic-software-directory-terms
Dated 16 March 2026. Raw: sources_raw/software-directory-terms.raw.md
Full extraction: CLAUDE_COMPLIANCE_REQUIREMENTS_CANONICAL.md §6 (T1-T10).

---

**From §6b (ANTHROPIC):**

⚠️ THIS DOCUMENT HAD NO REPO COPY OF ANY KIND UNTIL 2026-08-04. §6 reproduces the POLICY in full
and never mentioned the TERMS — while Policy §3H makes agreeing to them MANDATORY. The Policy says
what the Software must do; the TERMS are what you WARRANT when you submit.

---

**From §6b (ANTHROPIC):**

     copy. ⚠️ The Trademark Guidelines are a SECOND referenced binding document and are NOT in the
     repo — .md returns 404 and the HTML is a Next.js bundle. NEEDS A PASTE. Recorded as an
     obligation whose CONTENT IS UNKNOWN.

---

**From §6b (ANTHROPIC):**

⚠️ THE ART. 28 ERROR IS NOW A WARRANTY DEFECT, NOT LEGAL HYGIENE. Privacy policy v3.2
characterises Anthropic as an Art. 28 data processor, which is incorrect. Under T-3 it is
inaccurate information given to Anthropic; under T-4 it is a policy that does not "clearly and
accurately describe" the third-party relationship. It moves from "should fix" to FIX BEFORE THE
FORM GOES IN. It is cheap, and it is the one document Anthropic is guaranteed to read closely.

---

**From §8 (Pre-Submission):**

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

---

**From §12 (POST-PUBLICATION):**

Source: building/after-publishing. ⚠️ RELAY-ONLY, NO ARTIFACT — this page has no raw file in
sources_raw/. Recorded because it materially changes how reversible submission decisions are, but
it is the weakest provenance category in this document. See sources_raw/PROVENANCE.md.

---

**From §12 (POST-PUBLICATION):**

⚠️ CAVEAT, AND IT IS NOT SMALL. Software Directory Policy states Anthropic conducts "both initial
and ONGOING reviews", and Terms T-8 obliges continued maintenance of standards consistent with the
policy AS UPDATED. "No scheduled re-review" is NOT "never reviewed again". This is latitude for
iteration, not a gap to ship through.

---

**From §12 (POST-PUBLICATION):**

which changes can be made directly and which require review. ⚠️ UNCAPTURED — not fetched, not
pasted. It is a separate page, not a rename of after-publishing.

---

**From §4C (OAuth) — the lazy-authentication delta, added by the marker check:**

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

---

# 4. 9. PG-Specific Compliance Blockers (Claude Submission)

PG STATUS AGAINST THE CANONICAL REQUIREMENTS — moved here 2026-08-05.

⚠️ This table lived in CLAUDE_COMPLIANCE_REQUIREMENTS_CANONICAL.md as a "PG status" column and was
removed. That file is an EVALUATION INSTRUMENT — the questions, not the answers. A requirements
document carrying its own verdicts stops working as an instrument: the reader sees a verdict instead
of a criterion, and the verdict goes stale while the criterion does not. Per-app status belongs
here, in the audit record.

RECORDED STATUS, NOT A WORK LIST. Nothing below is assigned; deciding whether to act is separate.

Coverage of the 121 rows: 35 verified · 17 findings · 45 not assessed ·
the remainder n/a or recorded-as-accepted. NOT ASSESSED IS THE DEFAULT AND THE CORRECT ANSWER where
the audit established nothing.

VERIFIED (35)

| Req | Evidence |
|---|---|
| **P1F** | ✅ verified — **pattern and scope stated:** `grep -rniE "conversation_(history\|summary)\|chat_history\|claude_memory\|user_files\|conversation_summar"` over `mcp_server/**/*.py` and `backend/**/*.py`, excluding tests → **0 matches**. ⚠️ *Bounded by the pattern: this proves no identifier-level match, not that no such access exists under a name the pattern misses* |
| **P3F** | ✅ verified — first-party backend; `mcp.priority-guard.com` matches the service |
| **P4A** | ✅ verified — PG does none of this |
| **P4B** | ✅ verified — PG generates no media |
| **P4C** | ✅ verified — PG carries none. **Absent from `review-criteria`; binding only via the policy** |
| **P5C** | ✅ verified — 8/8 public tools; longest served is `delete_my_priority_guardian_data` at **32** |
| **P5D** | ✅ verified — OAuth 2.0 + PKCE S256, TLS on both hosts |
| **P5E** | ✅ verified on the **Claude serving surface** — all 8 public tools carry a title and at least one hint. `title` is structurally guaranteed (required positional field on `ToolDefinition`). ⚠️ `create_priority` is `destructive_hint=False` in the **shared registry** and overridden to `True` for Claude in `tools_list_dupl.py` — **audit the serving path, not the registry** |
| **R1** | ✅ verified — purpose-built tools, no catch-all with a `method` parameter; writes already split by action type |
| **A1** | ✅ verified |
| **A2** | ✅ verified — live AS metadata |
| **A3** | ✅ verified live — `HTTP/2 401`, `resource_metadata=…`, `scope="pg.access"` |
| **A4** | ✅ verified — `https://mcp.priority-guard.com/mcp` |
| **A5** | ✅ verified — single entry |
| **A6** | ✅ verified |
| **A8** | ✅ verified — both `.ai` and `.com` variants registered |
| **A9** | ✅ verified against Claude Code's **published CIMD** — both accepted, port-agnostic, negative controls rejected |
| **A10** | ✅ verified live — token endpoint returned `invalid_grant` |
| **A11** | ✅ verified |
| **A12** | ✅ verified live — form body parsed, 400 `invalid_grant`, **not 415** |
| **A13** | ✅ verified indirectly — JSON to `/token` returns 422, confirming the split |
| **A15** | ✅ verified — not implemented |
| **A16** | ✅ verified — bearer header only |
| **A22** | ✅ verified — PG returns a transport-level 401 |
| **A23** | ✅ verified — PG sends `scope="pg.access"` |
| **M11** | ✅ verified — declared on all three `_meta.ui` blocks |
| **M12** | ✅ verified — `['inline','fullscreen']` |
| **X1** | ✅ Set deliberately — PG's widget runs its own OAuth flow (`openLink` to a Google connect URL). **Accepted cost:** origin shared across conversations |
| **X2** | ✅ verified — computed at import from `MCP_RESOURCE_URL`; `https://mcp.priority-guard.com/mcp` → `a7b31ccb…` |
| **X4** | ✅ verified — `main.css:8-15` |
| **X5** | ✅ verified — in the Vite build input **and** the served artifact |
| **L1** | ✅ PG calls `openLink` |
| **L2** | ✅ verified — the target is `BACKEND_PUBLIC_URL` (`https://www.priority-guard.com`), a domain PG owns; **not** `accounts.google.com` |
| **S3** | ✅ verified |
| **S4** | ✅ verified — 8/8 public tools; nothing lands in the un-annotated group |

FINDINGS (17)

| Req | Finding |
|---|---|
| **P1D** | ⚠️ `record_widget_diagnostic` accepts an open `data` object (`additionalProperties: true`). No violation evidenced — its only caller is the ChatGPT widget sending event names and user-agent — but the schema is not the guarantee; call sites are. **Not called from the Claude path** |
| **P2B** | ⚠️ `inspect_adapt`'s description says it **records** confirmed action steps; the handler persists nothing (332 lines, zero backend calls, docstring *"validate provenance → return success"*). **Recorded finding. Descriptions are shared with the live ChatGPT app and are not touched.** |
| **R6a** | ⚠️ Three of eight public descriptions carry override language (`BINDING RULES`, `SUSPENDED`, `default behavior`): `create_priority`, `inspect_adapt`, `onboarding_calendar_setup`. Five are clean. **Recorded. Not changed.** |
| **P3A** | ⚠️ Published, but still routes PG full deletion to `support@priority-guard.com`, which is wrong now the deletion tool ships. Separately: v3.2 characterises Anthropic as an **Art. 28 processor**, which is incorrect — see T3/T4 |
| **P3C** | ⚠️ No Claude-specific documentation page exists |
| **DOC1** | ⚠️ Not created. **There is no seven-section requirement in any binding document** |
| **R11** | ⚠️ Only `delete_my_priority_guardian_data` has been exercised end to end. See S12 — this is attested to in the portal |
| **T3** | ⚠️ The privacy policy's **Art. 28 characterisation of Anthropic is incorrect** — inaccurate information given to Anthropic |
| **T4** | ⚠️ PG connects to Google Calendar, so **Google's policy must be provided**, not merely disclosed around. Not verified. Compounded by the Art. 28 error |
| **T9** | ⚠️ **Appears unimplemented.** Distinct from P3B, which is a *user support* channel — T9 names Anthropic and third parties and adds a **duty of care** |
| **A18** | ⚠️ **Not satisfied.** None of the eight `oauth_consent_*.html` templates render it. **NOT A DIRECTORY GATE** — absent from `review-criteria` and from the binding policy. Open security item, post-submission |
| **M3** | ⚠️ Applied only under `platform === 'mobile' && hostFullscreen`; horizontal padding hardcoded 16px, so `.left`/`.right` are unused |
| **M10** | ⚠️ **Four layered width caps**, outermost smallest: `#root` 600px (binds), inline `<main>` 560px (binds), fullscreen `<main>` 672px (**dead**), pie section 672px (**dead**). Compliant inline; **in fullscreen the cap binds and auto margins produce the artifact M10 names** |
| **M14** | ⚠️ Set `false` on all three blocks → borderless on mobile too, while `safeAreaInsets.left`/`.right` go unapplied. **One decision with two consequences** |
| **X6** | ⚠️ Granted on all three blocks but **hollow** — no `--font-*` variable is referenced anywhere in the widget, so the CSP is widened for a capability not exercised |
| **S1** | ⚠️ **BLOCKS SUBMISSION.** Not an engineering task |
| **S12** | ⚠️ **Cannot be ticked truthfully today** — 1 of 8 public tools exercised end to end. Ticking it is a **warranty defect**, not a process shortcut |

NOT ASSESSED (45): P1A, P1B, P1C, P1E, P2A, P2C, P2D, P2E, P2F, P2G, P3B, P3D, P3E, P3G, P3H, P5A, P5B, P5F, R7a, T1, T2, T8, T10, A7, A14, A19, M1, M2, M4, M5, M6, M7, M8, M9, M15, X7, L3, L7, S2, S5, S6, S7, S8, S9, PUB3


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

---

# 5. 11. What Changed From Previous Version

### 2026-08-05 (d) — Consolidation DONE: 15 files -> 5

**Measured before:** `doc/Claude_Compliance/` held **15 files at 368 KB**, up from **6 files at
149 KB** when this pass began. Consolidation was the goal and the count had gone the wrong way.
**Now 5 files** plus `sources_raw/`.

**Coverage was verified BEFORE anything was removed** — the check I had said must happen first:
`CLAUDE_COMPLIANCE_REQUIREMENTS_CANONICAL.md` carries **121 requirement rows** covering every ID in
every removed artifact. The apparent gap (`R3`-`R10` absent as R-IDs) is **deduplication, not loss**:
per the increment briefing, where two pages state one obligation there is one row citing both
sources — R3->P5E, R4->P5C, R5->P2B, R6->P2D-P2G + R6a, R7->P5A + R7a, R8->P3F, R9->P4A/P4B,
R10->P3D/DOC1/S10/S11. Each cites `review-criteria` alongside the policy.

**REMOVED — nine files. Recoverable from git at `261a621`, the commit before this one.**

| Removed | Its content now lives in |
|---|---|
| `authentication_claude_connectors.md` | canonical §7 (A1-A24) · §4C of this file |
| `review_criteria_claude.md` | canonical §1-§5 (R rows deduplicated into P rows) |
| `design guidelines_mcpapps_claude.md` | canonical §8 (M1-M15) · §4K of this file |
| `transparent_theming_mcpapps_claude.md` | canonical §9 (X4-X8) · §4N of this file |
| `cross_compatibility_mcpapps_claude.md` | canonical §9 (X1-X3) · §4K of this file |
| `instance_supersession_mcpapps_claude.md` | §4M of this file (the page creates **no** obligation, so it has no canonical rows) |
| `software_directory_policy_claude.md` | canonical §1-§5 (P rows) |
| `software_directory_terms_claude.md` | canonical §6 (T1-T10) · §6b of this file |
| `software_directory_policy.md` | **stale duplicate** — the copy that carried *"Updated this week"*. `sources_raw/software-directory-policy.raw.md` is the bytes; §6 of this file is the reproduction |

**THREE COPIES OF THE POLICY ARE NOW ONE.** That was the exact condition `doc/README.md` warns
about — *"two documents describing the same thing will diverge"* — and they already had.

**MOVED:** `inc_claude_Requirements.md` -> `doc/`. An increment briefing does not belong in a
compliance folder; briefings live alongside `inc_compliancedoc_hygiene.md`.

**KEPT, each with a distinct job:**

| File | Job |
|---|---|
| `CLAUDE_COMPLIANCE_REQUIREMENTS_CANONICAL.md` | **What must be true.** Read this to ship or submit |
| `COMPLIANCE_AUDIT_RECORD.md` | Source synthesis and audit record — changelog, provenance, standing checks, sweep, mechanism |
| `sources_raw/` | The bytes. Every claim in both files traces here |
| `structural_guideline_claude_vs_openai.md` | Claude-vs-OpenAI structural differences (PG) — not a compliance extraction |
| `structural_guideline_claude_vs_openai_MindSortAI.md` | The same for MindSort |
| `remote_server_submission_guide.md` | Retained **only** because §4F cites its *"Recommended sections"* wording — the evidence that the "Required sections" claim was an inflation. ⚠️ Otherwise superseded, and it still carries the stale `e524d9ef` domain hash, flagged in place |

⚠️ **The middle layer is gone deliberately.** Raw sources hold the bytes, the canonical file holds
requirements, `PROVENANCE.md` holds provenance, this file holds synthesis. A per-page extraction
artifact had no remaining job, and seven of them were a divergence risk, not a safeguard.

⚠️ **This file is still 127 KB.** Shrinking it to synthesis-and-audit-record only — removing what is
now duplicated in the canonical file — is **not done**, and is the remaining half of the
consolidation.

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
