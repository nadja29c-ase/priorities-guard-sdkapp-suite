"""
Event sync package for Priority Guardian (Increment 6B/6D).

Public API exports:
- sync_calendar_events: Main orchestrator function
- transaction_scope: Transaction helper for test environments
"""

from backend.apps.focused.logic.sync.orchestrator import sync_calendar_events
from backend.apps.focused.logic.sync.tx import transaction_scope

__all__ = [
    "sync_calendar_events",
    "transaction_scope",
]
