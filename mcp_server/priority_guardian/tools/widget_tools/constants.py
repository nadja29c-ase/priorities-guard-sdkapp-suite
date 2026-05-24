# Single source of truth for the widget URI.
#
# Imported by:
#   - mcp_server/priority_guardian/handlers/resources.py (resource read handler)
#   - mcp_server/priority_guardian/tools/get_priorities.py
#   - mcp_server/priority_guardian/tools/create_priority.py
#   - mcp_server/priority_guardian/tools/render_weekly_report.py
#
# When bumping the version: change ONLY this constant.
# Do not redefine WIDGET_URI in any other file. Two copies will drift.
#
# Bump version (v12 → v13 → v14 ...) whenever the widget bundle content changes,
# to force ChatGPT to invalidate its widget cache and fetch the new bundle.
WIDGET_URI = "ui://widget/pg-dashboard-v14.html"
