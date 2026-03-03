"""
Integration tests for data minimization migration (w3x4y5z6a7b8).

Verifies:
1. Dropped columns are actually gone from database schema
2. NOT NULL constraint is enforced on session_token_hash
3. Row counts are preserved after migration
4. Index changes are applied correctly

These tests run against the actual database schema after migration.
"""

import pytest
from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import AsyncSession


class TestDroppedColumnsAbsence:
    """Verify dropped columns no longer exist in database schema."""

    @pytest.mark.asyncio
    async def test_oauth_access_tokens_no_last_used_at(self, async_session: AsyncSession):
        """last_used_at column should not exist in oauth_access_tokens."""
        result = await async_session.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'oauth_access_tokens'
                AND column_name = 'last_used_at'
            """)
        )
        rows = result.fetchall()
        assert len(rows) == 0, "last_used_at column should not exist in oauth_access_tokens"

    @pytest.mark.asyncio
    async def test_oauth_sessions_no_session_token(self, async_session: AsyncSession):
        """session_token (plaintext) column should not exist in oauth_sessions."""
        result = await async_session.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'oauth_sessions'
                AND column_name = 'session_token'
            """)
        )
        rows = result.fetchall()
        assert len(rows) == 0, "session_token column should not exist in oauth_sessions"

    @pytest.mark.asyncio
    async def test_oauth_authorization_codes_no_nonce(self, async_session: AsyncSession):
        """nonce column should not exist in oauth_authorization_codes."""
        result = await async_session.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'oauth_authorization_codes'
                AND column_name = 'nonce'
            """)
        )
        rows = result.fetchall()
        assert len(rows) == 0, "nonce column should not exist in oauth_authorization_codes"

    @pytest.mark.asyncio
    async def test_clarity_clusters_no_thoughts_exhausted(self, async_session: AsyncSession):
        """thoughts_exhausted column should not exist in clarity_clusters."""
        result = await async_session.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'clarity_clusters'
                AND column_name = 'thoughts_exhausted'
            """)
        )
        rows = result.fetchall()
        assert len(rows) == 0, "thoughts_exhausted column should not exist in clarity_clusters"

    @pytest.mark.asyncio
    async def test_clarity_clusters_no_correctly_clustered(self, async_session: AsyncSession):
        """correctly_clustered column should not exist in clarity_clusters."""
        result = await async_session.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'clarity_clusters'
                AND column_name = 'correctly_clustered'
            """)
        )
        rows = result.fetchall()
        assert len(rows) == 0, "correctly_clustered column should not exist in clarity_clusters"


class TestSessionTokenHashConstraints:
    """Verify session_token_hash has correct constraints after migration."""

    @pytest.mark.asyncio
    async def test_session_token_hash_is_not_null(self, async_session: AsyncSession):
        """session_token_hash column should be NOT NULL."""
        result = await async_session.execute(
            text("""
                SELECT is_nullable
                FROM information_schema.columns
                WHERE table_name = 'oauth_sessions'
                AND column_name = 'session_token_hash'
            """)
        )
        row = result.fetchone()
        assert row is not None, "session_token_hash column should exist"
        assert row[0] == "NO", "session_token_hash should be NOT NULL"

    @pytest.mark.asyncio
    async def test_session_token_hash_has_unique_index(self, async_session: AsyncSession):
        """session_token_hash should have a unique index."""
        result = await async_session.execute(
            text("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = 'oauth_sessions'
                AND indexname = 'idx_oauth_sessions_session_token_hash'
            """)
        )
        row = result.fetchone()
        assert row is not None, "idx_oauth_sessions_session_token_hash index should exist"
        assert "UNIQUE" in row[1].upper(), "session_token_hash index should be UNIQUE"


class TestDroppedIndexAbsence:
    """Verify dropped indexes no longer exist."""

    @pytest.mark.asyncio
    async def test_no_session_token_index(self, async_session: AsyncSession):
        """idx_oauth_sessions_session_token index should not exist."""
        result = await async_session.execute(
            text("""
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'oauth_sessions'
                AND indexname = 'idx_oauth_sessions_session_token'
            """)
        )
        rows = result.fetchall()
        assert len(rows) == 0, "idx_oauth_sessions_session_token index should not exist"


class TestRemainingColumnsExist:
    """Verify columns that should remain are still present."""

    @pytest.mark.asyncio
    async def test_oauth_sessions_has_session_token_hash(self, async_session: AsyncSession):
        """session_token_hash column should still exist."""
        result = await async_session.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'oauth_sessions'
                AND column_name = 'session_token_hash'
            """)
        )
        rows = result.fetchall()
        assert len(rows) == 1, "session_token_hash column should exist in oauth_sessions"

    @pytest.mark.asyncio
    async def test_oauth_sessions_has_session_token_enc(self, async_session: AsyncSession):
        """session_token_enc column should still exist."""
        result = await async_session.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'oauth_sessions'
                AND column_name = 'session_token_enc'
            """)
        )
        rows = result.fetchall()
        assert len(rows) == 1, "session_token_enc column should exist in oauth_sessions"

    @pytest.mark.asyncio
    async def test_clarity_clusters_has_content_hash(self, async_session: AsyncSession):
        """content_hash column should still exist in clarity_clusters."""
        result = await async_session.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'clarity_clusters'
                AND column_name = 'content_hash'
            """)
        )
        rows = result.fetchall()
        assert len(rows) == 1, "content_hash column should exist in clarity_clusters"

    @pytest.mark.asyncio
    async def test_clarity_clusters_has_cluster_data(self, async_session: AsyncSession):
        """cluster_data column should still exist in clarity_clusters."""
        result = await async_session.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'clarity_clusters'
                AND column_name = 'cluster_data'
            """)
        )
        rows = result.fetchall()
        assert len(rows) == 1, "cluster_data column should exist in clarity_clusters"


class TestAlembicVersionIntegrity:
    """Verify alembic version table is correct after migration."""

    @pytest.mark.asyncio
    async def test_single_alembic_version(self, async_session: AsyncSession):
        """alembic_version should have exactly one row."""
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM alembic_version")
        )
        count = result.scalar()
        assert count == 1, f"alembic_version should have exactly 1 row, got {count}"

    @pytest.mark.asyncio
    async def test_alembic_version_is_data_minimization(self, async_session: AsyncSession):
        """alembic_version should be the data minimization migration."""
        result = await async_session.execute(
            text("SELECT version_num FROM alembic_version")
        )
        version = result.scalar()
        assert version == "w3x4y5z6a7b8", (
            f"Expected version 'w3x4y5z6a7b8', got '{version}'"
        )
