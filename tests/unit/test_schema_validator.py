"""
Unit tests for schema validator.

Tests validation logic with mocked database responses.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.core.schema_validator import (
    validate_schema,
    _validate_alembic_version,
    _validate_table_constraints,
    _validate_indexes,
    PG_PRIORITIES_CHECK_CONSTRAINTS,
    PG_SNAPSHOTS_CHECK_CONSTRAINTS,
    PG_SNAPSHOTS_UNIQUE_CONSTRAINTS,
    PG_PRIORITIES_INDEXES,
)


class MockAsyncContextManager:
    """Mock async context manager for session.begin()."""

    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


def make_mock_session(constraint_rows=None, index_rows=None, alembic_rows=None):
    """Create a mock session with configurable query results."""
    session = MagicMock()

    async def mock_execute(query, params=None):
        result = MagicMock()
        query_str = str(query) if hasattr(query, 'text') else str(query)

        if "alembic_version" in query_str:
            result.fetchall.return_value = alembic_rows or []
        elif "pg_constraint" in query_str:
            result.fetchall.return_value = constraint_rows or []
        elif "pg_indexes" in query_str:
            result.fetchall.return_value = index_rows or []
        elif "SET LOCAL" in query_str:
            result.fetchall.return_value = []
        else:
            result.fetchall.return_value = []

        return result

    session.execute = mock_execute

    # Mock begin() to return an async context manager
    session.begin.return_value = MockAsyncContextManager()

    return session


def build_constraint_rows():
    """Build mock constraint rows matching expected schema."""
    rows = []

    # pg_priorities CHECK constraints
    for name, fragments in PG_PRIORITIES_CHECK_CONSTRAINTS:
        if fragments:
            # Build a definition containing all fragments
            definition = f"CHECK (({' AND '.join(fragments)}))"
        else:
            definition = f"CHECK ((complex expression for {name}))"
        rows.append((name, definition, "c"))

    # pg_weekly_snapshots CHECK constraints
    for name, fragments in PG_SNAPSHOTS_CHECK_CONSTRAINTS:
        if fragments:
            definition = f"CHECK (({' AND '.join(fragments)}))"
        else:
            definition = f"CHECK ((complex expression for {name}))"
        rows.append((name, definition, "c"))

    # pg_weekly_snapshots UNIQUE constraints
    for name, fragments in PG_SNAPSHOTS_UNIQUE_CONSTRAINTS:
        if fragments:
            definition = f"UNIQUE ({', '.join(fragments)})"
        else:
            definition = f"UNIQUE (columns)"
        rows.append((name, definition, "u"))

    return rows


def build_index_rows():
    """Build mock index rows matching expected schema."""
    rows = []
    for name, fragments in PG_PRIORITIES_INDEXES:
        if fragments:
            indexdef = f"CREATE UNIQUE INDEX {name} ON pg_priorities (user_id, calendar_keyword) WHERE status = 'active'"
        else:
            indexdef = f"CREATE INDEX {name} ON pg_priorities (columns)"
        rows.append((name, indexdef))
    return rows


class TestValidateSchema:
    """Tests for the main validate_schema function."""

    @pytest.mark.asyncio
    async def test_validate_schema_passes_with_all_constraints(self):
        """Validation passes when all expected constraints exist with correct definitions."""
        session = make_mock_session(
            constraint_rows=build_constraint_rows(),
            index_rows=build_index_rows(),
            alembic_rows=[("abc123def",)],
        )

        # Should not raise
        await validate_schema(session)

    @pytest.mark.asyncio
    async def test_validate_schema_raises_on_missing_constraint(self):
        """Validation fails when a constraint is missing."""
        # Remove one constraint from the list
        constraints = build_constraint_rows()
        constraints = [c for c in constraints if c[0] != "ck_pg_priorities_keyword"]

        session = make_mock_session(
            constraint_rows=constraints,
            index_rows=build_index_rows(),
            alembic_rows=[("abc123def",)],
        )

        with pytest.raises(RuntimeError) as exc_info:
            await validate_schema(session)

        assert "ck_pg_priorities_keyword" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validate_schema_raises_on_wrong_constraint_definition(self):
        """Validation fails when constraint exists but has wrong definition."""
        constraints = build_constraint_rows()
        # Replace one constraint with wrong definition (missing 'p1' fragment)
        constraints = [
            (name, defn, ctype) if name != "ck_pg_priorities_keyword"
            else (name, "CHECK ((calendar_keyword = 'wrong'))", ctype)
            for name, defn, ctype in constraints
        ]

        session = make_mock_session(
            constraint_rows=constraints,
            index_rows=build_index_rows(),
            alembic_rows=[("abc123def",)],
        )

        with pytest.raises(RuntimeError) as exc_info:
            await validate_schema(session)

        assert "ck_pg_priorities_keyword" in str(exc_info.value)
        assert "missing expected fragments" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validate_schema_raises_on_missing_index(self):
        """Validation fails when expected index is missing."""
        session = make_mock_session(
            constraint_rows=build_constraint_rows(),
            index_rows=[],  # No indexes
            alembic_rows=[("abc123def",)],
        )

        with pytest.raises(RuntimeError) as exc_info:
            await validate_schema(session)

        assert "idx_pg_priorities_user_keyword_active" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validate_schema_raises_on_wrong_index_predicate(self):
        """Validation fails when index exists but has wrong predicate."""
        # Index without 'active' in the WHERE clause
        wrong_indexes = [
            ("idx_pg_priorities_user_keyword_active",
             "CREATE UNIQUE INDEX idx_pg_priorities_user_keyword_active ON pg_priorities (user_id, calendar_keyword) WHERE status = 'retired'")
        ]

        session = make_mock_session(
            constraint_rows=build_constraint_rows(),
            index_rows=wrong_indexes,
            alembic_rows=[("abc123def",)],
        )

        with pytest.raises(RuntimeError) as exc_info:
            await validate_schema(session)

        assert "idx_pg_priorities_user_keyword_active" in str(exc_info.value)
        assert "missing expected fragments" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validate_schema_raises_on_multiple_alembic_heads(self):
        """Validation fails when alembic_version has multiple rows."""
        session = make_mock_session(
            constraint_rows=build_constraint_rows(),
            index_rows=build_index_rows(),
            alembic_rows=[("head1",), ("head2",)],  # Multiple heads
        )

        with pytest.raises(RuntimeError) as exc_info:
            await validate_schema(session)

        assert "multiple heads" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_validate_schema_raises_on_empty_alembic_revision(self):
        """Validation fails when alembic version_num is empty."""
        session = make_mock_session(
            constraint_rows=build_constraint_rows(),
            index_rows=build_index_rows(),
            alembic_rows=[("",)],  # Empty revision
        )

        with pytest.raises(RuntimeError) as exc_info:
            await validate_schema(session)

        assert "empty version_num" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validate_schema_raises_on_no_alembic_rows(self):
        """Validation fails when alembic_version has no rows."""
        session = make_mock_session(
            constraint_rows=build_constraint_rows(),
            index_rows=build_index_rows(),
            alembic_rows=[],  # No rows
        )

        with pytest.raises(RuntimeError) as exc_info:
            await validate_schema(session)

        assert "no rows" in str(exc_info.value)


class TestValidateAlembicVersion:
    """Tests for alembic version validation."""

    @pytest.mark.asyncio
    async def test_returns_none_on_valid_single_revision(self):
        """Returns None when exactly one valid revision exists."""
        session = AsyncMock()
        result = MagicMock()
        result.fetchall.return_value = [("abc123def456",)]
        session.execute = AsyncMock(return_value=result)

        error = await _validate_alembic_version(session)
        assert error is None

    @pytest.mark.asyncio
    async def test_returns_error_on_multiple_rows(self):
        """Returns error message when multiple rows exist."""
        session = AsyncMock()
        result = MagicMock()
        result.fetchall.return_value = [("head1",), ("head2",)]
        session.execute = AsyncMock(return_value=result)

        error = await _validate_alembic_version(session)
        assert error is not None
        assert "multiple heads" in error

    @pytest.mark.asyncio
    async def test_returns_error_on_empty_revision(self):
        """Returns error message when revision is empty."""
        session = AsyncMock()
        result = MagicMock()
        result.fetchall.return_value = [("",)]
        session.execute = AsyncMock(return_value=result)

        error = await _validate_alembic_version(session)
        assert error is not None
        assert "empty" in error

    @pytest.mark.asyncio
    async def test_returns_error_on_whitespace_only_revision(self):
        """Returns error message when revision is whitespace only."""
        session = AsyncMock()
        result = MagicMock()
        result.fetchall.return_value = [("   ",)]
        session.execute = AsyncMock(return_value=result)

        error = await _validate_alembic_version(session)
        assert error is not None
        assert "empty" in error
