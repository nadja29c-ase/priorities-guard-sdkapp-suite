# Alembic Migrations Operations Guide

## The Golden Rule

> **Before creating ANY migration, always:**
> ```bash
> git pull origin main
> alembic heads  # Must return exactly 1 head
> ```

Violations cause branch conflicts that block production deploys.

---

## ⚠️ STOP — Adding a new PG-owned state table? Read this first.

**A new table that holds PG user state requires a one-line change in
`backend/apps/priority_guardian/routers/reconcile_router.py`. Forgetting it silently gives
one user another user's data. There is no error, no log, and no test that catches it.**

### Why

`_reconcile_user_by_subject()` decides whether a `CoreUser` is a "fresh shell" — an empty
throwaway row safe to remap onto the canonical user (case C1) — or a real user that must not be
touched (case C2). It decides by checking whether the row has **any state**, and today "any
state" means exactly two things:

```python
has_google_connection  # active, non-revoked CoreConnection of type 'google'
has_priorities         # any PgPriority row, any status

if not has_google_connection and not has_priorities:
    return (subject_user_id, "C1")   # remap — assumed empty
else:
    return (jwt_user_id, "C2")       # refuse — has state
```

Add `pg_reflections` (say) and don't extend the check. A user who has reflections but no
priorities and no Google connection is now classified as a **fresh shell**. Reconciliation
returns a different `user_id`, and every subsequent tool call in that session reads and writes
**another user's data**. Their own rows are orphaned.

C1 is the *success* path, so nothing raises and nothing warns. This is the worst failure mode
in the suite: silent, cross-user, and invisible in logs.

### What to do

When a migration adds a table whose rows belong to a PG user:

1. Open `backend/apps/priority_guardian/routers/reconcile_router.py`
2. In `_reconcile_user_by_subject()`, add an `exists()` check for the new table alongside
   `has_priorities`
3. Include it in the `if not ... and not ...` fresh-shell condition
4. Add a test asserting a user with **only** a row in the new table is classified **C2**, not C1

### When it does NOT apply

- Tables not keyed to `core_users.id`
- Tables owned by another app (MindSort, Focused) — they have no reconciliation path
- Pure lookup, config, or reference tables with no user rows
- Audit tables that must survive deletion (e.g. `core_tool_audit_log`)

### Background

This check exists only on the **ChatGPT** path. Claude exposes no per-user identifier, so
`priority_guardian_claude` has no reconciliation step and no fresh-shell check. See
`doc/ADR_007_user_identity_and_lifecycle.md` §3 for the full A/B/C1/C2/X contract.

---

## Creating a Migration

```bash
# 1. Sync with main
git pull origin main

# 2. Verify single head
alembic heads | wc -l | grep -q "^1$" && echo "OK" || echo "STOP: Multiple heads"

# 3. Create migration
alembic revision --autogenerate -m "description_of_change"

# 4. Review generated file - autogenerate is not perfect
# 5. Test locally
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

## Before Pushing

```bash
# Verify still single head (in case you created multiple migrations)
alembic heads
```

## Before Deploying

The Render pre-deploy command enforces this automatically:

```bash
alembic heads | wc -l | grep -q "^1$" || exit 1 && alembic upgrade head
```

If deploy fails with "Multiple Alembic heads detected", see **Fixing Multiple Heads** below.

## Fixing Multiple Heads

### Scenario A: Neither branch is deployed to production

Merge the heads:
```bash
alembic merge heads -m "merge_branch_a_and_branch_b"
alembic heads  # Should now be 1
```

### Scenario B: One branch is deployed, one isn't (common)

Query production to find current version:
```bash
# Via Render MCP or psql
SELECT version_num FROM alembic_version;
```

Rebase the undeployed migration to depend on the deployed one:
```python
# In the undeployed migration file, change:
down_revision = "old_parent"
# To:
down_revision = "deployed_version"  # The one in production
```

Delete any merge migration if you created one:
```bash
rm backend/alembic/versions/*_merge_*.py
alembic heads  # Verify single head
```

### Scenario C: Both branches deployed (rare, messy)

This shouldn't happen if pre-deploy checks are in place. Manual DB intervention required.

## Defense in Depth

1. **Pre-deploy command** — Render rejects deploys with multiple heads
2. **Unique index on alembic_version** — DB rejects multiple version rows
3. **This workflow** — Prevents branches from being created in the first place

## Common Mistakes

| Mistake | Consequence | Prevention |
|---------|-------------|------------|
| Create migration without `git pull` | Branch conflict | Always pull first |
| Create migration from feature branch | Branch conflict | Create from main only |
| Push without checking `alembic heads` | Blocked deploy | Check before push |
| Force-merge without checking production state | Migration skipped or fails | Query production first |

## Migration File Best Practices

1. **Self-contained** — Never import application code; use inline SQL/operations
2. **Idempotent checks** — Use `IF NOT EXISTS` for safety where supported
3. **Backfills** — Handle NULL gracefully, batch large updates
4. **Reversible** — Always implement `downgrade()` properly
5. **Tested** — Run upgrade → downgrade → upgrade locally before pushing
