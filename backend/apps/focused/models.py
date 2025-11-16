"""
Database models for the Focused SDK app.

System-level entities (users, connections, etc.) live in backend.core.models.
This module is only for Focused-specific tables.

Currently:
- FocusedUserKeyword: custom focus keywords added by a user

System default keywords (e.g. "focus", "deep work") are defined in
backend.apps.focused.config and are NOT stored here.
"""

from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.models import Base


class FocusedUserKeyword(Base):
    """
    Custom focus keywords added by the user.

    Example:
        user_id = "abc123"
        keyword = "writing sprint"
    """

    __tablename__ = "focused_user_keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to core_users.user_id
    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("core_users.user_id", ondelete="CASCADE"),
        nullable=False,
    )

    # The actual keyword text
    keyword: Mapped[str] = mapped_column(String, nullable=False)

    # Optional: simple audit timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<FocusedUserKeyword user_id={self.user_id!r}, keyword={self.keyword!r}>"
