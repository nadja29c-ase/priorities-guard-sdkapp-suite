"""
Schema Validator — Startup check for required database constraints.

Validates that safety-critical CHECK constraints, UNIQUE constraints, and indexes
exist in the database with correct definitions. Blocks app startup if schema drift
is detected.

This catches migration issues (forks, partial applies) that would otherwise go
unnoticed until data corruption occurs.
"""

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


# =============================================================================
# Expected Constraints Configuration
# =============================================================================

# CHECK constraints on pg_priorities
# Format: (constraint_name, [definition_fragments] or None for name-only validation)
PG_PRIORITIES_CHECK_CONSTRAINTS = [
    ("ck_pg_priorities_keyword", ["calendar_keyword", "'p1'", "'p2'", "'p3'"]),
    ("ck_pg_priorities_type", ["type", "'deadline'", "'flexible'"]),
    ("ck_pg_priorities_status", ["status", "'active'", "'retired'"]),
    ("ck_pg_priorities_type_field_consistency", None),  # Complex cross-field logic
    ("ck_pg_priorities_weekly_target_positive", ["weekly_hour_target", "0"]),
    ("ck_pg_priorities_retirement_consistency", None),  # Complex cross-field logic
]

# CHECK constraints on pg_weekly_snapshots
PG_SNAPSHOTS_CHECK_CONSTRAINTS = [
    ("ck_pg_weekly_snapshots_actual_hours_non_negative", ["actual_hours", "0"]),
    ("ck_pg_weekly_snapshots_week_consistency", None),  # Date arithmetic
    ("ck_pg_weekly_snapshots_week_start_monday", None),  # extract/date_part
    ("ck_pg_weekly_snapshots_target_hours_non_negative", ["target_hours", "0"]),
    ("ck_pg_weekly_snapshots_other_hours_non_negative", ["other_hours", "0"]),
    ("ck_pg_weekly_snapshots_total_hours_non_negative", ["total_tracked_hours", "0"]),
]

# UNIQUE constraints on pg_weekly_snapshots (validated via pg_constraint, contype='u')
PG_SNAPSHOTS_UNIQUE_CONSTRAINTS = [
    ("uq_pg_weekly_snapshots_priority_week", ["priority_id", "week_start"]),
]

# Partial indexes (validated via pg_indexes, not pg_constraint)
PG_PRIORITIES_INDEXES = [
    ("idx_pg_priorities_user_keyword_active", ["status", "'active'"]),
]

# CHECK constraints on core_connections (data integrity guards)
CORE_CONNECTIONS_CHECK_CONSTRAINTS = [
    ("ck_connection_type_enum", ["connection_type", "'google'", "'apple'", "'oauth_provider'"]),
    ("ck_encrypted_access_token_conditional", None),  # Complex cross-field logic
    ("ck_encrypted_refresh_token_not_empty", ["encrypted_refresh_token"]),
    ("ck_scopes_not_empty", ["scopes"]),
]


# =============================================================================
# Validation Functions
# =============================================================================


async def validate_schema(session: AsyncSession) -> None:
    """
    Validate that required constraints and indexes exist in the database.

    Runs during application startup. If any expected constraint is missing or
    has an incorrect definition, raises RuntimeError to block startup.

    Args:
        session: AsyncSession for database queries

    Raises:
        RuntimeError: If schema validation fails (missing/invalid constraints)
    """
    errors: list[str] = []

    async with session.begin():
        # Set statement timeout to fail fast on DB issues
        await session.execute(text("SET LOCAL statement_timeout = '5s'"))

        # Log alembic revision BEFORE validation (visible even if validation fails)
        alembic_error = await _validate_alembic_version(session)
        if alembic_error:
            errors.append(alembic_error)

        # Validate pg_priorities constraints
        priorities_errors = await _validate_table_constraints(
            session,
            "pg_priorities",
            PG_PRIORITIES_CHECK_CONSTRAINTS,
            [],  # No UNIQUE constraints to check
        )
        errors.extend(priorities_errors)

        # Validate pg_priorities indexes
        index_errors = await _validate_indexes(
            session,
            "pg_priorities",
            PG_PRIORITIES_INDEXES,
        )
        errors.extend(index_errors)

        # Validate pg_weekly_snapshots constraints
        snapshots_errors = await _validate_table_constraints(
            session,
            "pg_weekly_snapshots",
            PG_SNAPSHOTS_CHECK_CONSTRAINTS,
            PG_SNAPSHOTS_UNIQUE_CONSTRAINTS,
        )
        errors.extend(snapshots_errors)

        # Validate core_connections constraints
        connections_errors = await _validate_table_constraints(
            session,
            "core_connections",
            CORE_CONNECTIONS_CHECK_CONSTRAINTS,
            [],  # No UNIQUE constraints to check
        )
        errors.extend(connections_errors)

    if errors:
        error_list = "\n  - ".join(errors)
        raise RuntimeError(
            f"Schema validation failed. Missing or invalid constraints:\n  - {error_list}"
        )

    logger.info("schema.validation.passed")


async def _validate_alembic_version(session: AsyncSession) -> str | None:
    """
    Validate alembic_version table has exactly one row with non-empty revision.

    Logs the revision as schema.alembic_revision before returning.

    Returns:
        Error message if validation fails, None if passes
    """
    result = await session.execute(text("SELECT version_num FROM alembic_version"))
    rows = result.fetchall()

    if len(rows) == 0:
        return "alembic_version: no rows (migrations never applied)"

    if len(rows) > 1:
        revisions = [row[0] for row in rows]
        return f"alembic_version: multiple heads detected ({revisions})"

    version_num = rows[0][0]
    if not version_num or not version_num.strip():
        return "alembic_version: empty version_num"

    # Log revision at INFO level for visibility
    logger.info("schema.alembic_revision", revision=version_num)
    return None


async def _validate_table_constraints(
    session: AsyncSession,
    table_name: str,
    check_constraints: list[tuple[str, list[str] | None]],
    unique_constraints: list[tuple[str, list[str] | None]],
) -> list[str]:
    """
    Validate CHECK and UNIQUE constraints exist with correct definitions.

    Args:
        session: Database session
        table_name: Table to check constraints on
        check_constraints: List of (name, fragments) for CHECK constraints
        unique_constraints: List of (name, fragments) for UNIQUE constraints

    Returns:
        List of error messages for missing/invalid constraints
    """
    errors: list[str] = []

    # Query all CHECK and UNIQUE constraints for the table
    # Note: Table name is hardcoded (not user input) so string formatting is safe
    result = await session.execute(
        text(f"""
            SELECT conname, pg_get_constraintdef(oid), contype
            FROM pg_constraint
            WHERE conrelid = 'public.{table_name}'::regclass
              AND contype IN ('c', 'u')
        """),
    )
    rows = result.fetchall()

    # Build lookup: constraint_name -> (definition, contype)
    # Note: asyncpg returns contype as bytes (b'c'), must decode to str
    constraint_map: dict[str, tuple[str, str]] = {}
    for row in rows:
        conname, condef, contype = row
        # Decode contype if it's bytes (asyncpg behavior for char type)
        if isinstance(contype, bytes):
            contype = contype.decode('ascii')
        constraint_map[conname] = (condef.lower() if condef else "", contype)

    # Validate CHECK constraints (contype='c')
    for name, fragments in check_constraints:
        if name not in constraint_map:
            errors.append(f"{table_name}: missing CHECK constraint '{name}'")
        elif constraint_map[name][1] != "c":
            errors.append(f"{table_name}: '{name}' is not a CHECK constraint")
        elif fragments is not None:
            definition = constraint_map[name][0]
            missing_frags = [f for f in fragments if f.lower() not in definition]
            if missing_frags:
                errors.append(
                    f"{table_name}: CHECK '{name}' missing expected fragments {missing_frags}"
                )

    # Validate UNIQUE constraints (contype='u')
    for name, fragments in unique_constraints:
        if name not in constraint_map:
            errors.append(f"{table_name}: missing UNIQUE constraint '{name}'")
        elif constraint_map[name][1] != "u":
            errors.append(f"{table_name}: '{name}' is not a UNIQUE constraint")
        elif fragments is not None:
            definition = constraint_map[name][0]
            missing_frags = [f for f in fragments if f.lower() not in definition]
            if missing_frags:
                errors.append(
                    f"{table_name}: UNIQUE '{name}' missing expected fragments {missing_frags}"
                )

    return errors


async def _validate_indexes(
    session: AsyncSession,
    table_name: str,
    expected_indexes: list[tuple[str, list[str] | None]],
) -> list[str]:
    """
    Validate partial indexes exist with correct definitions.

    Args:
        session: Database session
        table_name: Table to check indexes on
        expected_indexes: List of (name, indexdef_fragments)

    Returns:
        List of error messages for missing/invalid indexes
    """
    errors: list[str] = []

    # Query all indexes for the table
    # Note: Table name is hardcoded (not user input) so string formatting is safe
    result = await session.execute(
        text(f"""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = '{table_name}' AND schemaname = 'public'
        """),
    )
    rows = result.fetchall()

    # Build lookup: index_name -> indexdef
    index_map: dict[str, str] = {}
    for row in rows:
        indexname, indexdef = row
        index_map[indexname] = indexdef.lower() if indexdef else ""

    # Validate expected indexes
    for name, fragments in expected_indexes:
        if name not in index_map:
            errors.append(f"{table_name}: missing index '{name}'")
        elif fragments is not None:
            indexdef = index_map[name]
            missing_frags = [f for f in fragments if f.lower() not in indexdef]
            if missing_frags:
                errors.append(
                    f"{table_name}: index '{name}' missing expected fragments {missing_frags}"
                )

    return errors
