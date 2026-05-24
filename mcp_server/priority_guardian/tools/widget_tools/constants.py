# Single source of truth for the widget URI.
#
# Imported by:
#   - mcp_server/priority_guardian/handlers/resources.py (resource read handler)
#   - mcp_server/priority_guardian/tools/get_priorities.py
#   - mcp_server/priority_guardian/tools/create_priority.py
#   - mcp_server/priority_guardian/tools/render_weekly_report.py
#
# IMPORTANT: Do NOT bump the version for approved apps!
# OpenAI freezes the tool schema at approval time. ChatGPT will always request
# the URI from the frozen schema (v12). Bumping to v13/v14 breaks the handler
# (returns empty response, ChatGPT falls back to stale CDN cache).
#
# To update widget content: change the HTML bundle, keep URI unchanged.
# ChatGPT fetches fresh content on each ReadResourceRequest regardless of URI.
WIDGET_URI = "ui://widget/pg-dashboard-v12.html"
