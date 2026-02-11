"""
Priority Guardian App Configuration.

This module contains static, system-level configuration values
for the Priority Guardian SDK app. These values are NOT user-editable
and are not stored in the database.

Increment 01: Foundation only - no business logic constants yet.
"""

# -----------------------------------------------------------
# APP IDENTITY
# -----------------------------------------------------------

PG_APP_NAME = "priority-guardian"
PG_APP_DISPLAY_NAME = "Priority Guardian"

# -----------------------------------------------------------
# GOOGLE OAUTH SCOPES
# -----------------------------------------------------------

# PG requests two scopes (space-separated):
# - events.readonly: Read calendar events for time tracking
# - settings.readonly: Read user timezone for accurate week boundaries
GOOGLE_CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events.readonly https://www.googleapis.com/auth/calendar.settings.readonly"

# -----------------------------------------------------------
# CALENDAR KEYWORDS (Increment 05)
# -----------------------------------------------------------

# Keywords for matching calendar events to priorities
# Order matters: P1 has highest priority for bar segment allocation
PG_KEYWORDS = ["P1", "P2", "P3"]
