Increment 48b — Centralize WIDGET_URI
Goal: Single source of truth for the widget URI. When the version bumps next time, one edit instead of 13.

Context
WIDGET_URI = "ui://widget/pg-dashboard-v8.html" is currently defined as a module-level constant in 13 files:
In mcp_server/priority_guardian/tools/widget_tools/:
add_priority.py, update_priority.py, delete_priority.py, add_deliverable.py, update_deliverable.py, delete_deliverable.py, add_goal.py, update_goal.py, delete_goal.py, connect_google_calendar.py, disconnect_google_calendar.py
In mcp_server/priority_guardian/tools/:
get_priorities.py, get_weekly_report.py

What to do
1. Create mcp_server/priority_guardian/tools/widget_tools/constants.py
python# Single source of truth for the widget URI.
# Must stay in sync with WIDGET_URI in handlers/resources.py.
# Update this value when the widget version bumps.
WIDGET_URI = "ui://widget/pg-dashboard-v8.html"
2. In all 11 files inside widget_tools/:
Remove the module-level WIDGET_URI = "..." line and replace with:
pythonfrom .constants import WIDGET_URI
3. In tools/get_priorities.py and tools/get_weekly_report.py:
Remove the module-level WIDGET_URI = "..." line and replace with:
pythonfrom .widget_tools.constants import WIDGET_URI

Constraints

widget_tools/ already contains __init__.py — do not remove or modify it.
Replace only the literal WIDGET_URI = "ui://widget/pg-dashboard-v8.html" assignments. Do not touch any computed values or any other constants.
The string value "ui://widget/pg-dashboard-v8.html" must be identical before and after in all files.
No logic changes anywhere. No other modifications.
Do not touch handlers/resources.py — it has its own WIDGET_URI and WIDGET_VERSION constants that control widget resource registration, not tool response metadata. These two files serve different purposes and must remain separate. They must always hold the same URI value but are intentionally not merged.


Verification
After the change:
bashgrep -r 'WIDGET_URI = "ui://' mcp_server/
Must return exactly one result: constants.py.
All other files must show either from .constants import WIDGET_URI or from .widget_tools.constants import WIDGET_URI.

Deployment
Normal Render deploy required. Tools are loaded at startup — import changes are not picked up without a server restart. Runtime behavior is unchanged.