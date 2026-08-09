# Source drift sweep — 2026-08-09

**Report only. No captured source was overwritten.** All eleven captured on **2026-08-04**; re-fetched
2026-08-09, five days later.

**Headline: 3 of 11 drifted, all cosmetic. But the sweep's most serious finding is not drift at all —
a canonical row quotes a sentence that exists in no source, in either artifact form.** See §4.

---

## 1. Bounds, stated up front

**The eleven files, by name:** `authentication` · `cross-compatibility` · `design-guidelines` ·
`instance-supersession` · `lazy-authentication` · `review-criteria` · `software-directory-policy` ·
`software-directory-terms` · `submission` · `testing` · `transparent-theming` (all `.raw.md`).

- **Drift is detectable but never dateable.** The `.md` endpoints return no `Last-Modified` and no
  `ETag`. Nothing here can say *when* a change happened, only that the bytes differ from 2026-08-04.
  "Changed since capture" is the strongest available claim.
- **Eight documents known silent in `llms.txt` are NOT covered**, because they were never captured:
  Trademark Guidelines · Usage Policy · Universal Usage Standards · High-Risk Use Case requirements ·
  supported-countries policy · Enterprise Managed Auth · directory-vs-custom · managing-your-listing.
  **They cannot drift-check because they do not exist here.** Trademark Guidelines is cited as binding
  by Terms T-10.
- **Three sources are relay-only** — external-links, troubleshooting, after-publishing — pasted into a
  review chat and never handed over. **Their captured state may already be incomplete**, so "identical"
  could not be asserted for them even if they were present. They are not among the eleven.
- **Comparison is byte-level against the `.md` artifact only.** PROVENANCE.md's warning that the `.md`
  "is a **different artifact** from the rendered HTML page" is **not** resolved by this sweep for ten of
  the eleven. It was tested for exactly one page — see §4 — and there the two agreed.

### What a clean result would and would not prove

**Would:** the captured bytes still match what the `.md` endpoint serves today.

**Would not:**
- that the `.md` matches the rendered HTML a human reviewer reads (untested for 10 of 11);
- that a requirement absent from both is not binding (see the eight uncaptured documents);
- that the capture was complete when made (relay-only sources);
- that a canonical row's *quotation* is faithful to the source it cites — **that is a different check,
  and it is the one that failed.**

---

## 2. Result

| File | Status | Captured SHA-256 (12) | Live (12) |
|---|---|---|---|
| `authentication.raw.md` | IDENTICAL | `63693a28e5f0` | `63693a28e5f0` |
| `cross-compatibility.raw.md` | IDENTICAL | `c5765e1b9f1f` | `c5765e1b9f1f` |
| `design-guidelines.raw.md` | IDENTICAL | `c71822eee421` | `c71822eee421` |
| `instance-supersession.raw.md` | IDENTICAL | `3419450364b4` | `3419450364b4` |
| **`lazy-authentication.raw.md`** | **DRIFTED** | `a97a4b415dd7` | `a184ae63ecdf` |
| `review-criteria.raw.md` | IDENTICAL | `9eb4a370c0bd` | `9eb4a370c0bd` |
| `software-directory-policy.raw.md` | IDENTICAL | `031086f3df37` | `031086f3df37` |
| `software-directory-terms.raw.md` | IDENTICAL | `8729c84d840f` | `8729c84d840f` |
| **`submission.raw.md`** | **DRIFTED** | `5cf22c424136` | `9c0f206e339f` |
| **`testing.raw.md`** | **DRIFTED** | `f401556d1c0c` | `b9ba20aee481` |
| `transparent-theming.raw.md` | IDENTICAL | `5e8a4faed9aa` | `5e8a4faed9aa` |

**Both directory documents are byte-identical** — policy and terms, the two with real legal weight,
have not moved. That is the most reassuring line in the table.

---

## 3. The three drifts — all COSMETIC, one operationally relevant

**One hunk each. All three are the same upstream event: a UI navigation rename.** No `MUST` added,
removed or reworded. No constraint value changed. No new section.

| File | Change | Class |
|---|---|---|
| `lazy-authentication` | `Settings → Connectors → Add custom connector` ⟶ `Customize > Connectors`, select `Add custom connector` | Cosmetic |
| `testing` | `Settings > Connectors > Add custom connector` ⟶ `Customize > Connectors`, select `Add custom connector` | Cosmetic |
| `submission` | `Admin settings > Roles` ⟶ `Organization settings > Roles`; permission **`Directory management`** ⟶ **`Directory`** | Cosmetic *for the requirement*, **operationally relevant** |

### Canonical rows affected

| Row | Cites | Effect |
|---|---|---|
| **S1** | *"Admin settings — and therefore the portal — are unavailable on individual plans"* | Label stale (`Admin settings` → `Organization settings`). **Requirement unchanged**: a Team or Enterprise org is still required. |
| **S2** | *"Enterprise may delegate via a custom role with **Directory management** or **Libraries**"* | **Permission renamed to `Directory`.** Requirement unchanged — Owner/Primary Owner, Enterprise may delegate, Team has no custom roles. |

**S2 is the one worth acting on, and it is not a compliance issue.** Its *obligation* is untouched, but
anyone following S2 to delegate submission rights will search a UI for **"Directory management"** and
find **"Directory"**. Submission is imminent, so the stale label costs time at exactly the wrong moment.

**Nothing in the drift changes PG's compliance posture. No row's verdict moves.**

---

## 4. The finding that is not drift — X2 quotes a sentence that exists nowhere

While mapping drift to rows, `Settings > Connectors` was found cited in **X2**:

> | X2 | … **Hash the exact string entered in Settings > Connectors, including path and any trailing
> slash** | `CONDITIONAL` ⚠️SILENT | cross-compatibility (raw 29, 32) |

**That sentence is in no captured source, and in no live artifact.**

- `cross-compatibility.raw.md` is 39 lines. It contains **none** of `Settings`, `Connectors`,
  `Hash the exact`, or `trailing slash`.
- **No** captured source contains the sentence.
- The **rendered HTML page** (404 KB) does not contain it either — `trailing` appears **zero** times.
  *Positive control run before trusting that negative:* `claudemcpcontent` ×4, `Domain handling` ×4,
  `registerAppTool` ×4 all found in the same bundle. **The absence is real, not a search artifact.**

So this is **not** the `.md`-vs-HTML gap PROVENANCE warned about. For this page the two agree — and
neither says it.

**What the source at lines 29–39 does support:** compute
`sha256(<your server URL>)[:32] + ".claudemcpcontent.com"`, with the worked example
`https://example.com/mcp` — which **does** include a path. PG implements exactly this. **X2's substance
is satisfied.**

**What it does not support:** *"the exact string entered in Settings > Connectors"* and *"including …
any trailing slash"*. Both are interpolation presented as quotation.

**Why that matters.** The trailing-slash concern is the whole basis of X2's ⚠️SILENT marker and of the
audit record's *"Real but unactionable … known latent risk"* — and of the `.rstrip("/")` worry in
`config.py`. **That risk analysis rests on words the source never used.** The risk may still be real as
engineering judgment; it is simply not sourced, and it is recorded as though it were.

**This is a citation-integrity defect, not a drift defect** — and no amount of re-fetching would ever
have caught it. It surfaced only because drift was mapped back to rows, which is why that step was
worth doing.

---

## 5. The mechanism

- **`doc/Claude_Compliance/sources_raw/MANIFEST.json`** — per file: SHA-256, byte count, URL,
  provenance category (verbatim from PROVENANCE.md's own assessment), capture commit and commit date.
- **`doc/scripts/source_drift_sweep.py`** — re-runnable. Fetches to `/tmp`, compares hashes, prints a
  unified diff per mismatch. Exit code 1 on drift, so it can gate. **It never writes to
  `sources_raw/`.** `--write-manifest` regenerates the manifest.

Next drift is caught deliberately rather than by luck.

---

## 6. Not checked

- The eight uncaptured documents (§1) — **cannot be checked; they are not here.**
- The three relay-only sources — not among the eleven.
- `.md` vs rendered HTML for **ten of eleven** pages. Tested for `cross-compatibility` only.
- Whether every *other* canonical quotation is faithful to its source. **X2 was found by accident of
  drift-mapping.** One row was checked; **129 rows were not.** Given what checking one row turned up,
  that is the obvious next sweep.
- Publication dates for the two directory documents — recorded in PROVENANCE from pastes
  (2026-04-15, 2026-03-16); the fetches carry none, and this sweep cannot confirm them.
