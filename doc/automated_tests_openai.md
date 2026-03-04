
What OpenAI's automated scans likely check:

MCP server reachability — Can they hit your public HTTPS endpoint and get a valid MCP response? Your server must be on a publicly accessible domain, not localhost/ngrok.
CSP declaration — You defined openai/widgetCSP on your widget resources. This is explicitly stated as "required to submit your app for security reasons." Their scan almost certainly validates this exists.
HTTPS everywhere — They'll verify your MCP endpoint is TLS-secured. No HTTP.
Tool listing — They call your MCP server, list tools, and validate: tool names are present, descriptions exist, annotations (readOnlyHint, openWorldHint, destructiveHint) are set. "Incorrect or missing action labels are a common cause of rejection."
OAuth flow completeness (for authenticated apps) — They'll attempt the full OAuth dance: hit /.well-known/oauth-protected-resource, do dynamic client registration, authorize, exchange code for token, call a tool with that token. If any step fails, rejected.
Schema validation — outputSchema matches what your tools actually return in structuredContent. Mismatches = rejection.
Error responses — They likely send malformed requests or invalid tokens to see if your server crashes or returns garbage vs. proper error codes (401 with WWW-Authenticate, etc.). "Apps should not crash, hang, or show inconsistent behavior."
Response latency — "Slow responses" are flagged in their troubleshooting docs. Components that take more than a few hundred milliseconds feel sluggish. They may have a timeout threshold.