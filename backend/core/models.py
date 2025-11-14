"""
SQLAlchemy models for Priority Guardian.

Core tables for OAuth token storage.
"""

from datetime import datetime
from sqlalchemy import (
    String,
    Text,
    CheckConstraint,
    Index,
    UniqueConstraint,
    ARRAY,
    DateTime,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func, text


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


class CoreConnection(Base):
    """
    Store encrypted OAuth tokens for external service connections.

    Supports Google and Apple OAuth providers.
    """

    __tablename__ = "core_connections"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), # unique identifier for database row
        primary_key=True, 
        server_default=text("gen_random_uuid()"),
    )

    user_id: Mapped[str] = mapped_column(String(255), nullable=False) #The ChatGPT user ID (or my internal user ID later)

    provider: Mapped[str] = mapped_column(String(50), nullable=False) #OAuth provider.

    encrypted_access_token: Mapped[str] = mapped_column(Text, nullable=False) #The user’s Google access token, but encrypted with AES-256

    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True) #Google’s refresh token, encrypted.
    
    token_expires_at: Mapped[datetime] = mapped_column( #The timestamp at which the access token expires.
        DateTime(timezone=True), nullable=False
    )

    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False) #All scopes authorized by the user (f.e. calendar.readyonly)

    created_at: Mapped[datetime] = mapped_column( #The timestamp when this connection row was first created.
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column( #Whenever tokens are refreshed or updated, this timestamp updates.
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = ( #Inside a SQLAlchemy model, __table_args__ is a special class attribute that lets you define anything that applies to the whole table f.e. Unique constrainsts, Indexes, Check constraints
        UniqueConstraint("user_id", "provider", name="uq_user_provider"), # Ensures there is only one row per user per provider to prevent duplicates
        CheckConstraint("provider IN ('google', 'apple')", name="ck_provider_valid"),
        Index("ix_user_provider", "user_id", "provider"), #A database index for fast lookups
        Index("ix_token_expires", "token_expires_at"),
    )
