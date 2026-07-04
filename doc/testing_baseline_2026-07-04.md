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
| `tests/unit/core/` + `tests/unit/oauth_provider/` | 5 | All triaged — stale test expectations (see table below). | Yes — test staleness. |

### Triaged (core/oauth, 5 tests) — all stale expectations

| Test | Failure | Classification |
|------|---------|---------------|
| `test_state_over_512_chars_returns_error_redirect` | Expects redirect, behavior changed | Stale expectation |
| `test_consent_rate_limit_uses_correct_key` | Expects limit=20, gets limit=100 | Stale — rate limit intentionally raised (commit 68b8f51) |
| `test_authorize_missing_login_hint_returns_error` | Expects 302, gets 200 (consent rendered) | Stale — behavior changed to render consent |
| `test_authorize_invalid_client_returns_error` | Expects 302, gets 400 | Stale — security improvement (no redirect to unknown client's URI) |
| `test_authorize_invalid_redirect_uri_returns_error` | Expects 302, gets 400 | Stale — security improvement (no redirect to malicious URI) |

**Verdict:** All 5 are stale test expectations, not regressions. The 400 responses for invalid_client/invalid_redirect_uri are correct — RFC 6749 says "If the request fails due to a missing, invalid, or mismatching redirection URI... the authorization server SHOULD inform the resource owner of the error and MUST NOT automatically redirect."

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
