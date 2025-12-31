Claude Code Briefing: Add Privacy Policy Route
Objective
Add a static HTML route to serve the privacy policy at /privacy-policy on the Unpack MCP server.
Context

Unpack is deployed on Render at https://fulfilling-productivity.onrender.com
The privacy policy HTML file exists at mcp_server/unpack/assets/privacy-policy.html
The MCP server uses FastAPI
This route is required for OpenAI SDK app submission

Requirements

Add GET route at /privacy-policy that serves the HTML file
Return HTMLResponse with correct content-type
Handle file not found gracefully (return 404 with message)
No authentication required — this is a public page

Expected Endpoint
GET /privacy-policy → Returns HTML content
File Locations

Server: mcp_server/unpack/server.py
Privacy policy: mcp_server/unpack/assets/privacy-policy.html

Acceptance Criteria

https://fulfilling-productivity.onrender.com/privacy-policy returns the privacy policy HTML
Response content-type is text/html
Works in browser (renders as webpage)

Notes

Keep it simple — just read the file and return it
Use pathlib.Path relative to the server file location
No caching needed for now

