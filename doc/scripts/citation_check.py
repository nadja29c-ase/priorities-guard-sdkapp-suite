"""Mechanical half of the citation-integrity sweep.

WHY. Canonical row X2 presented invented text as a quotation, attributed to a
source that never said it. It was found by accident while mapping source drift to
rows. One row's quotation was checked; it was wrong. This checks every one.

WHAT IT ANSWERS. For each QUOTED span in a table row, does the file that row cites
actually contain that text? That is mechanical and decidable. Whether a PARAPHRASE
is fair is not, and this script deliberately does not pretend to judge it —
anything surviving here still needs reading by eye.

METHOD NOTE, earned the hard way today. Three false negatives in one day came from
searches whose bounds were never stated. So:
  - text is NORMALISED before comparison (smart quotes, dashes, markdown emphasis,
    collapsed whitespace) — otherwise a faithful quote reads as missing;
  - a POSITIVE CONTROL runs first. If a string known to be present is not found,
    the run aborts rather than reporting a clean sweep.

    python doc/scripts/citation_check.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CC = ROOT / "doc/Claude_Compliance"
SRC = CC / "sources_raw"
TARGETS = [CC / "CLAUDE_COMPLIANCE_REQUIREMENTS_CANONICAL.md",
           CC / "COMPLIANCE_AUDIT_RECORD.md"]

# citation keyword -> captured file. Keys are what the source column actually says.
SOURCE_MAP = {
    "authentication": "authentication.raw.md",
    "lazy-authentication": "lazy-authentication.raw.md",
    "cross-compatibility": "cross-compatibility.raw.md",
    "design-guidelines": "design-guidelines.raw.md",
    "instance-supersession": "instance-supersession.raw.md",
    "review-criteria": "review-criteria.raw.md",
    "submission": "submission.raw.md",
    "testing": "testing.raw.md",
    "transparent-theming": "transparent-theming.raw.md",
    "software-directory-policy": "software-directory-policy.raw.md",
    "directory-policy": "software-directory-policy.raw.md",
    "software-directory-terms": "software-directory-terms.raw.md",
    "directory-terms": "software-directory-terms.raw.md",
    "policy": "software-directory-policy.raw.md",
    "terms": "software-directory-terms.raw.md",
}
# cited but never captured -> cannot be checked, must not read as a pass
UNCAPTURED = {"after-publishing", "troubleshooting", "external-links", "trademark",
              "usage-policy", "managing-your-listing", "directory-vs-custom",
              "enterprise-managed-auth", "supported-countries", "high-risk"}


def norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'")
    s = s.replace("“", '"').replace("”", '"')
    s = s.replace("—", "-").replace("–", "-").replace("→", "->")
    s = re.sub(r"[*`_]", "", s)          # markdown emphasis / code ticks
    s = re.sub(r"\s+", " ", s)
    s = s.strip().lower()
    # Terminal punctuation is a QUOTING convention, not a fidelity claim: a quote
    # ending "...up-to-date." against a source reading "...up-to-date; and (iv)"
    # is faithful. Not stripping it produced two false fabrication reports on the
    # first run — the same unstated-bound failure this sweep exists to catch.
    s = s.strip(" .,;:!?\u2026")
    s = re.sub(r"^\.{3}|\.{3}$", "", s).strip()
    return s


SOURCES = {f.name: norm(f.read_text()) for f in SRC.glob("*.raw.md")}

# ---- positive control: a string known to be in a captured source -------------
CONTROL = ("authentication.raw.md",
           "Claude does not honor a `WWW-Authenticate` header on a `200` response")
if norm(CONTROL[1]) not in SOURCES[CONTROL[0]]:
    sys.exit("POSITIVE CONTROL FAILED — normalisation or paths are wrong. "
             "Aborting rather than reporting a clean sweep.")

BOLD_RE = re.compile(r"\*\*([^*]{40,400})\*\*")
QUOTE_RE = re.compile(r'"([^"]{25,400})"')      # quoted spans, long enough to be a claim
ROW_RE = re.compile(r"^\|\s*\*{0,2}([A-Z]{1,3}[0-9]{1,3})\*{0,2}\s*\|(.+)\|\s*$")

rows_checked = missing = 0
findings, unresolved, bold_misses = [], [], []

for target in TARGETS:
    for lineno, line in enumerate(target.read_text().splitlines(), 1):
        m = ROW_RE.match(line)
        if not m:
            continue
        rid, body = m.group(1), m.group(2)
        cells = [c.strip() for c in body.split("|")]
        cited = cells[-1] if cells else ""

        files = {v for k, v in SOURCE_MAP.items() if k in cited.lower()}
        uncap = {k for k in UNCAPTURED if k in cited.lower()}
        quotes = [q for q in QUOTE_RE.findall(body) if len(norm(q)) >= 25]

        # BOLD claims. X2 — the fabrication that motivated this script — is BOLD,
        # not quoted, so a quote-only check would have missed its own founding case.
        # Bold is also used for legitimate emphasis and paraphrase, so a miss here
        # is a WORKLIST ITEM for human reading, never a finding on its own.
        for b in BOLD_RE.findall(body):
            nb = norm(b)
            if len(nb) < 40 or not files:
                continue
            if not any(nb in SOURCES[f] for f in files if f in SOURCES):
                bold_misses.append((target.name, lineno, rid, b[:150], sorted(files)))

        if not quotes:
            continue
        rows_checked += 1

        for q in quotes:
            nq = norm(q)
            if not files:
                if uncap:
                    unresolved.append((target.name, lineno, rid, q[:70],
                                       f"cites uncaptured source ({','.join(sorted(uncap))})"))
                else:
                    unresolved.append((target.name, lineno, rid, q[:70],
                                       f"no captured source resolved from {cited[:40]!r}"))
                continue
            if any(nq in SOURCES[f] for f in files if f in SOURCES):
                continue
            if uncap:
                # X9 case: the cell names captured sources AND explicitly attributes
                # this particular claim to an uncaptured relay-only page. That is
                # honest citation, not fabrication. Reporting it as NOT-FOUND was a
                # false positive on the first run.
                unresolved.append((target.name, lineno, rid, q[:70],
                                   f"claim attributed to uncaptured source ({','.join(sorted(uncap))})"))
                continue
            missing += 1
            findings.append((target.name, lineno, rid, q, sorted(files)))

print("=" * 100)
print("CITATION INTEGRITY — mechanical half: does the cited source contain the quoted text?")
print(f"positive control PASSED ({CONTROL[0]})")
print("Scope: QUOTED spans >=25 chars in table rows of the canonical file and the audit record.")
print("NOT checked: whether a paraphrase is fair. That needs eyes.")
print("=" * 100)
print(f"rows with quotations checked: {rows_checked}")
print(f"quotations NOT found in cited source: {missing}")
print(f"quotations whose source could not be resolved: {len(unresolved)}")

if findings:
    print("\n" + "=" * 100)
    print("NOT FOUND IN CITED SOURCE")
    print("=" * 100)
    for f, ln, rid, q, files in findings:
        print(f"\n  {f}:{ln}  [{rid}]  cites {', '.join(files)}")
        print(f"    \"{q[:160]}\"")

if unresolved:
    print("\n" + "=" * 100)
    print("UNRESOLVED — cannot be checked (not a pass)")
    print("=" * 100)
    for f, ln, rid, q, why in unresolved[:40]:
        print(f"  {f}:{ln} [{rid}] {why}")
        print(f"    \"{q}...\"")

print("\n" + "=" * 100)
print(f"BOLD CLAIMS NOT PRESENT VERBATIM IN CITED SOURCE: {len(bold_misses)}")
print("Paraphrase is legitimate here — this is a WORKLIST FOR EYES, not a finding list.")
print("X2 must appear below; if it does not, this extension is broken.")
print("=" * 100)
for f, ln, rid, b, files in bold_misses:
    print(f"  {f.split('/')[-1][:28]:<30}:{ln:<5} [{rid:<4}] {b[:96]}")

sys.exit(1 if findings else 0)
