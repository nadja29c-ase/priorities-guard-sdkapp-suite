# Single source of truth for the widget URI.
#
# Imported by:
#   - mcp_server/priority_guardian/handlers/resources.py (resource read handler)
#   - mcp_server/priority_guardian/tools/get_priorities.py
#   - mcp_server/priority_guardian/tools/create_priority.py
#   - mcp_server/priority_guardian/tools/render_weekly_report.py
#
# IMPORTANT: Do NOT bump the version for approved ChatGPT Store apps!
# OpenAI freezes the tool schema at approval time — ChatGPT requests the URI
# from the frozen schema, not the live MCP server's tools/list response.
# Bumping to a new version breaks the handler (returns empty, ChatGPT falls
# back to stale CDN cache). Last working version: v12.
#
# To update widget content: change the HTML bundle, keep URI unchanged.
# ChatGPT fetches fresh content on each ReadResourceRequest.
WIDGET_URI = "ui://widget/pg-dashboard-v12.html"
