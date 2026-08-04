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

`data_retention_strategy.md` is a transcription of a signed PDF. The live privacy policy and
ToS are **not** in this repo — they are published at `fulfilling-productivity.com` and that
published version is authoritative.

Stale in-repo copies were deleted deliberately (2026-08-04). The reason is specific: a stale
copy of `pg_privacy_policy_v3.1.md` produced a false finding in an earlier increment, because
it was read as current. **Fetch the live policy; do not read a repo copy.**

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
