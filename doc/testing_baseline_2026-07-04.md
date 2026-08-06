# Test Baseline — 2026-07-04

**Total tests:** ~2292 — ⚠️ **unverified, and probably wrong. See the amendment below.**
**Status:** ~154 known-red in included suite, 5 excluded behind `mcp_focused` collection ignore
**Tag:** Re-baseline post-submission (MindSort Claude submission is the priority)

---

## ⚠️ AMENDMENT 2026-08-06 — every count in this document is suspect

Found while upgrading the PG-Claude widget SDK (increment Claude-A). Recorded here because a
known-false claim in an authoritative record is worse than a missing one, and CLAUDE.md rule 4
points readers at this file.

**`addopts` in `pytest.ini:26` contains `--maxfail=5`, and has since 2025-11-24** — seven months
before this baseline was taken. It applies to every invocation that does not override it, including
the documented command at "How to run full baseline" below, which does **not** override it.

Consequences:

1. **A run using the documented command stops at the 5th failure.** It cannot produce "~154
   known-red", so the headline figures were not produced by the procedure this document describes.
   Where they came from is unknown.
2. **At least one per-area count was a stopping condition recorded as a measurement.**
   `tests/unit/mcp_pg_claude/` was listed as 5; measured with the cap lifted it is **10**. That row
   is corrected below. The other rows have **not** been re-measured and are not to be trusted.
3. **The aggregate is stale independently of the cap.** This repo's own commit `eb3373c7`
   (2026-08-03) records a full-suite run of **321 failed / 14 errors / 3206 → 3216 passed** — against
   a baseline claiming ~2292 total and ~154 red.

**No corrected aggregate is stated here, because none was measured.** Re-baselining requires a full
run with the cap lifted (`--maxfail=1000` or similar) and is its own piece of work, tracked as the
test-infrastructure increment. Until then, treat every unamended number below as unverified.

**Method note.** An instrument's bound is not the thing it measures. A truncated run reports the
truncation; a scan window reports the window. Numbers copied out of either are artifacts unless the
bound was lifted first.

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
| `tests/unit/mcp_pg_claude/` | **10** ⚠️ corrected 2026-08-06 — was recorded as 5 | **The "5" was `--maxfail=5`, not a count.** Measured with the cap lifted: 10 failed / 21 passed in `test_scaffold.py`. Causes are NOT "stale mocks": 4 hardcoded `ui://pg-claude/dashboard-v1.html` literals against a v4 runtime (2 reachable, fixed 2026-08-06 to compare against imported `WIDGET_URI`; 2 sit in tests blocked earlier); 3 `ImportError` on `adapt_get_priorities_meta`, renamed to `adapt_widget_tool_meta`; plus `test_health_returns_ok`, `test_list_tools_annotations_match_registry`, two adapter list-stripping tests, `test_non_widget_tools_have_no_meta`. **PG-Claude is NOT deprecated** — it is the app being submitted to the Claude MCP Directory. The same false deprecation appears at `OPERATIONS_PREDEPLOY.md:301`. | Partly — 8 remain, unverified individually. |
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
