"""
Focused app business logic package.

Contains modular logic for:
- Webhook processing (logic/webhook/)
- Calendar sync operations (logic/sync/)
"""

# Re-export commonly used functions for convenience
from backend.apps.focused.tools.check_calendar_impl import check_calendar_impl
from backend.apps.focused.tools.watch_calendar_impl import register_calendar_webhook
from backend.apps.focused.tools.helpers.keyword_utils import (
    load_user_custom_keywords,
    matches_focus_keywords,
)

__all__ = [
    "check_calendar_impl",
    "register_calendar_webhook",
    "load_user_custom_keywords",
    "matches_focus_keywords",
]
