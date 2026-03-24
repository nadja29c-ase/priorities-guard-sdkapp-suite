Increment: Production Latency Verification
Goal
Create and run a one-shot latency check script against the live Render services to verify Priority Guardian performs within acceptable thresholds before OpenAI store submission.
Services:

Backend: https://priorities-guard-sdkapp-suite.onrender.com
MCP Server: https://pg.priority-guard.com

What to build
ops/pg_latency_check.py — standalone, no new dependencies beyond httpx.
Endpoints to measure — derive exact paths from the codebase:

Backend: GET /, GET /api/priority-guardian/health, GET /oauth/pg/.well-known/openid-configuration, GET /oauth/pg/jwks
MCP: GET /, GET /health, HEAD /mcp, GET /.well-known/oauth-protected-resource, POST /mcp (JSON-RPC method: tools/list)

For POST /mcp: send JSON-RPC body {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}} with headers Content-Type: application/json and Accept: application/json, text/event-stream (both required — 406 without them). Response is SSE-framed; parse data: lines to extract and print tool count.
HTTP client: single httpx.Client session, timeout 15s.
Output per endpoint: icon + method + label + elapsed ms + HTTP status + threshold label. Thresholds: <300ms good, 300–500ms acceptable, 500–1000ms sluggish, >1000ms timeout risk. Summary at end.
Run it after creating it. Report results.
Read OPERATIONS_PREDEPLOY.md before starting.