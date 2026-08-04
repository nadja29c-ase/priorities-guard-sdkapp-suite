# `sources_raw/` — where each file came from, and what that guarantees

Written 2026-08-04, after a challenge that exposed a conflation in how this directory was
introduced.

## The distinction these files do and do not settle

| Question | Settled by committing bytes? |
|---|---|
| **Checkability** — is the artifact faithful to *a* source? | ✅ yes. This is what round 2 needs |
| **Currency** — is that source what Anthropic publishes *now*? | ❌ **no** |

When this directory was created the commit message said appending `.md` to a doc URL "unblocks
round 2", and the report said *"you don't need me to paste it; you can read it."* **That was
wrong.** Nadja had been pasting the pages specifically because fetches can be stale. Answering a
staleness concern with a durability fix, and then declaring the staleness concern resolved, is a
category error — and it quietly took back a control she had deliberately established.

## What the `.md` endpoint actually is

`https://claude.com/docs/connectors/building/<page>.md` returns raw markdown, HTTP 200. Response
headers, measured 2026-08-04:

```
cache-control: public, max-age=0, must-revalidate
age: 247
x-vercel-cache: HIT
```

**No `Last-Modified`. No `ETag`.** So:

- ✅ It is a genuine live origin fetch, edge-cached but revalidating.
- ❌ **The response carries no publication date.** There is no way to tell from the fetch when the
  content was authored.
- ❌ The `.md` file is a **different artifact** from the rendered HTML page. Nothing measured here
  rules out the `.md` generation lagging the page a human reads.

**One positive data point, stated at its true width:** `transparent-theming.raw.md` was compared
against Nadja's paste of the same page and matched over the first 60 lines, including
`theme={null}` markers and an inline comment inside the `registerAppResource` snippet. That shows
the endpoint returned current content **for that page, at that moment**. It does not generalise to
other pages or other days.

## Provenance of each file currently in this directory

| File | Origin | Cross-checked against a paste? |
|---|---|---|
| `design-guidelines.raw.md` | fetch | ❌ no — but the page was pasted twice and agreed |
| `transparent-theming.raw.md` | fetch | ✅ **yes**, 60 lines, byte-identical |
| `instance-supersession.raw.md` | fetch | ❌ no — page was pasted, not compared |
| `cross-compatibility.raw.md` | fetch | ❌ no — page was pasted, not compared |
| `authentication.raw.md` | fetch, **paste-corroborated ×3** | ✅ **CLOSED 2026-08-04.** Three independent copies compared — this fetch and two pastes — **no divergence anywhere**, including the A18 sentence verbatim. Do not request this page again |
| **`review-criteria.raw.md`** | **fetch only** | ❌ **impossible — never pasted** |
| `software-directory-policy.raw.md` | fetch, **paste-corroborated** | ✅ identical across all five sections. ⚠️ **Publication date 15 April 2026 — recovered from the paste only; the fetch carries none** |
| `software-directory-terms.raw.md` | fetch | ✅ content corroborated. **Publication date 16 March 2026 — from the paste; the fetch carries none.** First capture — no repo copy existed before 2026-08-04 |
| `testing.raw.md` | fetch | ⚠️ not cross-checked |
| `lazy-authentication.raw.md` | fetch | ⚠️ not cross-checked |
| `submission.raw.md` | **fetch, relay-corroborated** | ✅ **8 distinct facts cross-checked** — see the third category below. **No further paste needed** |
| *Trademark Guidelines* | ❌ **NOT CAPTURED** | `.md` returns **404**; HTML is a Next.js bundle with no clean extraction. **Referenced as binding by Terms T-10. Needs a paste** |

✅ **`authentication` is now closed.** A18 — the only failed requirement found anywhere — rests on
Nadja's copy rather than on a fetch. The `static_bearer` drift and the 17 MUSTs behind the OAuth
attestation are equally covered.

⚠️ **`review-criteria` is now the ONLY page in the audit resting on an unverified fetch**, and it
supplies **R1–R11** plus **raw line 72** — half the evidence for resizing Blocker 1 from "seven
sections before submission" to "a blog post by publish date." **Still needs a paste.**

## ⚠️ A concrete defect in the `.md` method, found 2026-08-04

**The `.md` endpoint strips the publication date.** `software-directory-policy.raw.md` contains no
date stamp anywhere — grep for `updated`/`2026`/`april` returns nothing. The rendered page carries
**"April 15, 2026"**, and the paste carries it too.

**This is the currency metadata the entire provenance argument turns on**, and the fetch silently
drops it. It is no longer a general worry about staleness: **the method is measurably lossy on
exactly the field that would let anyone detect staleness.**

Consequence: a fetched raw file can never be dated from its own contents. Where a date matters,
**the paste is the only source that carries it.** Record the publication date from the rendered
page alongside the fetch date.

**Dates recovered from pastes, existing nowhere in the fetched files:**

| Document | Published | Present in fetch? |
|---|---|---|
| Software Directory Policy | **15 April 2026** | ❌ no date anywhere |
| Software Directory Terms | **16 March 2026** | ❌ no date anywhere |

**This is the first case where the paste is demonstrably BETTER, not merely more trustworthy.**
Every earlier round argued the paste was *safer*; here it carries information the fetch provably
does not. That is a stronger claim and it is now evidenced.

**Related: relative timestamps are worse than none.** Two repo files carried *"Updated this week"*,
captured when the support article displayed a relative stamp. A relative timestamp in a committed
file **silently re-anchors to whenever the reader looks** — it reads as current forever. Both are
now fixed or flagged: `software_directory_policy.md` carries the absolute date;
`remote_server_submission_guide.md` is marked undated, because its real publication date was never
captured and inventing one would be worse.

**The `.md` method is now 3-for-3 against pastes** (`transparent-theming`, and `authentication`
twice). Still evidence about a method and nothing more — it does not establish that any *particular*
future fetch is current.

---

## ⚠️ A process failure worth more than the provenance finding

**Three rounds were spent re-confirming a page that was settled on the first.** The authentication
paste was delivered to the review chat — where the comparison had already been made — and never
reached the agent that had asked for it. Each round the agent asked again, because from its side
nothing had arrived; each round the reviewer re-verified, because from its side a paste had.

**Neither party was wrong and the loop still cost three rounds.** The lesson is not about
provenance at all: **when an agent asks for an artifact, the answer has to reach that agent.**
Confirming to a third party that the artifact exists reads, at the asking end, as silence.

**Rule: once a page is corroborated, record it here as CLOSED and stop asking.** This file is the
shared state; a question already answered in this table must not be re-raised from any side.

---

## Adopted 2026-08-04 — "Option B", to stop the double-paste tax

Pasting every page twice — once per agent — is what produced the loop. Going forward:

| Page | Handling |
|---|---|
| `review-criteria` | **Double paste.** The only page where nothing has been read from source, and it carries R1–R11 plus raw line 72 — half the Blocker 1 resize |
| all remaining pages | **Fetch, committed, with cross-check status recorded per file in the table above.** No paste required |

The status column is the honest part: a fetch-only page is *usable* and is *labelled as unverified
for currency*. That is a stated limitation rather than a hidden one, which is the whole point of
this file.

## A third provenance category — relay corroboration

Fetching `submission` bypassed the paste-first rule. The corroboration happened anyway, in a form
worth naming rather than treating as a waiver:

1. Nadja pasted the page into the review chat.
2. The reviewer relayed **eight distinct, checkable facts** — the Team/Enterprise gate verbatim,
   B5 (allowed-link ownership), B7 (the attestation wording), B8 (seven acknowledgments), B9
   (character limits and the permanent slug), the eleven-step structure, the Skills correction,
   and the screenshot specifications.
3. The fetched raw was checked against all eight. **All eight match.**

**That is a real cross-check, not a waiver.** It is cheaper than double-pasting and stronger than
a bare fetch, so it gets its own label rather than being rounded to either neighbour:

| Category | Meaning |
|---|---|
| **paste** | The bytes came from the rendered page. Carries the publication date |
| **relay-corroborated** | Fetched, then N specific facts confirmed against a paste held elsewhere. **State N** |
| **fetch** | Fetched only. Usable, **not currency-verified**, and **carries no publication date** |

⚠️ **Relay corroboration does NOT recover the publication date** — that is a property of the bytes,
and the relayed facts were content, not metadata. `submission.raw.md` remains undated.

## ⚠️ The source inventory was never enumerated — corrected 2026-08-04

For six rounds this pass reported "the remaining four pages" / "remaining five" **without ever
having read the documentation index.** `https://claude.com/docs/llms.txt` existed throughout and
lists the complete set. The running tally was assembled ad hoc from cross-references encountered
while reading other pages — so it could only ever contain pages something else happened to link.

**This is the writing rule applied to the work plan rather than to a sentence:** *no summary may
quantify over items the table beneath it does not enumerate.* "Four pages remain" is exactly that
shape, and it was wrong for six rounds.

**Four relevant pages the ad-hoc tally missed:**

| Page | Why it matters |
|---|---|
| **`building/testing`** | **The documented procedure for the B7/R11 attestation** — a critical-path item nobody knew had published guidance |
| **`building/lazy-authentication`** | Referenced **four times** from `authentication`; carries the canonical 401 shape §4C leans on |
| `building/directory-vs-custom` | PG runs as a custom connector today and becomes a directory connector after review. External-link behaviour already differs; other differences unknown |
| `building/after-publishing` | The renamed `managing-your-listing` — where reviewer feedback and post-publication health land |

## ⚠️ `llms.txt` indexes `claude.com/docs` ONLY — five binding documents live outside it

A clean read of the index **must not be reported as full coverage.** These are binding and none is
in that index:

| Document | Made binding by | Captured? |
|---|---|---|
| Software Directory **Policy** | referenced throughout | ✅ (support.claude.com) |
| Software Directory **Terms** | Policy §3H | ✅ (support.claude.com) |
| **Trademark Guidelines** | Terms T-10 | ❌ **no** |
| **Usage Policy** | Policy §1A | ❌ **no** |
| **Universal Usage Standards** | Policy §1A | ❌ **no** |
| **High-Risk Use Case requirements** | Policy §1A | ❌ **no** |
| **Supported-countries policy** | Policy §1A | ❌ **no** |

**Policy §1A alone makes four uncaptured documents binding.** Revised count: **13 pages captured,
2 relevant pages outstanding, 5 binding documents outside the index.**

## The rule going forward

**Step 0 is the paste. Committing it is step 0b.**

1. Nadja pastes the page from the rendered source.
2. That paste is committed here verbatim as `<page>.raw.md`.
3. A fetch may be used **only** to corroborate a paste, never to replace one — and when both
   exist, any divergence is reported, not silently reconciled.

She keeps the freshness guarantee; the tree keeps the checkability. Nothing downstream rests on a
fetch nobody can compare against.

**Do not write "commit the raw at step 0" as though the fetch were the source of truth.** It is
not. It was never established as one, and one page's agreement is not the evidence that would
establish it.
