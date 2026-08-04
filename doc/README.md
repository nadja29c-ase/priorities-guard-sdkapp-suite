# `doc/` — what goes where

Written 2026-08-04, after the ADR / OAuth / compliance reorganisation, because "is this a
compliance document?" turned out to be a real question with a non-obvious answer.

The organising distinction is **who wrote the rule**, not what the document is about.

| Folder | Holds | Test |
|---|---|---|
| `ADR/` | Architecture decision records, numbered | A decision we made, with its reasoning and alternatives |
| `OAuth/` | Everything about our OAuth provider | Our authorization server — spec, integration, investigations |
| `Claude_Compliance/` | **Anthropic's** rules for us | Written by Anthropic. We comply; we do not amend |
| `OpenAI_compliance/` | **OpenAI's** rules for us | Written by OpenAI. Same |
| `legal/` | Published or signed artefacts | Binds us externally |
| `sql/` | Standalone queries | Runnable, not prose |
| `internal_changelog/` | Dated incident and change notes | What happened, when |
| `clarity_doc/`, `pg_doc/` | Per-app documents | Scoped to one app |
| root | Operational runbooks and cross-cutting references | `OPERATIONS_*`, canonical URLs, the testing baseline |

---

## The two that are easy to misfile

### `OAuth_Hard_Requirements.md` is NOT a compliance document

It looks like one — it is versioned, has a changelog, and is titled "Hard Requirements". But
the compliance folders hold **external rulebooks**: documents Anthropic or OpenAI wrote, that
we satisfy and cannot change.

`OAuth_Hard_Requirements.md` is **our own normative spec for our own authorization server**,
derived from the RFCs and from what both platforms need at their inbound edge. We wrote it and
we amend it — §12a was added during the Claude connector auth increment.

It also covers **both** platforms, so it could not live in a single-platform compliance folder
even if it were external.

It lives in `doc/OAuth/` because that is the OAuth folder. Note that folder is not
"investigations only": `NEW_APP_OAUTH_INTEGRATION.md` is normative too, and CLAUDE.md rule 3
mandates reading it before any new-app OAuth work.

### `legal/` is what we published, not what we intend

`pg_data_retention_and_permission_surface.md` is the in-repo retention record for Priority
Guardian. The shared-backend strategy it descends from exists only as a signed PDF outside
this repo. The live privacy policy and ToS are **not** in this repo either — they are
published at `fulfilling-productivity.com`, and that published version is authoritative.

Stale in-repo copies were deleted deliberately (2026-08-04). The reason is specific: a stale
copy of `pg_privacy_policy_v3.1.md` produced a false finding in an earlier increment, because
it was read as current. **Fetch the live policy; do not read a repo copy.**

---

## One writing rule for compliance documents

**No summary sentence may quantify over items the table beneath it does not enumerate.**

- *"Nothing was stale"* requires every row marked checked.
- *"Verified against live docs"* requires naming which docs, and when.
- *"All 17 tools lack X"* requires having looked at all 17.

This is a writing rule, not a judgement call, and it is here because the same failure occurred
three times in one session — each time in a summary, never in the check underneath it:

| Claim | What was actually checked |
|---|---|
| *"500px — verified from live docs"* | a stale fetch, never re-verified |
| *"All 17 tools lack `title` — required code fix"* | nothing; `title` was a required field already |
| *"Nothing in §4C was found to be stale"* | 16 of 17 rows; the 17th (`static_bearer`) had drifted |

Each was believed **because** it was specific. The underlying checks were sound every time;
the sentence generalising over them was not. A confident summary is the most dangerous line in
a compliance document, because it is the one people quote instead of re-deriving.

**Corollary — fix the claim, not the instance.** When a false statement is found, grep the repo
for it before closing. The `title` claim lived in three places; fixing the one being pointed at
left two, and it took two review rounds to clear.

**Second corollary — a negative claim must state the scope it was proved over.** *"No
fullscreen-scoped override exists anywhere in the widget's CSS"* was **literally true and
substantively wrong**: the override was a JSX inline style object, and the search covered `.css`
files. A negative finding is only as wide as its search, so the search has to be in the sentence.

Write *"no `max-width` in `src/**/*.css`"*, not *"no `max-width` anywhere"*. The second is a
claim about the widget; the first is a claim about the grep, and only the first was tested. This
is not the corollary above — nothing needed fixing in three places. **The search scope silently
excluded the answer**, which no amount of grepping for the same wrong pattern would have caught.

Three findings this session were "checked where I was looking": the `title` claim (three
locations), the `resourceDomains` third block, and this one. The first two are the corollary. The
third is this rule.

---

## The compliance-page refresh routine

Ten Anthropic source pages feed `claude_connectors_compliance_master.md`. Each is refreshed on
its own commit, and **a page is not done until step 5.** Steps 1–4 were the routine as practised;
step 5 kept being remembered rather than executed, and the currency metadata lagged the work two
rounds running. It is a step now.

0. **Commit the raw source verbatim** to `Claude_Compliance/sources_raw/<page>.raw.md`.
   **Append `.md` to the doc URL** — `…/building/authentication.md` returns 17 KB of raw
   markdown, HTTP 200. No rendering, no summarisation, no transcription step. This is step 0
   because without it every later step rests on a fetch only one party saw, and a reviewer who
   cannot read the source cannot check the artifact against it — which is the whole of round 2.
1. **Fetch live** and write a dated source dump into `Claude_Compliance/`.
2. **Extract the obligations** into a numbered table, distinguishing MUST from recommendation.
3. **Verify PG against each**, citing file and line — or say "not verified" and why.
4. **Diff against every repo doc that touches it**, applying the corollary below: grep for each
   false claim before closing, because it will not be in one place.
5. **Update the currency metadata in the same commit** — the master's header line *and* the §11
   changelog heading. Both must name exactly which pages are refreshed and which are not.

Understating currency is the same class of error as overstating it. The header exists so a reader
can trust its scope without re-deriving it; a header that is merely *stale in the safe direction*
still can't be trusted, which is the only property that matters.

### Round 1 catches omission; round 2 catches invention

**Round 1** is steps 1–5 above: did the source get captured. **Round 2** runs *after* the master
is rewritten and checks the reverse direction:

- Does every claim now in the master trace to a line in a source dump?
- Does every PG status claim trace to a file and a line?

Round 1 structurally cannot catch a fabrication, because a fabrication has no source to be missing
from. On 2026-08-04 three passed round 1 untouched — the 500px provenance, a "new" proactive-refresh
item the master already documented, and *"nothing in §4C was stale."* All three were specific, and
believed because they were specific.

**"Closed" means both rounds.** Saying it after round 1 is the same overstatement the writing rule
below prohibits, one level up.

**Round 2 is artifact-level and synthesis-level, and they are not the same pass.** Checking the
source dumps is not checking the master. §4C/§4K/§4N are unrewritten, so no round 2 has touched
the synthesis — do not let a tally of green artifacts imply otherwise.

**Two things round 2 catches that are not fabrications**, both found on 2026-08-04:

- **Miscounts in summary sentences.** *"11 of the 17 are verified"* counted table rows, not
  requirements — one row held two. The writing rule catches this only if someone re-counts.
- **Citations that cannot be checked.** A provenance note cited line numbers in a file that had
  been deleted; a "verbatim" reproduction silently dropped a declaration; an evidence column
  carried the word *"likely."* None changed a verdict. All three erode the citations that do.

**Cite the declaration, not the line number, unless you can re-read it.** Hand-counted line
numbers are wrong often enough to poison the citations around them.

---

## Why the taxonomy is written down at all

Documents drifted into the wrong folders twice in one session, and once a normative spec was
moved into an investigations folder by accident and had to be reverted. A folder whose
membership rule is only implied gets the wrong members.

Two related lessons from the same period, recorded because they are about `doc/` rather than
about code:

- **A document asserting something "verified" is not evidence.** `mindsort_claude/config.py`
  carried a comment reading *"PRODUCTION SHAPE (verified 2026-07-04)"* which was false, and it
  misdirected a full day because it was specific enough to be believed.
- **Two documents describing the same thing will diverge.** The retention strategy PDF and its
  markdown transcription already disagree; whichever governs must say so in both. Tracked
  separately.
