"""
Integration tests for schema validator.

Tests validation against the real test database built from SQLAlchemy models.
The test database includes constraints defined in db_models.py.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.schema_validator import validate_schema


class TestSchemaValidatorIntegration:
    """Integration tests for schema validator against real DB."""

    @pytest.mark.asyncio
    async def test_validate_schema_passes_on_real_db(self, async_session_with_alembic: AsyncSession):
        """
        Schema validation passes against the test database.

        The test database is built from SQLAlchemy models which define the same
        CHECK constraints, UNIQUE constraints, and indexes that migrations create.
        This proves the expected constraint list in schema_validator.py matches
        what the models define.

        Uses async_session_with_alembic fixture which creates the alembic_version
        table with a test revision (normally created by Alembic, not SQLAlchemy).
        """
        # Should not raise - all expected constraints exist
        await validate_schema(async_session_with_alembic)
