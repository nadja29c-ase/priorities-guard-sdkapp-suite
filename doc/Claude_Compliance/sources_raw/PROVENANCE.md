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
| `authentication.raw.md` | fetch | ✅ **YES — paste-verified 2026-08-04.** Agrees on every discriminating marker incl. the A18 sentence verbatim. Structural + distinctive-string comparison, not a byte diff |
| **`review-criteria.raw.md`** | **fetch only** | ❌ **impossible — never pasted** |

✅ **`authentication` is now closed.** A18 — the only failed requirement found anywhere — rests on
Nadja's copy rather than on a fetch. The `static_bearer` drift and the 17 MUSTs behind the OAuth
attestation are equally covered.

⚠️ **`review-criteria` is now the ONLY page in the audit resting on an unverified fetch**, and it
supplies **R1–R11** plus **raw line 72** — half the evidence for resizing Blocker 1 from "seven
sections before submission" to "a blog post by publish date." **Still needs a paste.**

**The `.md` method is 2-for-2 against pastes** (`transparent-theming`, `authentication`). That is
evidence about the method and nothing more. It is **not** a licence to skip the remaining paste —
two agreements do not establish that a third fetch is current, and the page still to be checked is
the one steering the critical-path estimate.

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
