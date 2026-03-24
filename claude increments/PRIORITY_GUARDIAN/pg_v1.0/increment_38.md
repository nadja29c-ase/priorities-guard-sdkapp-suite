Confirmed. google_connected_at is present in every single widget tool. Full picture:
FileHas google_connected_atadd_priority.py✅ yesadd_deliverable.py✅ yesadd_goal.py✅ yesupdate_priority.py✅ yesupdate_deliverable.py✅ yesupdate_goal.py✅ yesdelete_priority.py✅ yesdelete_deliverable.py✅ yesdelete_goal.py✅ yes
All 9 files. Same one-liner in each: "google_connected_at": google_connection.get("connected_at").

Increment briefing: Remove google_connected_at from all widget tool responses
Context
Increment 37 removed google_connected_at from get_priorities.py structuredContent but missed all 9 widget mutation tools. The field is unused by the widget (verified in ConnectionStatus.tsx — prop accepted but never rendered). This is output minimization compliance item #28.
What to fix
Remove the "google_connected_at": google_connection.get("connected_at") line from the structured_content["data"] dict in each of these 9 files:

widget_tools/add_priority.py
widget_tools/add_deliverable.py
widget_tools/add_goal.py
widget_tools/update_priority.py
widget_tools/update_deliverable.py
widget_tools/update_goal.py
widget_tools/delete_priority.py
widget_tools/delete_deliverable.py
widget_tools/delete_goal.py

No other changes. Do not touch logic, error handling, annotations, or any other field.
Verification

Grep confirms zero remaining occurrences: grep -rn "google_connected_at" mcp_server/priority_guardian/tools/
Existing tests still pass — no test should assert presence of this field; if any does, that test is wrong and should be updated to assert absence instead.

Read OPERATIONS_PREDEPLOY.md before committing.