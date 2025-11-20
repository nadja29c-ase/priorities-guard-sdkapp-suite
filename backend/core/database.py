"""
DB ENGINE + Session Management
Async database connection and session management.

Uses SQLAlchemy 2.0 async engine with PostgreSQL.
"""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.sql import text

from backend.core.config import settings



# Create async engine that manages ALL your database connections efficiently, safely, and asynchronously
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=10, #Max simultaneous DB connections your backend keeps open
    max_overflow=20, #Allows the pool to create temporary extra connections above pool_size
    echo=False, #keeps logs clean
    pool_pre_ping=True,  # Test connections before using them (prevents stale connection errors)
)

# Create async session factory when FastAPI needs a DB session for a request
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI endpoints to get database sessions.

    Yields:
        AsyncSession: Database session
        
    get_db() gives each request a safe, isolated, auto-cleaned, auto-rollback, auto-commit database session.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit() #It means: The endpoint ran successfully; No errors occurred; DB changes should be saved
        except Exception:
            await session.rollback() #Rollback = undo everything this request did to the DB
            raise
        finally:
            await session.close()


async def test_connection() -> None:
    """
    Raise an exception if the DB connection fails.
    """
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
