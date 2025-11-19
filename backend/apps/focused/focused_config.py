"""
Focused App Configuration

This module contains static, system-level configuration values
for the Focused SDK app. These values are NOT user-editable and
are not stored in the database.

Users may add custom keywords, but default system keywords
cannot be removed or overridden.
"""

from datetime import timedelta

# -----------------------------------------------------------
# DEFAULT SYSTEM KEYWORDS (NOT user-editable)
# -----------------------------------------------------------

DEFAULT_FOCUS_KEYWORDS = [
    "focus",
    "deep work",
]

# -----------------------------------------------------------
# OPTIONAL: Default scanning window limits
# These are internal defaults used only when the caller does
# not provide time_start/time_end.
# -----------------------------------------------------------

DEFAULT_SCAN_WINDOW_DAYS = 7
MAX_SCAN_WINDOW_DAYS = 30   # safety cap

# -----------------------------------------------------------
# GDPR-COMPLIANT DATA RETENTION (Increment 6C)
# -----------------------------------------------------------

# Event descriptions are deleted after 72 hours
# This is GDPR-compliant because:
# - Descriptions are only needed for short-term sync correctness
# - SHA256 hash still includes description for change detection
# - If event is re-synced, description is restored with fresh 72h window
FOCUSED_EVENTDESCR_TTL = timedelta(hours=72)

# -----------------------------------------------------------
# Helper function (not required, but clean)
# -----------------------------------------------------------

def get_default_keywords() -> list[str]:
    """
    Return a copy of the system default focus keywords.

    A copy is returned to prevent accidental modification
    of the original list.
    """
    return DEFAULT_FOCUS_KEYWORDS.copy()
