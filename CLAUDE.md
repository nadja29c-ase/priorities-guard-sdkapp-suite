# Claude Code Project Instructions

## Review Discipline

**Hash-verified reviews:** Reviews verify against `git show <commit-hash>:<path>`, never the working tree. Every reviewed round ends with a commit hash in Claude Code's report. This prevents the failure mode where work appears reviewed but was never committed (or was overwritten before commit).

Example verification command:
```bash
git show abc1234:path/to/file.py
```

## Git Safety

See `doc/OPERATIONS_PREDEPLOY.md` for the full pre-deploy checklist. Key rules:

- **Stash-before-overwrite:** Any `git checkout`, `git restore`, or full-file overwrite of tracked files requires `git stash push` first — even "obviously safe" ones.
- **Never amend after hook failure:** Pre-commit hook failures mean the commit didn't happen. Create a NEW commit after fixing, never `--amend` (which would modify the previous commit).
- **Stage specific files:** Prefer `git add <file>` over `git add -A` to avoid accidentally staging secrets or large binaries.

## Test Baseline

Full suite is ~2292 tests. **~154 known-red in included suite** plus 5 excluded behind `mcp_focused`. See `doc/testing_baseline_2026-07-04.md` for the discriminated classification (areas, counts, natures, untriaged items).

Do not assume green-minus-nothing. New failures beyond the baseline are regressions; failures matching the baseline are known-red awaiting post-submission re-baseline.

Run scope-isolation invariant tests after any tool registration change:
```bash
poetry run pytest tests/unit/oauth_discovery/test_tool_scope_invariants.py -v
```

## OAuth Architecture

Four apps, one Authorization Server (`https://www.priority-guard.com`):
- **PG-OpenAI:** Shape #1 (mixed-origin proxy) — LEGACY, not template for new apps
- **MindSort-OpenAI:** Shape #2 (path-qualified AS mount) — reference for new ChatGPT apps
- **PG-Claude:** Shape #3 (root-issuer) — shares registry with PG-OpenAI
- **MindSort-Claude:** Shape #3 (root-issuer) — submission app

See `doc/OAuth/NEW_APP_OAUTH_INTEGRATION.md` for the routing playbook.
