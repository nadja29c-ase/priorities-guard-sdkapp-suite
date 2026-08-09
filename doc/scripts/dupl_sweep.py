"""_dupl divergence sweep — symbol-level, not size-level.

Method note (this is the point of the whole exercise):
  Line-count delta is worse than useless here. It produces a FALSE ALARM on
  mindsort_claude/mcp_auth_dupl.py (-84%, but safe: it delegates to the source)
  and a FALSE NEGATIVE on priority_guardian_claude/server_dupl.py (-11%, but it
  had silently dropped JWT validation, scope enforcement and the 413 guard — the
  A22 defect). So we compare SYMBOLS, and for each symbol we separate STRUCTURE
  from LITERALS:

    - structure identical, literals differ  -> CONFIG-ONLY (the claimed reason)
    - structure differs                     -> DIVERGENT (needs classification)
    - in source, absent from _dupl          -> DROPPED (the A22 shape)
    - in _dupl only                         -> ADDED

  DROPPED is called out separately because a symbol that simply isn't there is
  invisible to any same-name comparison.
"""
import ast, re, sys
from pathlib import Path

ROOT = Path("/Users/nadja/Desktop/Priority Guard Suite/priority-guardian")
CLAUDE_TREES = ["mcp_server/priority_guardian_claude", "mcp_server/mindsort_claude"]

SRC_RE = re.compile(r"(mcp_server/[A-Za-z0-9_/]+\.py)")


def stated_source(path: Path):
    """Resolve the source a _dupl file CLAIMS to mirror, from its header."""
    head = "".join(path.read_text().splitlines(keepends=True)[:12])
    for m in SRC_RE.finditer(head):
        cand = ROOT / m.group(1)
        if cand.exists() and cand != path:
            return cand, head
    return None, head


class Strip(ast.NodeTransformer):
    """Drop docstrings so prose changes don't read as behaviour changes."""
    def _strip(self, node):
        self.generic_visit(node)
        b = node.body
        if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant) \
           and isinstance(b[0].value.value, str):
            node.body = b[1:] or [ast.Pass()]
        return node
    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _strip
    visit_Module = _strip


class Blank(ast.NodeTransformer):
    """Normalise every constant, so config VALUES stop counting as divergence."""
    def visit_Constant(self, node):
        return ast.copy_location(ast.Constant(value="<K>"), node)


def symbols(path: Path):
    """Top-level defs/classes plus class methods, as qualified names."""
    tree = Strip().visit(ast.parse(path.read_text()))
    out = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out[node.name] = node
            if isinstance(node, ast.ClassDef):
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        out[f"{node.name}.{sub.name}"] = sub
    return out


def full(n):
    return ast.dump(n, annotate_fields=False)


def struct(n):
    import copy
    return ast.dump(Blank().visit(copy.deepcopy(n)), annotate_fields=False)


def reexports(path: Path, src: Path):
    """Does the _dupl import symbols back out of its source? Explains absence."""
    mod = str(src.relative_to(ROOT)).replace("/", ".")[:-3]
    txt = path.read_text()
    return f"from {mod} import" in txt or f"import {mod} as" in txt


rows, findings = [], []
for tree_dir in CLAUDE_TREES:
    for f in sorted((ROOT / tree_dir).rglob("*_dupl.py")):
        rel = str(f.relative_to(ROOT))
        src, head = stated_source(f)
        if src is None:
            findings.append((rel, "NO-SOURCE", "header states no resolvable source file"))
            rows.append((rel, "—", 0, 0, 0, 0, False))
            continue

        d, s = symbols(f), symbols(src)
        deleg = reexports(f, src)

        dropped = [k for k in s if k not in d]
        added = [k for k in d if k not in s]
        common = [k for k in d if k in s]

        cfg = [k for k in common if full(d[k]) != full(s[k]) and struct(d[k]) == struct(s[k])]
        div = [k for k in common if struct(d[k]) != struct(s[k])]

        rows.append((rel, str(src.relative_to(ROOT)), len(dropped), len(div), len(cfg), len(added), deleg))

        for k in dropped:
            if not deleg:
                findings.append((rel, "DROPPED", f"{k} — in source, absent here (A22 shape)"))
        for k in div:
            findings.append((rel, "DIVERGENT", f"{k} — structure differs, not just constants"))

print("=" * 108)
print("SCOPE: Claude trees only — priority_guardian_claude/, mindsort_claude/. OpenAI trees are SOURCES, not swept.")
print("=" * 108)
print(f"{'_dupl file':<52}{'drop':>5}{'diverge':>9}{'config':>8}{'added':>7}  {'delegates'}")
print("-" * 108)
for rel, src, nd, nv, nc, na, dg in rows:
    print(f"{rel.replace('mcp_server/',''):<52}{nd:>5}{nv:>9}{nc:>8}{na:>7}  {'yes' if dg else ''}")

print()
print("=" * 108)
print(f"FINDINGS ({len(findings)}) — DROPPED and DIVERGENT only; config-only and delegated absences excluded")
print("=" * 108)
cur = None
for rel, kind, msg in findings:
    if rel != cur:
        print(f"\n### {rel.replace('mcp_server/','')}")
        cur = rel
    print(f"  [{kind}] {msg}")
