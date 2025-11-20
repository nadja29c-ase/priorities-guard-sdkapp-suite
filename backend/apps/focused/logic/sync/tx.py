"""
Transaction management utilities for sync operations.

Provides reusable transaction context manager that handles both
production (new transaction) and test environments (nested transaction/savepoint).
"""

import logging
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@asynccontextmanager
async def transaction_scope(session: AsyncSession):
    """
    Smart transaction context manager.

    - If no transaction active: starts new transaction with session.begin()
    - If transaction already active: uses nested transaction (savepoint) with session.begin_nested()

    This allows production code to use explicit transaction boundaries
    while still working correctly in test environments where the test
    fixture provides a session with an active transaction.
    """
    if session.in_transaction():
        # Already in transaction (test environment or nested call)
        # Use savepoint for nested transaction
        async with session.begin_nested():
            yield
    else:
        # Not in transaction (production environment)
        # Start new transaction
        async with session.begin():
            yield
