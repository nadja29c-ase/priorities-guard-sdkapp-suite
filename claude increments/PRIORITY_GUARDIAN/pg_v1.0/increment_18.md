# Phase 2 Onboarding Flow: Calendar Connection & First Value

## Prerequisites
- User has completed Phase 1 (1-3 priorities set up)
- ONBOARDING_COMPLETION_GUIDANCE delivered (dashboard intro, calendar bridge)
- NO deliverable education yet — that happens in this phase after first snapshot

## Flow

### Step 1 — Calendar Bridge (already delivered)

Handled by ONBOARDING_COMPLETION_GUIDANCE at end of Phase 1:
- Why: PG needs to see how you spend time
- Where: full dashboard
- No how, no OAuth details, no scope explanation

User opens full dashboard, connects via UI. LLM waits.

---

### Step 2 — Keyword Education (after connection, before any report)

**Trigger:** User signals "connected" / "done" / "what's next"

**LLM calls:** `onboarding_calendar_setup` with `phase: "keyword_education"`

Tool verifies connection and returns priorities with keywords. If not connected → error guidance sends user back to dashboard.

**LLM educates on keywords (driven by assistant_guidance):**
- Explain the mechanism: add the keyword to your calendar event title — PG reads titles and counts the hours automatically
- Use their real priority names and keywords as examples:
  "If 'Client Acquisition' is P1, name your event 'P1: Client call with X'"
- Brief, concrete, tied to their setup

**Then the critical behavioral prompt:**
- "Go add P1/P2/P3 to 2-3 event titles from this week in your Google Calendar right now. Come back and I'll generate your first snapshot so you can see how it works."
- Creates: action, micro-commitment, immediate loop closure

LLM waits for user to return.

---

### Step 3 — First Real Snapshot (after user adds keywords to event titles)

**Trigger:** User signals "done" / comes back

**LLM calls:** `onboarding_calendar_setup` with `phase: "first_snapshot"`

Tool calls the same backend as `get_weekly_report` (current week, live computation). Returns snapshot data with onboarding-specific guidance.

**This report:**
- Has real data (user just added keywords to event titles)
- Has untagged data (rest of the week)
- The contrast is visible — that's the point

**LLM frames the results (driven by assistant_guidance):**
- Show how time splits across priorities: "P1: 4h this week, P2: 2h"
- Acknowledge events without keywords: "You still have ~Xh in events without keywords — that's normal. As you add keywords to more event titles, tracking becomes precise."
- Semantic grouping shows other events with potential overlap: "These other hours include [event names] — some might belong to your priorities too"

**This is the "aha" moment.** Not before.

**This report is NOT stored.** Current week = live calendar computation only. No persistence.

---

### Step 3b — Deliverable Education (part of `first_snapshot` phase guidance)

**Immediately after showing the snapshot.** Driven by `deliverable_education` field in `first_snapshot` assistant_guidance.

This is the ONLY moment deliverables are introduced. The user has just seen their real data — hours split across priorities. Now "outcome-based tracking" is concrete, not abstract.

For deadline priorities:
- Show the contrast between tracking with and without deliverables:
  - Without: "P1: 12h this week — client calls, proposal writing, research." Hours and semantic grouping, but no sense of whether you're on track to deliver.
  - With: "P1: 4/10 deliverables done, 20 days to deadline." Now you know exactly where you stand.
- "You can add E2E deliverables to your deadline priorities — the big chunks of work that need to happen to ship. Not tasks, just the major pieces from start to finish. Add them in the dashboard card anytime."

For flexible priorities:
- "Your monthly goal already anchors what the hours should produce."

**No coaching. No prompting to add them now. No multi-step.**
If user asks → use the dashboard. If not → move on.

---

### Step 4 — Weekly Reflection Setup

**Trigger:** After user absorbs the snapshot and deliverable education.

**LLM calls:** `onboarding_calendar_setup` with `phase: "reflection_setup"`

Tool returns purely guidance-driven response (no backend data call needed).

**LLM introduces two ways to track progress (driven by assistant_guidance):**

1. **Dashboard (always available):** The progress bar in the dashboard shows real-time hours against each priority — a quick glance anytime to see if the week is on track.

2. **Weekly report (snapshot):** Every week PG saves a snapshot of time allocation. Over time this builds a history — week-over-week comparison that reveals patterns: "Am I consistently under-investing in P2?" or "Client work keeps eating into my P1 time." The weekly report is where you spot these patterns and decide what to adjust.

**LLM suggests the recurring event:**
- "Create a recurring Friday event — something like 'PG Reflection'. That's 10 minutes to pull up your weekly report, see the patterns, and decide if anything needs to shift for next week."
- Frame as: this is where the system pays off — not just tracking, but learning from your own data and making better decisions about next week.
- NOT a chore — a decision-making ritual.

**User creates event externally → returns → LLM acknowledges.**

Guidance includes `"onboarding_complete": true` — signals the LLM that onboarding is done.

Onboarding complete.

---

## Why This Flow Works

1. **No empty report** — user never sees zero-value output
2. **No abstract explanation** — education happens in context, tied to their own data
3. **No silence gap** — value delivered in the same session
4. **Behavioral reinforcement** — small action (adding keywords to event titles) required before reward
5. **Progressive disclosure** — mechanics first (Phase 1), then meaning (Phase 2)

## What Should NOT Happen

- ❌ Generating report immediately after connection (before user adds keywords to event titles)
- ❌ Generating report with 0 keyword-matched hours
- ❌ Explaining OAuth scopes in detail
- ❌ Coaching user into defining all deliverables
- ❌ Making deliverables mandatory
- ❌ Setting up weekly reflection before user has seen value
- ❌ Explaining keywords before calendar is connected
- ❌ Using "tag" — always say "add the keyword to the event title"

## Deliverable Education — Single Touch

Deliverable education happens ONLY after the first real snapshot (Step 3b). Not during priority creation. The user needs to see their data before "outcome-based tracking" means anything concrete.

## Tool Architecture

Phase 2 onboarding is driven by a dedicated `onboarding_calendar_setup` MCP tool — NOT by overloading `get_weekly_report`.

### Why a separate tool?

| Concern | `get_weekly_report` | `onboarding_calendar_setup` |
|---------|--------------------|-----------------------------|
| Purpose | Operational weekly reflection | First-time education on how tracking works |
| Tone | Reflective, neutral | Educational, motivating |
| Sequencing | User-initiated anytime | Once, immediately after priority setup |
| Guidance | Semantic grouping proposals | Keyword education → snapshot → deliverables → reflection setup |
| State mutation | None (read-only) | None (read-only) |

Mixing these creates heuristic branching ("is this onboarding?") which violates structure-beats-instruction.

### Tool responsibility matrix (complete)

| Tool | Responsibility |
|------|---------------|
| `create_priority` | Phase 1 onboarding — define what to track |
| `onboarding_calendar_setup` | Phase 2 onboarding — explain how tracking works |
| `get_weekly_report` | Operational weekly reporting |

---

## `onboarding_calendar_setup` Tool Specification

### Metadata

- **Name:** `onboarding_calendar_setup`
- **Visibility:** public (LLM can see and call)
- **widget_accessible:** false (widget cannot call this)
- **widget_uri:** `"ui://widget/pg-dashboard.html"` (renders dashboard with snapshot data)
- **read_only_hint:** true (never mutates state)
- **destructive_hint:** false
- **open_world_hint:** true (reads Google Calendar via backend)
- **required_scopes:** `["pg.access"]`

### Description (binding rules)

```
ONBOARDING PHASE 2 — CALENDAR SETUP AND FIRST SNAPSHOT.

Call this tool ONLY after the user has set up their priorities AND connected Google Calendar via the dashboard. Do NOT call this for returning users who have already completed onboarding.

BINDING RULES: This is an educational flow. Guide the user through understanding how PG tracks time. Do NOT rush through — each step builds on the previous. Follow the assistant_guidance sequence exactly.

PRECONDITION: User must have at least 1 active priority AND Google Calendar connected. If calendar is not connected, do NOT call this tool — instead guide user to connect via the full dashboard first.
```

### Input Schema

```json
{
  "type": "object",
  "properties": {
    "phase": {
      "type": "string",
      "enum": ["keyword_education", "first_snapshot", "reflection_setup"],
      "description": "Which phase of onboarding step 2 to execute. Must be called in sequence: keyword_education first, then first_snapshot after user adds keywords to event titles, then reflection_setup after user sees snapshot."
    }
  },
  "required": ["phase"],
  "additionalProperties": false
}
```

The `phase` enum enforces sequencing structurally — the LLM cannot skip to `first_snapshot` without first calling `keyword_education`. The `assistant_guidance` from each phase tells the LLM what to do next and when to call the tool again.

### Handler behavior by phase

#### Phase: `keyword_education`

1. Call backend `GET /api/priority-guardian/priorities` to get active priorities with keywords
2. If no calendar connection → return error guidance: "Guide user to connect calendar in full dashboard first"
3. If no active priorities → return error guidance: "Guide user to set up priorities first"
4. Return structured guidance with:
   - Priority names + their assigned keywords (P1/P2/P3) for concrete examples
   - Keyword education instruction (use their real data)
   - Prompt to add keywords to 2-3 event titles and come back

**assistant_guidance:**
```json
{
  "action": "KEYWORD_EDUCATION",
  "priorities": [
    {"name": "Ship PG V1.0", "keyword": "P1"},
    {"name": "Client outreach", "keyword": "P2"}
  ],
  "instruction": "Explain how PG tracks time: add the keyword to the calendar event title. PG reads titles and counts hours automatically. Use the user's real priority names and keywords as examples: 'If [priority_name] is [keyword], name your event [keyword]: [example activity]'. Then prompt: 'Go add your keywords to 2-3 event titles from this week in your Google Calendar. Come back when you're done and I'll generate your first snapshot.' Do NOT present as a lecture — weave into conversation naturally. Do NOT use the word 'tag'.",
  "next_phase": "first_snapshot"
}
```

#### Phase: `first_snapshot`

1. Call the same backend endpoint as `get_weekly_report` — `GET /api/priority-guardian/weekly-report` (current week, live computation, no persistence)
2. Return snapshot data with onboarding-specific guidance (NOT the standard reflection guidance)

**assistant_guidance:**
```json
{
  "action": "FIRST_SNAPSHOT",
  "instruction": "Present the weekly snapshot. Frame positively — this is the user's first look at their data. Show how time splits across priorities. Acknowledge events without keywords: 'You still have ~Xh in events without keywords — that's normal. As you add keywords to more event titles, tracking becomes precise.' If semantic grouping of untagged events is possible, show overlap with priorities: 'These hours include [events] — some might already relate to your priorities.'",
  "deliverable_education": {
    "instruction": "After presenting the snapshot, explain deliverables. Show the contrast: Without deliverables: 'P1: 12h this week — client calls, proposal writing, research.' Hours and activity, but no sense of whether you're on track. With deliverables: 'P1: 4/10 deliverables done, 20 days to deadline.' Now you know exactly where you stand. Then: 'You can add E2E deliverables in the dashboard — the big chunks of work from start to finish. Not tasks, just the major pieces. Add them anytime.' For flexible priorities: 'Your monthly goal already anchors what the hours should produce.' No coaching. No prompting to add them now."
  },
  "next_phase": "reflection_setup"
}
```

#### Phase: `reflection_setup`

1. No backend call needed — purely guidance-driven
2. Return structured guidance for weekly reflection event setup

**assistant_guidance:**
```json
{
  "action": "REFLECTION_SETUP",
  "instruction": "Introduce two ways to track progress: 1) Dashboard — the progress bar shows real-time hours, a quick glance anytime. 2) Weekly report — PG saves a snapshot each week, building history for week-over-week comparison. Over time this reveals patterns: 'Am I consistently under-investing in P2?' or 'Client work keeps eating into P1 time.' The weekly report is where you spot patterns and decide what to adjust. Then suggest: 'Create a recurring Friday event — something like PG Reflection. That's 10 minutes to pull up your weekly report, see the patterns, and decide what to shift for next week.' Frame as: this is where the system pays off — learning from your own data. NOT a chore — a decision-making ritual.",
  "onboarding_complete": true
}
```

### Registry

Add to `TOOL_REGISTRY` in `tools/__init__.py`. Add invocation messages:

```python
"onboarding_calendar_setup": (
    "Setting up your tracking...",
    "Here's your Priority Guardian dashboard.",
),
```

### What this tool does NOT do

- Does NOT persist any data
- Does NOT create snapshots
- Does NOT modify priorities or calendar
- Does NOT duplicate `get_weekly_report` logic — calls the same backend endpoint
- Does NOT replace `get_weekly_report` for returning users

### Handler Guards

1. **Already onboarded:** If past `pg_weekly_snapshots` exist for this user, return error guidance: "User has already completed onboarding. Use get_weekly_report for regular reflection." No new DB column needed — existing snapshots are the signal.

2. **Zero keyword hours on `first_snapshot`:** If all priority hours == 0 and other_hours > 0, return guidance: "Keywords aren't reflected yet — make sure they're in the event titles and give Google a moment to sync. Try again in a minute." Do NOT show an empty report — this violates the "no zero-value output" rule.

3. **No calendar connection on `keyword_education`:** Return error guidance: "Google Calendar isn't connected yet. Open the full dashboard to set that up first."

4. **No active priorities:** Return error guidance: "Set up at least one priority first."

---

## Unit Tests

**File:** `tests/unit/mcp_pg/test_onboarding_calendar_setup.py`

1. **test_keyword_education_returns_priorities_with_keywords** — mock backend returning 2 active priorities. Assert guidance includes priority names and keywords.
2. **test_keyword_education_no_connection_returns_error** — mock backend returning no connection. Assert `isError=True` with guidance to connect via dashboard.
3. **test_keyword_education_no_priorities_returns_error** — mock backend returning 0 priorities. Assert error guidance.
4. **test_first_snapshot_returns_weekly_data** — mock backend returning current week report with tagged hours. Assert response includes snapshot data and deliverable_education.
5. **test_first_snapshot_zero_keyword_hours_returns_retry_guidance** — mock backend returning 0 priority hours, >0 other hours. Assert guidance tells user keywords aren't reflected yet. Assert NO snapshot data in response.
6. **test_first_snapshot_already_onboarded_returns_error** — mock backend indicating past snapshots exist. Assert error guidance saying user is already onboarded.
7. **test_reflection_setup_returns_guidance_only** — call with phase `reflection_setup`. Assert no backend call made. Assert guidance includes `onboarding_complete: true`.
8. **test_schema_rejects_invalid_phase** — assert schema `additionalProperties: false` and enum validation.
9. **test_tool_is_read_only** — assert `read_only_hint=True` on tool definition.
10. **test_tool_not_widget_accessible** — assert tool is not widget-callable.

## Integration Tests

**File:** `tests/integration/priority_guardian/test_onboarding_flow.py`

11. **test_keyword_education_with_real_priorities** — create user with 2 priorities, call `keyword_education` phase, assert response contains correct priority names and keywords.
12. **test_first_snapshot_with_tagged_events** — create user with priorities and calendar connection, call `first_snapshot`, assert response includes weekly allocation data.
13. **test_first_snapshot_already_onboarded_rejected** — create user with past snapshots, call `first_snapshot`, assert error response.
14. **test_full_onboarding_sequence** — call all three phases in order, assert each returns expected guidance with correct `next_phase` / `onboarding_complete`.

## Logging

Each handler phase must log:
- `onboarding.phase_called` — phase name, user_id, correlation_id
- `onboarding.no_connection` — when calendar not connected
- `onboarding.no_priorities` — when no active priorities
- `onboarding.zero_keyword_hours` — when first_snapshot has no tagged hours
- `onboarding.already_completed` — when past snapshots exist
- `onboarding.phase_success` — phase completed successfully

---

## Implementation Details

### Calendar connection check

The `GET /api/priority-guardian/priorities` response includes:
```python
google_connection = data.get("google_connection", {"connected": False})
```
Use `google_connection["connected"]` as the boolean check in `keyword_education` phase.

### Past snapshots check ("already onboarded" guard)

Call `GET /api/priority-guardian/weekly-report` with last Monday's `week_start` parameter. If `snapshot_saved: true` in response, user has past snapshots → already onboarded.

```python
from datetime import date, timedelta
today = date.today()
days_since_monday = today.weekday()
last_monday = today - timedelta(days=days_since_monday + 7)
week_start = last_monday.isoformat()
# Call: /api/priority-guardian/weekly-report?week_start={week_start}
# If response["data"]["snapshot_saved"] == True → already onboarded
```

### Weekly report endpoint

`GET /api/priority-guardian/weekly-report` with no `week_start` parameter returns current week with live Google Calendar computation (no persistence).

Response structure:
```python
{
    "success": True,
    "data": {
        "week_start": "2026-02-17",
        "week_end": "2026-02-23",
        "is_current_week": True,
        "snapshot_saved": False,
        "priorities": [...],
        "time_allocation": {
            "total_tracked_hours": 24.5,
            "keywords": {
                "P1": {"hours": 8.0, "event_count": 5},
                "P2": {"hours": 4.0, "event_count": 3},
                "P3": {"hours": 0.0, "event_count": 0},
            },
            "other_hours": 12.5,
        },
        "all_events": [...],
    },
}
```

### Zero keyword hours detection

```python
ta = data["time_allocation"]
priority_hours = sum(ta["keywords"][kw]["hours"] for kw in ["P1", "P2", "P3"])
other_hours = ta["other_hours"]
total = ta["total_tracked_hours"]

if total == 0:
    # Empty week — no events at all
    return guidance("No calendar events found this week...")
elif priority_hours == 0 and other_hours > 0:
    # Events exist but no keywords in titles
    return retry_guidance("Keywords aren't reflected yet...")
else:
    # Has real keyword-matched data — proceed with snapshot
    ...
```
