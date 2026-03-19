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


# ============================================================================
# Weekly Report Normalization Helpers (Increment 77)
# ============================================================================

def normalize_priority_report(p: dict) -> dict:
    """
    Normalize priority report fields from backend snake_case to spec camelCase.

    Used by get_priority_events and render_weekly_report for weekly report data.

    Args:
        p: Priority report dict from backend

    Returns:
        Normalized priority dict
    """
    result = {
        "id": p.get("id"),
        "name": p.get("name"),
        "type": p.get("type"),
        "calendarKeyword": p.get("calendar_keyword"),
        "actualHours": p.get("actual_hours"),
        "eventCount": p.get("event_count"),
    }

    # Deadline-specific fields
    if p.get("type") == "deadline":
        result["deadlineDate"] = p.get("deadline_date")
        result["daysRemaining"] = p.get("days_remaining")
        result["deliverablesCompleted"] = p.get("deliverables_completed")
        result["deliverablesTotal"] = p.get("deliverables_total")
        # pacingStatus intentionally excluded - LLM should not use computed status

    # Flexible-specific fields
    elif p.get("type") == "flexible":
        result["targetHours"] = p.get("target_hours")
        # flexStatus intentionally excluded - LLM should not use computed status
        # Aggregates are placeholders (always 0/null until persistence ships)
        result["streakCount"] = p.get("streak_count", 0)
        result["totalHoursInvested"] = p.get("total_hours_invested", 0.0)

    # Previous week comparison (always null until persistence ships)
    result["previousWeek"] = None

    return result


def normalize_time_allocation(ta: dict) -> dict:
    """
    Normalize time allocation fields from backend snake_case to spec camelCase.

    Used by get_priority_events and render_weekly_report.
    """
    keywords = ta.get("keywords", {})
    return {
        "totalTrackedHours": ta.get("total_tracked_hours"),
        "keywords": {
            "P1": {
                "hours": keywords.get("P1", {}).get("hours", 0.0),
                "eventCount": keywords.get("P1", {}).get("event_count", 0),
            },
            "P2": {
                "hours": keywords.get("P2", {}).get("hours", 0.0),
                "eventCount": keywords.get("P2", {}).get("event_count", 0),
            },
            "P3": {
                "hours": keywords.get("P3", {}).get("hours", 0.0),
                "eventCount": keywords.get("P3", {}).get("event_count", 0),
            },
        },
        "otherHours": ta.get("other_hours", 0.0),
    }


def normalize_event(e: dict) -> dict:
    """
    Normalize event fields for LLM semantic grouping.

    Used by get_priority_events and render_weekly_report.
    """
    return {
        "title": e.get("title", ""),
        "description": e.get("description", ""),
        "start": e.get("start"),
        "end": e.get("end"),
        "matchedKeywords": e.get("matched_keywords", []),
    }
