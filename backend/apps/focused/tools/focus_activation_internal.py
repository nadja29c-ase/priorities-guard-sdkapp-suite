"""
Internal Focus Mode Activation Utilities (Increment 20).

Provides internal functions for focus mode activation that can be called
directly by Celery tasks, bypassing MCP/HTTP overhead.

Key difference from run_focus_mode_impl:
- run_focus_mode_impl: Full tool logic with validation, session creation, user confirmation
- run_focus_mode_internal: Minimal utility that just generates shortcut URL

The Celery task handles validation separately; this function is a pure utility.
"""

from typing import TypedDict
from urllib.parse import quote

from backend.apps.focused.db_models import FocusedFocusSession


class FocusActivationResult(TypedDict):
    """Result from run_focus_mode_internal()."""
    shortcut_url: str
    focus_name: str
    end_time: str | None


# Shortcut URL template
ACTIVATE_SHORTCUT_URL = (
    "shortcuts://run-shortcut?name=Activate%20Focus%20Mode&input=text&text={focus_name}"
)

# Default focus name if event summary is empty
DEFAULT_FOCUS_NAME = "Focus Session"


def extract_focus_name(event_summary: str | None) -> str:
    """
    Extract a focus name from the event summary.

    The focus name is used as input to the iOS Shortcut.
    If the event summary is empty or None, returns the default.

    Args:
        event_summary: Calendar event summary/title

    Returns:
        Focus name for the shortcut
    """
    if not event_summary or not event_summary.strip():
        return DEFAULT_FOCUS_NAME

    # Use the event summary as the focus name
    # Truncate to 100 chars to keep URL reasonable
    return event_summary.strip()[:100]


def generate_shortcut_url(focus_name: str) -> str:
    """
    Generate the iOS Shortcut URL for activating Focus Mode.

    Args:
        focus_name: Name to pass to the shortcut

    Returns:
        Full shortcut:// URL for activation
    """
    return ACTIVATE_SHORTCUT_URL.format(focus_name=quote(focus_name))


def run_focus_mode_internal(session: FocusedFocusSession) -> FocusActivationResult:
    """
    Generate shortcut URL for focus activation.

    This is a minimal utility function that generates the shortcut URL
    from a focus session. It does NOT:
    - Validate user confirmation
    - Check for existing active sessions
    - Create or modify session records
    - Schedule auto-deactivation

    Those responsibilities belong to the Celery task that calls this function.

    Args:
        session: Focus session to generate URL for

    Returns:
        Dictionary with:
        - shortcut_url: URL for the iOS Shortcut
        - focus_name: Name passed to the shortcut
        - end_time: Session end time (ISO 8601 string or None)
    """
    focus_name = extract_focus_name(session.event_summary)
    shortcut_url = generate_shortcut_url(focus_name)

    return {
        "shortcut_url": shortcut_url,
        "focus_name": focus_name,
        "end_time": session.end_time.isoformat() if session.end_time else None,
    }
