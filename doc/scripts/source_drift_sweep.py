"""Detect upstream drift in doc/Claude_Compliance/sources_raw/.

WHY THIS EXISTS. Drift in lazy-authentication.raw.md was found BY ACCIDENT — a
re-fetch of a file wrongly believed missing. Eleven sources, captured over weeks,
and nothing detected any of them changing. The canonical file's rows all trace
back to these documents, so a requirement that moved since capture is invisible.

WHAT IT DOES NOT DO. It never overwrites a captured file. Re-capture is a
deliberate act with provenance consequences — a paste corroborates a fetch, a
fetch does not replace one. This reports; a human decides.

    python doc/scripts/source_drift_sweep.py            # fetch + compare
    python doc/scripts/source_drift_sweep.py --write-manifest

BOUND, load-bearing: the .md endpoints carry no Last-Modified and no ETag, so a
fetch cannot be dated from its own contents. Drift is DETECTABLE but never
DATEABLE — "changed since capture" is the strongest claim available, never "changed
on date X".
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "doc/Claude_Compliance/sources_raw"
MANIFEST = SRC / "MANIFEST.json"
SCRATCH = Path("/tmp/source_drift_fetch")

# provenance category, verbatim from PROVENANCE.md's own assessment
BASE = "https://claude.com/docs/connectors/building"
SOURCES = {
    "authentication.raw.md":            (f"{BASE}/authentication.md",                  "fetch, paste-corroborated x3 — CLOSED"),
    "cross-compatibility.raw.md":       (f"{BASE}/mcp-apps/cross-compatibility.md",    "fetch only — page pasted, not compared"),
    "design-guidelines.raw.md":         (f"{BASE}/mcp-apps/design-guidelines.md",      "fetch only — page pasted twice, agreed"),
    "instance-supersession.raw.md":     (f"{BASE}/mcp-apps/instance-supersession.md",  "fetch only — page pasted, not compared"),
    "lazy-authentication.raw.md":       (f"{BASE}/lazy-authentication.md",             "fetch only — NOT cross-checked"),
    "review-criteria.raw.md":           (f"{BASE}/review-criteria.md",                 "FETCH ONLY — never pasted, impossible to corroborate"),
    "submission.raw.md":                (f"{BASE}/submission.md",                      "fetch, relay-corroborated — 8 facts"),
    "testing.raw.md":                   (f"{BASE}/testing.md",                         "fetch only — NOT cross-checked"),
    "transparent-theming.raw.md":       (f"{BASE}/mcp-apps/transparent-theming.md",    "fetch, paste-corroborated 60 lines"),
    "software-directory-policy.raw.md": ("https://support.claude.com/en/articles/13145358-anthropic-software-directory-policy.md", "fetch, paste-corroborated — pub date 2026-04-15 from paste only"),
    "software-directory-terms.raw.md":  ("https://support.claude.com/en/articles/13145338-anthropic-software-directory-terms.md",  "fetch, content corroborated — pub date 2026-03-16 from paste only"),
}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def fetch(url: str) -> bytes | None:
    r = subprocess.run(["curl", "-sS", "--max-time", "30", url],
                       capture_output=True)
    return r.stdout if r.returncode == 0 and r.stdout else None


def main() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    write_manifest = "--write-manifest" in sys.argv
    manifest, rows, drifted = {}, [], []

    for name, (url, prov) in sorted(SOURCES.items()):
        captured_p = SRC / name
        if not captured_p.exists():
            rows.append((name, "MISSING", "-", "-")); continue

        captured = captured_p.read_bytes()
        c_hash = sha(captured)
        manifest[name] = {
            "sha256": c_hash,
            "bytes": len(captured),
            "url": url,
            "provenance": prov,
            "captured_mtime_utc": None,
        }

        live = fetch(url)
        if live is None:
            rows.append((name, "FETCH-FAILED", c_hash[:12], "-")); continue

        (SCRATCH / name).write_bytes(live)   # scratch only — never the repo copy
        l_hash = sha(live)
        status = "IDENTICAL" if l_hash == c_hash else "DRIFTED"
        if status == "DRIFTED":
            drifted.append(name)
        rows.append((name, status, c_hash[:12], l_hash[:12]))

    print("=" * 104)
    print("SOURCE DRIFT SWEEP — 11 captured files vs live fetch")
    print("BOUND: .md endpoints carry no Last-Modified / no ETag. Drift is detectable, NEVER dateable.")
    print("Captured files are NOT modified by this script.")
    print("=" * 104)
    print(f"{'file':<36}{'status':<15}{'captured':<15}{'live':<15}")
    print("-" * 104)
    for n, s, c, l in rows:
        print(f"{n:<36}{s:<15}{c:<15}{l:<15}")

    print(f"\n{len(drifted)} of {len(SOURCES)} drifted: {', '.join(drifted) or 'none'}")

    for name in drifted:
        print("\n" + "=" * 104)
        print(f"DIFF — {name}   (captured  ->  live)")
        print("=" * 104)
        subprocess.run(["diff", "-u", str(SRC / name), str(SCRATCH / name)])

    if write_manifest:
        MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        print(f"\nwrote {MANIFEST.relative_to(ROOT)} ({len(manifest)} entries)")

    return 1 if drifted else 0


if __name__ == "__main__":
    sys.exit(main())
