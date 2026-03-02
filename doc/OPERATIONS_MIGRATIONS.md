# Alembic Migrations Operations Guide

## The Golden Rule

> **Before creating ANY migration, always:**
> ```bash
> git pull origin main
> alembic heads  # Must return exactly 1 head
> ```

Violations cause branch conflicts that block production deploys.

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
