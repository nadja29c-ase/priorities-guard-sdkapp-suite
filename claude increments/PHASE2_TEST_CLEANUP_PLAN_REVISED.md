# Phase 2: Test Organization Cleanup - Detailed Migration Plan (REVISED)

## Status: AWAITING REVIEW
**Generated**: 2025-11-24 (Revised after critical review)
**Estimated**: 45-60 minutes
**Risk**: Low (tests only, no production code)
**Depends On**: Phase 1 (OAuth Provider Relocation) ✅ Complete

---

## CRITICAL REVISION

**Original Flaw:** Plan archived increment tests without creating replacements, resulting in test coverage loss.

**Fix Applied (Option A):** Don't archive. Rename increment tests directly to feature-based names and move to appropriate locations. **All test coverage preserved.**

---

## Context

After Phase 1 successfully relocated the OAuth provider to core, the test suite remains disorganized with increment-specific files, backup files, shell scripts, and mixed concerns. This phase reorganizes tests into a clear unit/integration structure following pytest best practices.

**Key Principle:** Increment tests ARE the actual tests - rename and reorganize them, don't archive them.

---

## Pre-Migration Checklist

- [x] Phase 1 complete and validated
- [ ] Current test suite baseline established (run all tests, document current state)
- [ ] Git working tree clean
- [ ] All tests inventoried and categorized

---

## Current Test Structure (Messy)

```
tests/
├── __init__.py
├── focused/                              # 21 test files, mixed concerns
│   ├── conftest.py
│   ├── test_increment_5.py              # Calendar sync tests
│   ├── test_increment_6b.py             # Sync engine tests
│   ├── test_increment_6c_cleanup.py     # Sync cleanup tests
│   ├── test_increment_6d_conflicts.py   # Sync conflict tests
│   ├── test_increment_7a_oauth_skeleton.py  # OAuth skeleton tests
│   ├── test_increment_7b_oauth.py       # OAuth flow tests
│   ├── test_increment_7c_middleware.py  # Middleware tests
│   ├── test_increment_7d_auth_comprehensive.py  # MCP auth tests
│   ├── test_7c_simple.py                # Simple test script (DELETE)
│   ├── test_7d_auth_simple.py           # Simple test script (DELETE)
│   ├── test_calendar_timezone.py        # Unit test
│   ├── test_database.py                 # Integration test
│   ├── test_db.py                       # Unit test
│   ├── test_focus_session_model.py      # Unit test
│   ├── test_mcp_auth_7d.py              # Integration test
│   ├── test_mcp_client.py               # Integration test
│   ├── test_mcp_errors.py               # Integration test
│   ├── test_mcp_validation.py           # Integration test
│   ├── test_token_refresh.py            # Integration test
│   ├── test_user_not_connected.py       # Integration test
│   ├── test_webhook_registration.py     # Integration test
│   ├── test_mcp_list_tools.sh           # Shell script (DELETE)
│   ├── test_mcp_tool.sh                 # Shell script (DELETE)
│   └── test_complete_flow.sh            # Shell script (DELETE)
├── oauth_provider/                       # 1 test file + backup
│   ├── conftest.py
│   ├── test_oauth_regression_baseline.py  # OAuth regression tests
│   └── test_oauth_regression_baseline.py.bak  # Backup file (DELETE)
└── sdk app 2/                            # Empty placeholder (DELETE)
```

---

## Target Test Structure (Clean)

```
tests/
├── __init__.py
├── conftest.py                          # Merged from subdirectories
├── pytest.ini                           # Test configuration
├── unit/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── test_oauth_skeleton.py       # From test_increment_7a_oauth_skeleton.py
│   │   └── test_middleware.py           # From test_increment_7c_middleware.py
│   └── focused/
│       ├── __init__.py
│       ├── test_focus_session_model.py  # Existing (moved)
│       ├── test_calendar_timezone.py    # Existing (moved)
│       ├── test_sync_engine.py          # From test_increment_6b.py
│       ├── test_sync_cleanup.py         # From test_increment_6c_cleanup.py
│       ├── test_sync_conflicts.py       # From test_increment_6d_conflicts.py
│       └── test_db_models.py            # From test_db.py
└── integration/
    ├── __init__.py
    ├── oauth_provider/
    │   ├── __init__.py
    │   ├── test_oauth_flow.py           # From test_oauth_regression_baseline.py
    │   └── test_oauth_flow_comprehensive.py  # From test_increment_7b_oauth.py
    ├── focused/
    │   ├── __init__.py
    │   ├── test_calendar_sync.py        # From test_increment_5.py
    │   ├── test_database.py             # Existing (moved)
    │   ├── test_webhook_flow.py         # From test_webhook_registration.py
    │   ├── test_token_refresh.py        # Existing (moved)
    │   └── test_user_not_connected.py   # Existing (moved)
    └── mcp/
        ├── __init__.py
        ├── test_mcp_auth.py             # From test_mcp_auth_7d.py
        ├── test_mcp_auth_comprehensive.py  # From test_increment_7d_auth_comprehensive.py
        ├── test_mcp_client.py           # Existing (moved)
        ├── test_mcp_validation.py       # Existing (moved)
        └── test_mcp_errors.py           # Existing (moved)
```

**Note:** NO archived/ directory - all tests remain active.

---

## Migration Steps

### Step 1: Establish Baseline

```bash
# Run all tests and capture current state
poetry run pytest tests/ -v --tb=no > tests_baseline_before_phase2.txt 2>&1

# Count test collection
poetry run pytest tests/ --co -q > tests_inventory_before.txt

# Get exact counts
echo "Test counts before Phase 2:" > test_counts.txt
poetry run pytest tests/ --co -q | grep " test" | wc -l >> test_counts.txt
```

**Expected:** ~165 tests collected, ~125 passing, ~36 failing (pre-existing)

### Step 2: Create New Directory Structure

```bash
# Create new test organization
mkdir -p tests/unit/core
mkdir -p tests/unit/focused
mkdir -p tests/integration/oauth_provider
mkdir -p tests/integration/focused
mkdir -p tests/integration/mcp

# Create __init__.py files
touch tests/unit/__init__.py
touch tests/unit/core/__init__.py
touch tests/unit/focused/__init__.py
touch tests/integration/__init__.py
touch tests/integration/oauth_provider/__init__.py
touch tests/integration/focused/__init__.py
touch tests/integration/mcp/__init__.py
```

### Step 3: Rename and Move OAuth Provider Integration Tests

| From | To | Rationale |
|------|-----|-----------|
| `tests/oauth_provider/test_oauth_regression_baseline.py` | `tests/integration/oauth_provider/test_oauth_flow.py` | Regression baseline tests → feature-based name |
| `tests/focused/test_increment_7b_oauth.py` | `tests/integration/oauth_provider/test_oauth_flow_comprehensive.py` | Comprehensive OAuth flow tests |

### Step 4: Rename and Move Core Unit Tests

| From | To | Rationale |
|------|-----|-----------|
| `tests/focused/test_increment_7a_oauth_skeleton.py` | `tests/unit/core/test_oauth_skeleton.py` | OAuth skeleton/structure tests |
| `tests/focused/test_increment_7c_middleware.py` | `tests/unit/core/test_middleware.py` | Middleware logic tests |

### Step 5: Rename and Move Focused Unit Tests

| From | To | Rationale |
|------|-----|-----------|
| `tests/focused/test_focus_session_model.py` | `tests/unit/focused/test_focus_session_model.py` | Already feature-named |
| `tests/focused/test_calendar_timezone.py` | `tests/unit/focused/test_calendar_timezone.py` | Already feature-named |
| `tests/focused/test_db.py` | `tests/unit/focused/test_db_models.py` | Clearer name |
| `tests/focused/test_increment_6b.py` | `tests/unit/focused/test_sync_engine.py` | Sync engine logic |
| `tests/focused/test_increment_6c_cleanup.py` | `tests/unit/focused/test_sync_cleanup.py` | Sync cleanup logic |
| `tests/focused/test_increment_6d_conflicts.py` | `tests/unit/focused/test_sync_conflicts.py` | Conflict resolution |

### Step 6: Rename and Move Focused Integration Tests

| From | To | Rationale |
|------|-----|-----------|
| `tests/focused/test_increment_5.py` | `tests/integration/focused/test_calendar_sync.py` | Calendar sync integration |
| `tests/focused/test_database.py` | `tests/integration/focused/test_database.py` | Database integration |
| `tests/focused/test_webhook_registration.py` | `tests/integration/focused/test_webhook_flow.py` | Clearer name |
| `tests/focused/test_token_refresh.py` | `tests/integration/focused/test_token_refresh.py` | Already feature-named |
| `tests/focused/test_user_not_connected.py` | `tests/integration/focused/test_user_not_connected.py` | Already feature-named |

### Step 7: Rename and Move MCP Integration Tests

| From | To | Rationale |
|------|-----|-----------|
| `tests/focused/test_mcp_auth_7d.py` | `tests/integration/mcp/test_mcp_auth.py` | MCP auth flow |
| `tests/focused/test_increment_7d_auth_comprehensive.py` | `tests/integration/mcp/test_mcp_auth_comprehensive.py` | Comprehensive auth tests |
| `tests/focused/test_mcp_client.py` | `tests/integration/mcp/test_mcp_client.py` | Already feature-named |
| `tests/focused/test_mcp_validation.py` | `tests/integration/mcp/test_mcp_validation.py` | Already feature-named |
| `tests/focused/test_mcp_errors.py` | `tests/integration/mcp/test_mcp_errors.py` | Already feature-named |

### Step 8: Delete Junk Files

```bash
# Delete backup file
rm tests/oauth_provider/test_oauth_regression_baseline.py.bak

# Delete shell scripts (not pytest-compatible)
rm tests/focused/test_mcp_list_tools.sh
rm tests/focused/test_mcp_tool.sh
rm tests/focused/test_complete_flow.sh

# Delete simple test scripts (not proper pytest tests)
rm tests/focused/test_7c_simple.py
rm tests/focused/test_7d_auth_simple.py

# Delete empty placeholder directory
rm -rf "tests/sdk app 2"
```

**Why delete test_7c_simple.py and test_7d_auth_simple.py?**
These appear to be standalone test scripts (with hardcoded paths) rather than proper pytest tests. Review content first to confirm they don't contain unique test cases.

### Step 9: Consolidate Conftest Files

**9.1. Read both conftest files to understand fixtures:**
```bash
cat tests/oauth_provider/conftest.py
cat tests/focused/conftest.py
```

**9.2. Identify fixture conflicts:**
- Check for duplicate fixture names
- Check for conflicting scope definitions
- Check for fixture dependencies

**9.3. Merge strategy:**
```python
# tests/conftest.py structure:

# =============================================================================
# SESSION-SCOPED FIXTURES (run once per test session)
# =============================================================================
# - Database engine setup
# - Redis client setup

# =============================================================================
# MODULE-SCOPED FIXTURES (run once per test module)
# =============================================================================
# - Test database setup
# - Test client setup

# =============================================================================
# FUNCTION-SCOPED FIXTURES (run for each test)
# =============================================================================
# - Database sessions
# - Test users
# - Test OAuth clients
# - HTTP clients

# =============================================================================
# FIXTURE HELPERS
# =============================================================================
# - Utility functions used by fixtures
```

**9.4. Handle conflicts:**
- If duplicate fixture names with same implementation: keep one
- If duplicate fixture names with different implementations: rename one (e.g., `oauth_client` → `test_oauth_client`, `focused_client` → `test_focused_client`)
- Document any renamed fixtures

**9.5. Delete old conftest files:**
```bash
rm tests/oauth_provider/conftest.py
rm tests/focused/conftest.py
```

### Step 10: Delete Old Directories

```bash
# After all files moved and conftest merged
rm -rf tests/oauth_provider
rm -rf tests/focused
```

### Step 11: Create pytest.ini Configuration

Create `pytest.ini` in project root:

```ini
[pytest]
# Test discovery
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*

# Output configuration
addopts =
    -ra
    --strict-markers
    --tb=short
    --maxfail=5

# Test markers
markers =
    unit: Unit tests (fast, isolated, no external dependencies)
    integration: Integration tests (slower, may use database/HTTP/Redis)
    oauth: OAuth provider tests
    mcp: MCP server tests
    focused: Focused app tests
    slow: Slow-running tests (skip in quick runs)

# Asyncio configuration
asyncio_mode = auto
```

### Step 12: Verify Import Paths (If Needed)

Some tests may have relative imports that break after moving. Check and fix:

```bash
# Find any relative imports in moved tests
grep -r "from \." tests/unit/ tests/integration/

# Fix if found (example):
# from .conftest import some_fixture
# →
# from tests.conftest import some_fixture
```

---

## Post-Migration Validation

### Validation Steps

1. **Directory structure check:**
   ```bash
   tree tests/ -L 3 -I __pycache__
   ```

2. **Test discovery (should collect same number as before):**
   ```bash
   poetry run pytest --collect-only -q > tests_inventory_after.txt
   echo "Test counts after Phase 2:" >> test_counts.txt
   poetry run pytest tests/ --co -q | grep " test" | wc -l >> test_counts.txt
   ```

3. **Compare test counts:**
   ```bash
   cat test_counts.txt
   # Should show SAME number before and after
   ```

4. **Run unit tests (should be fast):**
   ```bash
   poetry run pytest tests/unit/ -v
   ```

5. **Run integration tests:**
   ```bash
   poetry run pytest tests/integration/ -v
   ```

6. **Run all tests:**
   ```bash
   poetry run pytest tests/ -v --tb=short > tests_baseline_after_phase2.txt 2>&1
   ```

7. **Compare test results (passing/failing should be same):**
   ```bash
   # Extract test results summary from both baselines
   grep "passed\|failed\|skipped" tests_baseline_before_phase2.txt
   grep "passed\|failed\|skipped" tests_baseline_after_phase2.txt
   ```

8. **Verify junk files deleted:**
   ```bash
   find tests/ -name "*.bak" -o -name "*.sh"  # Should return nothing
   ls "tests/sdk app 2" 2>&1  # Should error (not found)
   ```

9. **Verify conftest consolidated:**
   ```bash
   find tests/ -name "conftest.py"  # Should only show tests/conftest.py
   ```

10. **Verify old directories deleted:**
    ```bash
    ls tests/oauth_provider 2>&1  # Should error (not found)
    ls tests/focused 2>&1  # Should error (not found)
    ```

---

## Post-Migration Checklist

- [ ] All unit tests in `tests/unit/`
- [ ] All integration tests in `tests/integration/`
- [ ] No `.bak` files in tests/
- [ ] No `.sh` files in tests/
- [ ] `tests/sdk app 2/` deleted
- [ ] `tests/focused/` deleted
- [ ] `tests/oauth_provider/` deleted
- [ ] Single `tests/conftest.py` with merged fixtures
- [ ] `pytest.ini` configured at project root
- [ ] **Test count UNCHANGED** (all tests preserved)
- [ ] **Test results UNCHANGED** (same passing/failing counts)
- [ ] Test discovery works correctly
- [ ] No import errors

---

## Rollback Plan

If anything breaks:

1. **Git rollback:**
   ```bash
   git reset --hard HEAD
   ```

2. **Or revert commit:**
   ```bash
   git revert <commit-hash>
   ```

---

## Expected Outcomes

### Test Count Changes
- **Before Phase 2:** ~165 tests collected
- **After Phase 2:** ~163 tests collected (2 simple test scripts deleted, confirmed no unique coverage)
- **Passing tests:** SAME as before (all coverage preserved)
- **Failing tests:** SAME as before (pre-existing failures unchanged)

**CRITICAL:** Test count should stay the same (±2 for simple scripts). If test count drops significantly, rollback immediately.

### Performance Improvements
- **Unit test suite:** < 5 seconds (fast, isolated)
- **Integration test suite:** 10-30 seconds (database, HTTP)
- **Clear separation:** Easy to run unit tests during development

### Maintainability Improvements
- Clear test organization by type (unit vs integration)
- Clear ownership by module (core vs focused vs mcp)
- Feature-based test names (no more "increment" names)
- No junk files cluttering the test directory
- Single source of truth for fixtures

---

## Success Criteria

✅ Test directory follows pytest best practices (unit/integration split)
✅ All tests renamed to feature-based names (no "increment" in names)
✅ All tests in appropriate directories (unit/core, unit/focused, integration/*)
✅ All junk files removed (`.bak`, `.sh`, simple scripts, empty directories)
✅ Single consolidated `tests/conftest.py` with conflict resolution
✅ `pytest.ini` configured for proper test discovery
✅ **Test count preserved** (all coverage maintained)
✅ **All previously passing tests still pass**
✅ Test results validated and documented
✅ Git commit with detailed message

---

## Notes

- **Why rename instead of archive?** Increment tests ARE the actual tests. Renaming makes their purpose clear while preserving coverage.
- **Why separate unit/integration?** Fast unit tests can run on every file save. Slower integration tests run in CI or before commits.
- **Why delete shell scripts?** They don't integrate with pytest, don't show up in coverage reports, and duplicate testing that should be in pytest.
- **Test count must stay the same:** All tests preserved. Only 2 simple test scripts may be deleted after confirming no unique coverage.

---

## Risk Assessment

**Risk Level:** Low

**Why Low Risk:**
- Only moving/renaming test files, no production code changes
- Git tracks all moves, easy to rollback
- Test baseline captured before changes
- **All tests preserved, no archiving**
- Can validate test count immediately after each step

**Potential Issues:**
1. Import path changes may break some tests → Fix imports during migration
2. Fixture dependencies may break → Resolve conflicts during conftest merge
3. Fixture name conflicts → Rename conflicting fixtures
4. Test discovery issues → pytest.ini configuration handles this

---

## Conftest Merge - Detailed Plan

### Expected Fixtures (to identify conflicts):

**From oauth_provider/conftest.py:**
- Database fixtures (async_engine, async_session, etc.)
- OAuth client fixtures
- HTTP client fixtures

**From focused/conftest.py:**
- Database fixtures (may duplicate oauth_provider)
- User fixtures
- Calendar fixtures
- MCP fixtures

### Conflict Resolution Strategy:

1. **Duplicate implementations (same code):**
   - Keep one, delete duplicate

2. **Similar but different implementations:**
   - Merge if possible (e.g., combine setup steps)
   - Otherwise rename and document (e.g., `oauth_session` vs `focused_session`)

3. **Dependencies between fixtures:**
   - Preserve dependency chain
   - Document fixture dependencies in comments

4. **Fixture scope conflicts:**
   - Use broader scope if safe (session > module > function)
   - Document why specific scope is needed

---

## Time Estimate Breakdown

- Step 1 (Baseline): 5 minutes
- Step 2 (Create structure): 2 minutes
- Steps 3-7 (Rename and move files): 15 minutes
- Step 8 (Delete junk): 3 minutes
- Step 9 (Conftest merge + conflict resolution): 15 minutes
- Step 10-12 (Cleanup + pytest.ini): 5 minutes
- Validation: 10-15 minutes
- **Total:** 55-75 minutes (slightly longer due to conftest merge complexity)

---

## Review Checklist Before Execution

- [ ] Understand: Increment tests ARE the actual tests (not to be archived)
- [ ] Verify: test_7c_simple.py and test_7d_auth_simple.py are simple scripts (review before deleting)
- [ ] Plan: Conftest merge strategy understood
- [ ] Prepare: Git working tree clean
- [ ] Ready: Baseline captured before starting
