Goal

Enforce strict MVP1 rule:
Manual activation only supports “start now”, not “start later”.
All future-scheduled activations must be rejected by the backend and surfaced by the SDK with a clear prompt.

This applies to:

“activate tomorrow…”

“activate at 9am…”

“activate in 2 hours…”

any request where the user expects delayed activation

Calendar-driven activation remains unchanged (handled automatically via Google Calendar events).

Backend Requirements (run_focus_mode_impl.py)
1. Manual activation must happen immediately

Trigger:
action="on" AND trigger_source="user"

Behavior:

Reject any fields implying future start (none exist today, but guard anyway)

Reject missing duration_minutes

Reject negative or >480 duration (already implemented)

Add one new check just after validating duration_minutes:

if trigger_source == "user" and "future" in requested_intent_context:
    return _error_response("Future activation is not supported. Create a calendar block instead.")


Since the backend receives no natural language, this is actually:

Do nothing. No changes needed.
Backend already enforces:

start = now

duration required

no “future” semantic fields exist

Backend is fully compliant. No code change required.

SDK Layer Requirements (ChatGPT App Tooling)
Implement an intent filter before calling run_focus_mode:

If user expresses a future time (natural language):

parse with your existing LLM logic

do NOT call run_focus_mode

respond with:

"Scheduling Focus Mode in the future isn’t supported. 
If you want Focus Mode to turn on at a specific time, 
create a calendar event and Focused will handle it automatically."


Examples that must trigger this path:

“turn on focus mode at 9am”

“activate focus mode tomorrow morning”

“start focus mode in two hours”

“activate focus for the whole day tomorrow”

“schedule a focus session for Friday”

For valid “start now” intents:

Call:

{
  "action": "on",
  "trigger_source": "user",
  "duration_minutes": <parsed_value>,
  "user_confirmation": true
}

For missing duration:

SDK must ask:

“For how long?”

Test Cases Claude Must Add
New SDK tests (NOT backend tests)

future scheduling detected → rejected

calendar suggestion provided

no backend call made

manual immediate activation still works

manual immediate activation without duration triggers prompt

Backend tests remain unchanged.

Summary for Claude

DO NOT change backend code.

Add future-intent detection in the SDK layer.

Add SDK tests to match this behavior.

Respond with calendar-block suggestion for any future scheduling request.