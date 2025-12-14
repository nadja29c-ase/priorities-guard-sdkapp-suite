# Phase 2: Test Organization Cleanup - Detailed Migration Plan

## Status: READY TO EXECUTE
**Generated**: 2025-11-24
**Estimated**: 45-60 minutes
**Risk**: Low (tests only, no production code)
**Depends On**: Phase 1 (OAuth Provider Relocation) ✅ Complete

---

## Context

After Phase 1 successfully relocated the OAuth provider to core, the test suite remains disorganized with increment-specific files, backup files, shell scripts, and mixed concerns. This phase reorganizes tests into a clear unit/integration structure following pytest best practices.

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
│   ├── test_increment_5.py              # Increment-specific
│   ├── test_increment_6b.py             # Increment-specific
│   ├── test_increment_6c_cleanup.py     # Increment-specific
│   ├── test_increment_6d_conflicts.py   # Increment-specific
│   ├── test_increment_7a_oauth_skeleton.py  # Increment-specific
│   ├── test_increment_7b_oauth.py       # Increment-specific (OAuth flow)
│   ├── test_increment_7c_middleware.py  # Increment-specific
│   ├── test_increment_7d_auth_comprehensive.py  # Increment-specific
│   ├── test_7c_simple.py                # Increment-specific
│   ├── test_7d_auth_simple.py           # Increment-specific
│   ├── test_calendar_timezone.py        # Unit test (keep)
│   ├── test_database.py                 # Integration test
│   ├── test_db.py                       # Unit test
│   ├── test_focus_session_model.py      # Unit test (keep)
│   ├── test_mcp_auth_7d.py              # Integration test (keep)
│   ├── test_mcp_client.py               # Integration test
│   ├── test_mcp_errors.py               # Integration test
│   ├── test_mcp_validation.py           # Integration test
│   ├── test_token_refresh.py            # Integration test
│   ├── test_user_not_connected.py       # Integration test
│   ├── test_webhook_registration.py     # Integration test
│   ├── test_mcp_list_tools.sh           # Shell script (delete)
│   ├── test_mcp_tool.sh                 # Shell script (delete)
│   └── test_complete_flow.sh            # Shell script (delete)
├── oauth_provider/                       # 1 test file + backup
│   ├── conftest.py
│   ├── test_oauth_regression_baseline.py
│   └── test_oauth_regression_baseline.py.bak  # Backup file (delete)
└── sdk app 2/                            # Empty placeholder (delete)
```

---

## Target Test Structure (Clean)

```
tests/
├── __init__.py
├── conftest.py                          # Merged from subdirectories
├── unit/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── test_oauth_provider.py      # OAuth provider unit tests
│   │   ├── test_jwt_utils.py           # JWT utility tests
│   │   ├── test_rate_limit.py          # Rate limiting logic
│   │   └── test_middleware.py          # Middleware unit tests
│   └── focused/
│       ├── __init__.py
│       ├── test_focus_session_model.py  # Model tests
│       ├── test_calendar_timezone.py    # Timezone logic
│       ├── test_sync_conflicts.py       # Sync conflict resolution
│       └── test_db_models.py            # Database model tests
├── integration/
│   ├── __init__.py
│   ├── oauth_provider/
│   │   ├── __init__.py
│   │   └── test_oauth_flow.py          # Full OAuth flow tests (regression baseline)
│   ├── focused/
│   │   ├── __init__.py
│   │   ├── test_google_calendar.py     # Calendar integration
│   │   ├── test_webhook_flow.py        # Webhook registration
│   │   ├── test_token_refresh.py       # Token refresh flow
│   │   └── test_user_not_connected.py  # Error scenarios
│   └── mcp/
│       ├── __init__.py
│       ├── test_mcp_auth.py            # MCP authentication flow
│       ├── test_mcp_client.py          # MCP client integration
│       ├── test_mcp_validation.py      # MCP validation
│       └── test_mcp_errors.py          # MCP error handling
└── archived/
    └── increment_tests/                 # Preserved for reference
        ├── test_increment_5.py
        ├── test_increment_6b.py
        ├── test_increment_6c_cleanup.py
        ├── test_increment_6d_conflicts.py
        ├── test_increment_7a_oauth_skeleton.py
        ├── test_increment_7b_oauth.py
        ├── test_increment_7c_middleware.py
        ├── test_increment_7d_auth_comprehensive.py
        ├── test_7c_simple.py
        └── test_7d_auth_simple.py
```

---

## Migration Steps

### Step 1: Establish Baseline

```bash
# Run all tests and capture current state
poetry run pytest tests/ -v --tb=no > tests_baseline_before_phase2.txt 2>&1

# Count passing/failing tests
poetry run pytest tests/ --co -q > tests_inventory.txt
```

**Expected:** ~26 passing (oauth_provider), ~36 failing (pre-existing), ~99 passing (focused)

### Step 2: Create New Directory Structure

```bash
# Create new test organization
mkdir -p tests/unit/core
mkdir -p tests/unit/focused
mkdir -p tests/integration/oauth_provider
mkdir -p tests/integration/focused
mkdir -p tests/integration/mcp
mkdir -p tests/archived/increment_tests

# Create __init__.py files
touch tests/unit/__init__.py
touch tests/unit/core/__init__.py
touch tests/unit/focused/__init__.py
touch tests/integration/__init__.py
touch tests/integration/oauth_provider/__init__.py
touch tests/integration/focused/__init__.py
touch tests/integration/mcp/__init__.py
```

### Step 3: Move OAuth Provider Tests

| From | To | Type |
|------|-----|------|
| `tests/oauth_provider/test_oauth_regression_baseline.py` | `tests/integration/oauth_provider/test_oauth_flow.py` | Integration |
| `tests/oauth_provider/conftest.py` | Merge into `tests/conftest.py` | Fixture |

### Step 4: Move Focused Unit Tests

| From | To | Type |
|------|-----|------|
| `tests/focused/test_focus_session_model.py` | `tests/unit/focused/test_focus_session_model.py` | Unit |
| `tests/focused/test_calendar_timezone.py` | `tests/unit/focused/test_calendar_timezone.py` | Unit |
| `tests/focused/test_db.py` | `tests/unit/focused/test_db_models.py` | Unit |

### Step 5: Move Focused Integration Tests

| From | To | Type |
|------|-----|------|
| `tests/focused/test_database.py` | `tests/integration/focused/test_database.py` | Integration |
| `tests/focused/test_webhook_registration.py` | `tests/integration/focused/test_webhook_flow.py` | Integration |
| `tests/focused/test_token_refresh.py` | `tests/integration/focused/test_token_refresh.py` | Integration |
| `tests/focused/test_user_not_connected.py` | `tests/integration/focused/test_user_not_connected.py` | Integration |

### Step 6: Move MCP Integration Tests

| From | To | Type |
|------|-----|------|
| `tests/focused/test_mcp_auth_7d.py` | `tests/integration/mcp/test_mcp_auth.py` | Integration |
| `tests/focused/test_mcp_client.py` | `tests/integration/mcp/test_mcp_client.py` | Integration |
| `tests/focused/test_mcp_validation.py` | `tests/integration/mcp/test_mcp_validation.py` | Integration |
| `tests/focused/test_mcp_errors.py` | `tests/integration/mcp/test_mcp_errors.py` | Integration |

### Step 7: Move Core/Middleware Tests

| From | To | Type |
|------|-----|------|
| `tests/focused/test_increment_7c_middleware.py` | `tests/unit/core/test_middleware.py` | Unit |

### Step 8: Archive Increment-Specific Tests

Move these to `tests/archived/increment_tests/` (preserve for reference):

```bash
# OAuth increment tests
mv tests/focused/test_increment_7a_oauth_skeleton.py tests/archived/increment_tests/
mv tests/focused/test_increment_7b_oauth.py tests/archived/increment_tests/
mv tests/focused/test_7c_simple.py tests/archived/increment_tests/
mv tests/focused/test_7d_auth_simple.py tests/archived/increment_tests/
mv tests/focused/test_increment_7d_auth_comprehensive.py tests/archived/increment_tests/

# Calendar sync increment tests
mv tests/focused/test_increment_5.py tests/archived/increment_tests/
mv tests/focused/test_increment_6b.py tests/archived/increment_tests/
mv tests/focused/test_increment_6c_cleanup.py tests/archived/increment_tests/
mv tests/focused/test_increment_6d_conflicts.py tests/archived/increment_tests/
```

**Rationale:** These tests are snapshots of specific development increments. They may have overlapping coverage with the consolidated tests. Keep for historical reference but exclude from regular test runs.

### Step 9: Delete Junk Files

```bash
# Delete backup files
rm tests/oauth_provider/test_oauth_regression_baseline.py.bak

# Delete shell scripts (not pytest-compatible)
rm tests/focused/test_mcp_list_tools.sh
rm tests/focused/test_mcp_tool.sh
rm tests/focused/test_complete_flow.sh

# Delete empty placeholder directory
rm -rf "tests/sdk app 2"
```

### Step 10: Consolidate Conftest Files

**Read both conftest files:**
```bash
cat tests/oauth_provider/conftest.py
cat tests/focused/conftest.py
```

**Merge into `tests/conftest.py`:**
- Combine fixtures from both files
- Remove duplicates
- Organize by scope (session, module, function)
- Add section comments

**Delete old conftest files:**
```bash
rm tests/oauth_provider/conftest.py
rm tests/focused/conftest.py
```

### Step 11: Delete Old Directories

```bash
# After all files moved
rm -rf tests/oauth_provider
rm -rf tests/focused
```

### Step 12: Add pytest.ini Configuration

Create `pytest.ini` in project root to configure test discovery:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
# Exclude archived tests from collection
norecursedirs = archived
# Show extra test summary info
addopts =
    -ra
    --strict-markers
    --tb=short
markers =
    unit: Unit tests (fast, isolated)
    integration: Integration tests (slower, external dependencies)
    oauth: OAuth provider tests
    mcp: MCP server tests
    focused: Focused app tests
```

### Step 13: Update Archive Tests (Optional)

Add pytest.skip to all archived increment tests:

```python
import pytest

pytestmark = pytest.mark.skip(reason="Archived increment test - preserved for reference")
```

---

## Post-Migration Validation

### Validation Steps

1. **Directory structure check:**
   ```bash
   tree tests/ -L 3
   ```

2. **Test discovery:**
   ```bash
   poetry run pytest --collect-only
   ```

3. **Run unit tests (should be fast):**
   ```bash
   poetry run pytest tests/unit/ -v
   ```

4. **Run integration tests:**
   ```bash
   poetry run pytest tests/integration/ -v
   ```

5. **Run all tests:**
   ```bash
   poetry run pytest tests/ -v --tb=short > tests_baseline_after_phase2.txt 2>&1
   ```

6. **Compare baselines:**
   ```bash
   diff tests_baseline_before_phase2.txt tests_baseline_after_phase2.txt
   ```

7. **Verify junk files deleted:**
   ```bash
   find tests/ -name "*.bak" -o -name "*.sh"  # Should return nothing
   ls "tests/sdk app 2" 2>&1  # Should error (not found)
   ```

8. **Verify conftest consolidated:**
   ```bash
   find tests/ -name "conftest.py"  # Should only show tests/conftest.py
   ```

---

## Post-Migration Checklist

- [ ] All unit tests in `tests/unit/`
- [ ] All integration tests in `tests/integration/`
- [ ] Increment tests archived in `tests/archived/`
- [ ] No `.bak` files in tests/
- [ ] No `.sh` files in tests/
- [ ] `tests/sdk app 2/` deleted
- [ ] `tests/focused/` deleted
- [ ] `tests/oauth_provider/` deleted
- [ ] Single `tests/conftest.py` with merged fixtures
- [ ] `pytest.ini` configured
- [ ] Test count unchanged (or improved if duplicates removed)
- [ ] All previously passing tests still pass
- [ ] Test discovery works correctly

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
- **Before Phase 2:** ~165 tests collected (26 oauth + 139 focused)
- **After Phase 2:** ~140-150 tests (excluding ~10 archived increment tests from collection)
- **Passing tests:** Should remain the same or increase (if duplicates removed)

### Performance Improvements
- **Unit test suite:** < 5 seconds (fast, isolated)
- **Integration test suite:** 10-30 seconds (database, HTTP)
- **Clear separation:** Easy to run unit tests during development

### Maintainability Improvements
- Clear test organization by type (unit vs integration)
- Clear ownership by module (core vs focused vs mcp)
- No confusing increment-specific test files
- No junk files cluttering the test directory
- Single source of truth for fixtures

---

## Success Criteria

✅ Test directory follows pytest best practices (unit/integration split)
✅ All production tests in appropriate directories
✅ Increment tests archived (not deleted, preserved for reference)
✅ All junk files removed (`.bak`, `.sh`, empty directories)
✅ Single consolidated `tests/conftest.py`
✅ `pytest.ini` configured for proper test discovery
✅ All previously passing tests still pass
✅ Test count documented and justified
✅ Git commit with detailed message

---

## Notes

- **Why archive instead of delete increment tests?** They document development history and may contain useful test patterns. Archiving preserves them without cluttering active test runs.
- **Why separate unit/integration?** Fast unit tests can run on every file save. Slower integration tests run in CI or before commits.
- **Why delete shell scripts?** They don't integrate with pytest, don't show up in coverage reports, and duplicate testing that should be in pytest.
- **Test count may decrease:** Some increment tests may be duplicates. This is OK and expected.

---

## Risk Assessment

**Risk Level:** Low

**Why Low Risk:**
- Only moving/renaming test files, no production code changes
- Git tracks all moves, easy to rollback
- Test baseline captured before changes
- Archived tests preserved, not deleted
- Can validate immediately after each step

**Potential Issues:**
1. Import path changes may break some tests → Fix imports during migration
2. Fixture dependencies may break → Test after conftest merge, fix as needed
3. Test discovery issues → pytest.ini configuration handles this

---

## Time Estimate Breakdown

- Step 1 (Baseline): 5 minutes
- Step 2 (Create structure): 2 minutes
- Steps 3-9 (Move files): 15 minutes
- Step 10 (Conftest merge): 10 minutes
- Step 11-13 (Cleanup): 5 minutes
- Validation: 10-15 minutes
- **Total:** 45-60 minutes
