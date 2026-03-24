Increment 56b — Remove outputTemplate from all CRUD tool handlers
Context: 56a fixed the ref not being advanced after CRUD. Bug persists because the iOS host replaces window.openai.toolOutput with a new object reference when it receives a tool response containing outputTemplate. This happens after the ref is advanced, creating a new mismatch that triggers the overwrite on expand. Removing outputTemplate from CRUD tools stops the host from replacing toolOutput after mutations.
No widget changes. Python backend only.
Files — in mcp_server/priority_guardian/tools/widget_tools/, remove the _meta block from structured_content in each of these files:

update_deliverable.py
add_deliverable.py
delete_deliverable.py
update_goal.py
add_goal.py
delete_goal.py
update_priority.py
delete_priority.py
add_priority.py

Also check connect_google_calendar.py and disconnect_google_calendar.py — apply same removal if present.
In each file, remove this block from structured_content:
python"_meta": {
    "openai/outputTemplate": WIDGET_URI,
},
Do NOT touch get_priorities.py or get_weekly_report.py.
No App.tsx changes. No new tests required.
Read OPERATIONS_PREDEPLOYMENT.md before committing.