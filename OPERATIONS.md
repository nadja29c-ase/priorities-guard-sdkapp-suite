# Operations Notes

## PostgreSQL Version

| Environment | Version | Notes |
|-------------|---------|-------|
| Production  | 16 | Render managed PostgreSQL |
| Local tools | 16 | `brew install postgresql@16` |

When Render upgrades PostgreSQL, update local tools to match for `pg_dump` schema diffs.

## Pre-Deploy Checks

### Alembic Migration Fork Detection

Before deploying, verify there's only one migration head:

```bash
cd priority-guardian
HEADS=$(alembic heads 2>/dev/null | wc -l)
if [ "$HEADS" -gt 1 ]; then
    echo "ERROR: Alembic has multiple heads. Merge before deploying."
    alembic heads
    exit 1
fi
echo "OK: Single migration head"
```

This catches migrations created with the same `down_revision` (fork).

### Production Schema Diff

To verify production schema matches migrations:

```bash
# Dump production schema
pg_dump --schema-only "$PRODUCTION_DATABASE_URL" > /tmp/prod_schema.sql

# Compare against expected (use psql introspection queries)
psql "$PRODUCTION_DATABASE_URL" -c "\d+ pg_priorities"
```
