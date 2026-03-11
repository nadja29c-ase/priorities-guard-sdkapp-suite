"""
Priority normalization helpers.

Extracted to avoid circular imports between get_priorities and widget_tools.
"""


def normalize_priority(p: dict, calendar_hours: dict | None = None) -> dict:
    """
    Normalize priority fields from backend snake_case to spec camelCase.

    Backend returns: calendar_keyword, weekly_hour_target, checkpoint_date, etc.
    Spec expects: calendarKeyword, weeklyHourTarget, checkpointDate, etc.

    Args:
        p: Priority dict from backend
        calendar_hours: Optional dict mapping keyword (P1/P2/P3) to hours

    Returns:
        Normalized priority dict with weeklyHourActual populated if available
    """
    # Normalize deliverables (already camelCase from backend, but ensure consistency)
    deliverables = p.get("deliverables", [])
    normalized_deliverables = [
        {
            "id": d.get("id"),
            "name": d.get("name"),
            "done": d.get("done", False),
        }
        for d in deliverables
    ]

    # Normalize goals (Inc D)
    goals = p.get("goals", [])
    normalized_goals = [
        {
            "id": g.get("id"),
            "text": g.get("text"),
            "achieved": g.get("achieved", False),
        }
        for g in goals
    ]

    # Compute weeklyHourActual from calendar data if available
    weekly_hour_actual = None
    if calendar_hours:
        keyword = p.get("calendar_keyword")
        if keyword and keyword in calendar_hours:
            weekly_hour_actual = calendar_hours[keyword]

    result = {
        "id": p.get("id"),
        "name": p.get("name"),
        "type": p.get("type"),
        "calendarKeyword": p.get("calendar_keyword"),
        "status": p.get("status"),
        "deadline": p.get("deadline"),
        "weeklyHourTarget": p.get("weekly_hour_target"),
        "weeklyHourActual": weekly_hour_actual,
        "checkpointDate": p.get("checkpoint_date"),
        "deliverables": normalized_deliverables,
        "goals": normalized_goals,
        # Include all aggregates for all priority types (Inc 08)
        "streakCount": p.get("streak_count", 0),
        "totalHoursInvested": p.get("total_hours_invested", 0.0),
        "avgTargetAchievement": p.get("avg_target_achievement"),
    }

    return result


# Backwards compatibility alias
_normalize_priority = normalize_priority
