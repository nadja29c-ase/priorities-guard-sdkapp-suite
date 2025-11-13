"""
Database models for Focused app.

Tables: focused_sessions, focused_patterns, focused_preferences
"""

from sqlalchemy import String, Integer, DateTime, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from core.db import Base


class FocusedSession(Base):
    """Track individual focus sessions."""

    __tablename__ = "focused_sessions"

    # TODO: Add columns:
    # - id (primary key)
    # - user_id (foreign key)
    # - event_id (optional)
    # - start_time
    # - duration_minutes
    # - completed (boolean)
    # - created_at
    pass


class FocusedPattern(Base):
    """Store analyzed focus patterns."""

    __tablename__ = "focused_patterns"

    # TODO: Add columns:
    # - id (primary key)
    # - user_id (foreign key)
    # - pattern_type (e.g., "best_time", "optimal_duration")
    # - pattern_data (JSON)
    # - confidence_score
    # - updated_at
    pass


class FocusedPreference(Base):
    """User preferences for Focused app."""

    __tablename__ = "focused_preferences"

    # TODO: Add columns:
    # - id (primary key)
    # - user_id (foreign key, unique)
    # - keywords (JSON list)
    # - default_duration_minutes
    # - auto_activate (boolean)
    # - updated_at
    pass
