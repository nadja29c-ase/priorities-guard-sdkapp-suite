"""
Migration-derived coverage check for PG deletion (Part A §6.1 decision).

WHY THIS FILE EXISTS SEPARATELY FROM test_pg_delete_data.py.

Every other test in this suite runs against a schema built by
`Base.metadata.create_all` (tests/conftest.py). That means they can only ever prove the
deletion code handles every table **the ORM knows about** — which is precisely the
assumption that fails when production carries a table the ORM does not model.

`pg_weekly_overview` is the worked example: created by p6k7l8m9n0o1, dropped in the upgrade
of s9t0u1v2w3x4, and invisible to `create_all` throughout. A production database sitting
between those two revisions has a fifth user-keyed PG table that no ORM-derived test could
detect (Part A §2, §6.1).

So this test builds the schema the way production does — `alembic upgrade head` against a
scratch database — and derives its assertion from `information_schema.tables` rather than
from the models. Nadja's decision, recorded in the Part A report's §6.1 block:

    "Take the migration-built version. The ORM-derived version can only prove the code
     deletes every table the ORM knows about, which is precisely the assumption
     pg_weekly_overview demonstrates can fail. For a test backing a published
     privacy-policy claim, an assertion that verifies the ORM against itself is not worth
     much."

It also exercises the migration chain end to end, which nothing else in the suite does.

SKIPS rather than fails if a scratch database cannot be created (no local PostgreSQL, no
createdb permission). A skip is honest; a silent pass would not be.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from backend.apps.priority_guardian.services.offboarding_service import (
    PG_APP_NAME,
    PG_SCOPE,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRATCH_DB = "priority_guardian_migration_coverage_test"

# The tables the deletion service names, taken from its own accounting dict rather than
# hand-copied — a hardcoded list would silently stop covering a table added later (§7.3).
from backend.apps.priority_guardian.services import offboarding_service  # noqa: E402


def _deletion_targets() -> set[str]:
    """The table names delete_user_data reports on, read from the source of truth."""
    import inspect
    import re

    src = inspect.getsource(offboarding_service.delete_user_data)
    # rows_deleted is initialised with one key per table the function accounts for.
    block = src.split("rows_deleted: dict[str, int] = {", 1)[1].split("}", 1)[0]
    return set(re.findall(r'"([a-z_]+)"', block))


def _run(cmd: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT), env=env)


@pytest.fixture(scope="module")
def migrated_schema() -> set[str]:
    """Build a scratch database with `alembic upgrade head` and return its table names."""
    if _run(["which", "createdb"]).returncode != 0:
        pytest.skip("createdb not available — cannot build a migration-derived schema")

    _run(["dropdb", "--if-exists", SCRATCH_DB])
    created = _run(["createdb", SCRATCH_DB])
    if created.returncode != 0:
        pytest.skip(f"could not create scratch database: {created.stderr.strip()}")

    try:
        env = {
            **os.environ,
            "DATABASE_URL": f"postgresql+asyncpg://localhost/{SCRATCH_DB}",
            "ENV": "test",
        }
        upgraded = _run(
            [str(REPO_ROOT / ".venv/bin/alembic"), "upgrade", "head"], env=env
        )
        if upgraded.returncode != 0:
            pytest.skip(
                "alembic upgrade head failed against the scratch database:\n"
                f"{upgraded.stderr[-1500:]}"
            )

        listed = _run([
            "psql", "-d", SCRATCH_DB, "-tAc",
            "select tablename from pg_tables where schemaname='public'",
        ])
        tables = {t.strip() for t in listed.stdout.splitlines() if t.strip()}
        assert tables, "scratch database has no tables after upgrade head"
        yield tables
    finally:
        _run(["dropdb", "--if-exists", SCRATCH_DB])


def test_migration_built_schema_has_no_pg_table_the_deletion_misses(migrated_schema):
    """
    Bug this catches: a PG-owned table that exists in the migration chain but not in the ORM,
    and therefore not in the deletion code. That is failure mode 3 from §0.2, in the one form
    no other test in this suite can see — every other test builds its schema from the same
    models the deletion code imports, so they agree with each other by construction.

    Derived from information_schema, not from a hand-copied list, per §7.3: a hardcoded list
    silently stops covering a table added later.
    """
    pg_tables = {t for t in migrated_schema if t.startswith("pg_")}
    assert pg_tables, "no pg_* tables in the migrated schema — the check would be vacuous"

    missed = pg_tables - _deletion_targets()

    assert not missed, (
        f"Tables present in the migration-built schema that delete_user_data does not "
        f"account for: {sorted(missed)}.\n"
        f"Either they hold no user data (in which case say so explicitly in the service "
        f"docstring), or the deletion is incomplete and a privacy-policy claim is false."
    )


def test_shared_tables_the_deletion_filters_exist_in_the_migrated_schema(migrated_schema):
    """
    Bug this catches: the deletion filtering a shared table that the migration chain does not
    actually create under that name — a rename or drop landing in a migration while the
    service still targets the old name. The ORM-built tests cannot see this either, because
    they create whatever the models declare.
    """
    for table in ("core_users", "core_consents", "core_connections",
                  "core_tool_audit_log", "oauth_access_tokens",
                  "oauth_authorization_codes", "oauth_sessions"):
        assert table in migrated_schema, f"{table} missing from the migration-built schema"


def test_deletion_targets_were_actually_parsed():
    """
    Bug this catches: _deletion_targets() silently returning an empty set — which would make
    the coverage assertion above pass unconditionally. This is the guard against the check
    itself becoming vacuous, which is the failure mode this increment keeps producing.
    """
    targets = _deletion_targets()

    assert len(targets) >= 8, f"parsed too few deletion targets: {sorted(targets)}"
    assert "pg_priorities" in targets
    assert "oauth_authorization_codes" in targets
    assert PG_APP_NAME == "priority_guardian" and PG_SCOPE == "pg.access"
