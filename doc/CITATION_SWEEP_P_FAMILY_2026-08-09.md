# Citation sweep — P* (Policy) bold claims, manual half

**Criterion written before reading, deliberately.** The mechanical half states its bounds in its own
docstring; the manual half has no such mechanism, so the rule is fixed here first and applied
unchanged. Deriving a criterion while reading is how a reader talks themselves past the thing they
are looking for.

---

## The criterion

For each bold span not present verbatim in its cited source, ask **one** question:

> **Does this read as a complete imperative sentence in the source's register — text that could be
> lifted verbatim from Anthropic's documentation?**

**FLAG** if yes. That is X2's exact shape: *"Hash the exact string entered in Settings > Connectors,
including path and any trailing slash"* — a full imperative sentence, source register, no hedging. It
survived two review rounds because it reads like Anthropic wrote it.

**PASS** if the span is:

- a **fragment** — a clause without a subject and verb, obviously mid-sentence
- a **number, identifier or literal** — `44 x 44pt`, `S256`, `prefersBorder`
- a **row-summary in the file's own voice** — `CONDITIONAL — applies only to …`, `Mandated rotation
  alone`, level markers, editorial notes
- a **paraphrase that does not present as quotation** — compressed, reordered, or generalised wording
  that no reader would take as verbatim

**PASS is not "verified accurate."** It means *not fabrication-shaped*. A fair-paraphrase judgement is
a separate question this pass does not make.

### Stop rule, fixed in advance

Read the **19 P\*/R6a/R7a rows only**. If none are FLAG, stop — the prior that the remaining 52
contain a fabrication drops sharply, since these 19 are the only rows never examined by any pass,
mechanical or manual. **If even one is FLAG, read all 71.**

---

*(Findings appended below after reading.)*

---

## Result — read 2026-08-09, criterion above applied unchanged

**16 P\*/R6a/R7a bold claims. Zero FLAG. Zero fabrications.**

*(Count correction: I earlier estimated "19 newly visible" from the 52→71 delta. The exact figure is
**16** P\*/R6a/R7a lines out of a 71-line worklist; 55 belong to other families. The 19 was arithmetic
on a delta, not a count of the thing itself — the same shortcut this sweep exists to catch.)*

### PASS — file's own voice or fragment (10)

| Row | Span | Why PASS |
|---|---|---|
| P3A:97 | `Stated a conditional obligation as universal.` | Round-2 correction note, editorial voice |
| P3A:265 | `CONDITIONAL — applies to Software that collects user data OR…` | Level marker, the file's taxonomy |
| P2D:253 | `call or coerce Claude into calling other external software…` | Fragment, mid-sentence |
| P2G:256 | `all behavioural guidance human-readable and clearly presented` | Fragment |
| R6a:257 | `if they tell Claude to behave in ways unrelated to the tool's function,` | Fragment |
| P3C:267 | `how the Software works, its intended purpose, and how users troubleshoot issues` | Fragment |
| P3F:271 | `of any API endpoint, domain or UI the Software connects to,` | Fragment |
| P4C:284 | `advertisements, sponsored content or paid product placements` | Fragment |
| P5B:293 | `— usage roughly commensurate with task complexity or impact;` | Fragment |
| P4C:1205 *(audit record)* | `Absent from review-criteria; binding only via the policy` | Editorial voice |

### PASS — source-register, and **checked against the source** (6)

These read as if the source said it, so each was verified rather than waved through.

| Row | Canonical bold | Source | Verdict |
|---|---|---|---|
| **P1F** | *Must not query or extract Claude's memory, chat history, conversation summaries…* | policy:17 — *"Software must not query or extract **data from** Claude's memory, chat history, conversation summaries, or user-generated or uploaded files."* | Faithful; drops "data from". Compression, not invention |
| **P4B** | *Design-focused visual aids are permitted* | policy:61 — *"Design-focused software that uses AI models to create visual aids (…) are permitted."* | Faithful compression |
| **P3H** | *and follow the design guidelines Anthropic publishes* | policy:53 — *"…and follow design guidelines Anthropic publishes applicable to Software."* | Faithful; adds "the" |
| **P3D-i** | *fully populated account, not an empty shell* | testing:39 — *"Provide a **fully populated account**—not an empty shell—"* | **Verbatim.** Checker missed it on em-dash vs comma |
| **P3D-i** | *and must include step-by-step setup instructions for someone unfamiliar with the service* | testing:39 — *"Include step-by-step setup instructions for someone unfamiliar with your service."* | Faithful; "your"→"the" |
| **R7a** | *successful response … Validate inputs and return actionable errors* | review-criteria:51-53, three bullets | Faithful compression of all three |

### Stop rule applied

The rule fixed in advance: **clean ⇒ stop.** These 16 were the only rows never examined by any pass,
mechanical or manual. None is fabrication-shaped. **The remaining 55 are not read**, and the prior that
they contain an X2-class fabrication is correspondingly lower — not zero.

**What this does not establish.** That the 55 are clean; that every PASS is a *fair* paraphrase (a
separate judgement this pass did not make); or that non-bold, non-quoted prose is faithful. X2 was
caught because it was bold **and** in a cited row. A fabrication in ordinary prose would still be
invisible to everything built today.

---

## Third pass — §8–§13 read, and the submission cluster closed (2026-08-10)

A reviewer read the header and §8 M2 → §13 by eye, applying the same criterion. **Zero fabrications.**
Every source-register bold span traced to real text: M3 *"Safe areas are not mobile-specific"* · M10
*"don't add side margins…"* · M18 *"Use host tokens for all structural elements"* · M19 · M20
*"skeleton screens… avoid spinners"* · X1 · X7 · X8 · X9 · S13 · PUB2 — all verbatim or faithful.

**That pass named its own gap: L1–L4, S5, S7, S8, S9 cite the submission page, which the reviewer had
not read.** It was called "the largest unverified cluster". `submission.raw.md` **is** captured, so the
cluster was checkable and is now checked:

| Row | Claim | Source | |
|---|---|---|---|
| **S7** | 3–5 · PNG · ≥1000px · crop to app response · prompt must not appear · prompt text separately · aspect ratio any · video/GIF rejected · one batch all surfaces · Figma template | `submission:90–101` | **10 of 10 verbatim** |
| L1 | field optional; if omitted users are shown a confirmation prompt each time | `submission:85–86` | verbatim |
| L2 | every origin/scheme must be owned by you; entries you don't own removed in review | `submission:82` | verbatim |
| L3 | scheme + hostname only; subdomains not implied, list each | `submission:79` | verbatim |
| L4 | custom URI scheme, native app you own, only scheme matched | `submission:80` | verbatim |
| S5 | name ≤100 · tagline ≤55 · description ≤2,000 · 1–5 categories | `submission:144` | **every number correct** |
| S8 | seven acknowledgments, all required, and the seven names | `submission:168` | **7 of 7, in order** |
| S9 | API own / proxied with permission / third party's; health data; sponsored content | `submission:160` | verbatim |

**S7 was singled out as the row to check because it will be followed literally in a few days and a wrong
detail costs a resubmission.** It is correct in every element, including the count.

### Standing after three independent passes

Mechanical (30 quoted rows, all families) · P\* manual (16 rows) · §8–§13 manual (this pass) + the
submission cluster (8 rows). **X2 remains the only fabrication ever found.**

**Remaining unverified:** non-quoted bold in §6 `T*` and §7 `A*`. Their *quoted* spans were covered
mechanically; their bold spans were not read by eye. Not blocking, and the prior after three clean
passes is low.
