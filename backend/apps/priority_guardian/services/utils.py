"""
Shared utility functions for Priority Guardian services.

This module contains helpers that need to be shared between services
to avoid circular imports.
"""

from datetime import date, timedelta


def priority_eligible_for_week(created_at: date, week_start: date) -> bool:
    """
    Check if a priority should have a snapshot for the given week.

    A priority is eligible if the week_start is on or after the first
    Monday on or after the priority's created_at date (full weeks only).

    Args:
        created_at: Date when the priority was created
        week_start: Monday of the week to check

    Returns:
        True if the priority should have a snapshot for this week
    """
    days_until_monday = (7 - created_at.weekday()) % 7
    first_valid_monday = created_at + timedelta(days=days_until_monday)
    return week_start >= first_valid_monday
