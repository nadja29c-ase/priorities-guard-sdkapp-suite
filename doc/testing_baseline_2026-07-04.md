# Test Baseline — 2026-07-04

**Total tests:** ~2292
**Status:** ~154 known-red in included suite, 5 excluded behind `mcp_focused` collection ignore
**Tag:** Re-baseline post-submission (MindSort Claude submission is the priority)

---

## Discriminated Baseline

### Excluded (collection ignore in conftest.py)

| Area | Count | Nature | Action |
|------|-------|--------|--------|
| `tests/unit/mcp_focused/` | 5 | Focused app deprecated (technically infeasible, ships nothing). Stale mocks, removed helpers. | Excluded via `collect_ignore`. Lift exclusion only if Focused is revisited. |

### Included but known-red

| Area | Count | Nature | Isolation-verified |
|------|-------|--------|-------------------|
| `tests/unit/mcp_priority_guardian/` | ~130 | Stale mocks against old service signatures, missing fixtures, removed dependencies. PG-OpenAI is stable in production; tests lag refactors. | Yes — failures are test staleness, not product bugs. |
| `tests/unit/mcp_pg_claude/` | 5 | Stale mocks (same pattern as PG-OpenAI). PG-Claude is deprecated pending Claude MCP Directory submission. | Yes — test staleness. |
| `tests/unit/celery/` | 2 | Celery beat schedule tests expect old task names or timing. Tasks work in production. | Yes — test staleness. |
| `tests/unit/core/` + `tests/unit/oauth_provider/` | 5 | Mixed. 2 confirmed stale (old OAuth validator signatures). **3 untriaged** — see below. | Partial — 3 require triage. |

### Untriaged (core/oauth, 3 tests)

These three tests failed in the baseline run but were not root-caused. They may be:
- Stale mocks (same pattern as above) — likely
- Real regressions — unlikely but not ruled out
- Environment-specific (missing test DB, Redis, etc.) — possible

**Action required:** Triage before post-submission re-baseline. Run in isolation, inspect failure messages, classify.

```
tests/unit/oauth_provider/test_<TBD>.py  # Exact test names to be filled from next baseline run
```

---

## How to run full baseline

```bash
# Full suite (excludes mcp_focused, excludes live-marked tests)
poetry run pytest tests/ -v --tb=short 2>&1 | tee baseline_run.log

# Count by outcome
grep -c "PASSED" baseline_run.log
grep -c "FAILED" baseline_run.log
grep -c "ERROR" baseline_run.log
```

---

## Re-baseline checklist (post-submission)

1. Run full suite, capture log
2. Diff against this baseline — new failures are regressions, resolved failures are fixed tests
3. Triage the 3 untriaged core/oauth tests
4. Update this doc with new counts and any new classifications
5. If green-minus-nothing achieved, update CLAUDE.md to reflect clean baseline

---

## History

- **2026-07-04:** Initial discriminated baseline created. Prior "212 tests" claims were subset runs against `tests/unit/oauth_discovery/` only; full suite is ~2292.
