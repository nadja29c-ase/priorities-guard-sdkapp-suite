# Briefing — Create `CLAUDE_COMPLIANCE_REQUIREMENTS_CANONICAL.md`

**Increment:** Compliance-Docs-02
**Location:** `doc/Claude_Compliance/CLAUDE_COMPLIANCE_REQUIREMENTS_CANONICAL.md`
**Deliverable:** One document containing every requirement an MCP App for Claude must satisfy to pass review — and nothing else.

---

## 0. Why this exists

The master carries four jobs at once: requirements, PG conformance status, audit apparatus, and implementation mechanism. Requirements are roughly 15% of it. That is why a 70 KB file whose own header contradicts itself is not readable before an increment, and why a stale constraint survived two months in it.

This file does **one** job. Anyone shipping or submitting reads this and nothing else.

---

## 1. Non-goals

- **Not a replacement for the master.** The master remains the source synthesis and audit record: changelog, provenance tables, standing checks, hardening sweep, round-1/round-2 status, and implementation mechanism.
- **No mechanism detail.** No CSS token tables, no `BroadcastChannel` election protocol, no SDK helper lists, no code. If a reader needs to know *how*, they follow the source link. This file states *what must be true*.
- **No new source fetches.** Populate from `sources_raw/` only.
- **No code changes. No tool description changes.**
- **Not a work list.** Status is recorded, not assigned.

If a row cannot be traced to a line in `sources_raw/`, it does not go in.

---

## 2. Schema

One row per requirement. Five columns:

| ID | Requirement | Level | Source | PG status |

**ID** — stable, section-prefixed, never renumbered. `P-1D`, `T-9`, `A-03`, `M-10`, `X-02`, `L-05`, `S-07`, `PUB-02`. Existing IDs from the audit (A-01…A-18, M-01…M-12, T-3, T-4, T-9, T-10) are preserved.

**Requirement** — one sentence, stated as the obligation. Not a summary of the page.

**Level** — the taxonomy below. This column is the point of the document.

**Source** — `<file>.raw.md` plus the section or line. Every row. No exceptions.

**PG status** — see §5.

---

## 3. Level taxonomy

Nine rounds of audit found the same defect repeatedly: soft language recorded as hard. This column makes that impossible to do silently.

| Level | Meaning |
|---|---|
| `POLICY` | Software Directory Policy MUST — binding, review-enforced |
| `TERMS` | Directory Terms warranty or obligation — contractual |
| `PORTAL` | Enforced by the submission portal, or a required form field |
| `DOC-CONSTRAINT` | Stated as a constraint on a docs page; binding via Policy §3H |
| `SPEC` | Inherited from the MCP specification via an Anthropic page — **not a directory gate** |
| `REVIEW-ONLY` | Appears only in `review-criteria` — reviewer-facing, not in the binding documents |
| `RECOMMENDED` | Explicitly soft in the source. Included so nobody re-promotes it. |
| `CONDITIONAL` | Binding only under a stated precondition — state the precondition in the requirement text |

A row whose level cannot be determined from the source is `RECOMMENDED` by default, with a note. Never round upward.

---

## 4. Section map

1. **Safety & Security** — Policy §1A–§1F
2. **Tool & capability descriptions** — Policy §2A–§2G
3. **Developer requirements** — Policy §3A–§3H
4. **Unsupported use cases** — Policy §4A–§4C
5. **MCP server requirements** — Policy §5A–§5G
6. **Directory Terms warranties** — T-1…T-10
7. **Authentication & OAuth** — A-01…A-18
8. **MCP Apps: display modes & design** — M-01…M-12 plus the carousel and scrolling constraints
9. **MCP Apps: widget domain, CSP, theming** — X-…, including the `ui.domain` computation and the trailing-slash rule
10. **External links** — L-…
11. **Submission portal** — S-…, including the Team/Enterprise access gate, the seven compliance acknowledgments each mapped to what it warrants, asset specs, character limits, the permanent slug, and the tool-exercise attestation
12. **Post-publication** — PUB-…
13. **Uncaptured obligations** — see §7

---

## 5. PG status column — populate conservatively

Three values only:

- `✅ verified` — with a file and declaration citation, read fresh
- `⚠️ <finding>` — a recorded, measured discrepancy
- `— not assessed` — the default

**Populate `✅` and `⚠️` only from claims already verified and recorded during the audit.** Do not run a fresh codebase audit to fill this column; that is a separate increment. Anything not already established is `— not assessed`, and that is the correct answer.

Status is recorded status. It is not a work list and generates no tasks in this increment.

---

## 6. Provenance markers

Carry the source-reliability marker into every row's Source cell, inherited from `PROVENANCE.md`:

- unmarked — paste or paste-corroborated
- `[fetch-only]` — `review-criteria`, `testing`, `lazy-authentication`: undated, uncorroborated
- `[relay-only]` — `external-links`, `troubleshooting`: no artifact in the tree

Rows sourced `[relay-only]` are included but visibly marked. When those two pastes land, the markers come off.

---

## 7. Section 13 — Uncaptured obligations

A short register of what is known to bind but has never been read. Not rows in the main table — a list, so the gaps are visible in the canonical document rather than only in the master's header.

- Trademark Guidelines (Terms T-10)
- Usage Policy, Universal Usage Standards, High-Risk Use Case requirements, supported-countries policy (Policy §1A)
- Enterprise Managed Auth (authentication page cross-reference)
- `building/directory-vs-custom`, `building/managing-your-listing`

---

## 8. Header

Short. Four things:

1. What this document is, and that it is the only one needed before shipping or submitting
2. Sources it is current against, by name, with the count
3. What it is silent on — the §7 list, by name
4. Date, and the rule that this file states current state only. **Prior entries go in the master's changelog, never inline here.**

---

## 9. Verification requirements

- Every row traces to a line in `sources_raw/`. Cite it. If it cannot be traced, it does not go in.
- Every `✅`/`⚠️` traces to a file and declaration in the codebase.
- Any count states its pattern and its predicate (standing check #7).
- Every item in a labelled group carries its own level — no blanket labels over mixed lists (standing check #6).
- Deduplicate across sources: where two pages state the same obligation, one row, both sources cited.
- Where two sources conflict, one row, both stated, conflict flagged — do not reconcile silently.
- Report ends with a commit hash and an explicit list of what was **not** verified.

---

## 10. Follow-on, not in this increment

- Renaming the master to reflect what it is (source synthesis and audit record)
- Removing from the master anything now duplicated here
- Round 2 on both files
- The master header's self-contradiction: prior entries preserved inline above the fold, contradicting the current entry. Supersession is a move, not an annotation.
