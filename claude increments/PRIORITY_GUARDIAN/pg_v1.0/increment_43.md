Increment Briefing: Redis Idempotent Token Replay + MCP Audience Fix (v4 — final)
Context
Priority Guardian FastAPI backend + MCP server on Render. ChatGPT sends multiple POST /oauth/token requests for the same authorization code within ~2 seconds. First succeeds (200), rest get invalid_grant: already used (400). ChatGPT aborts and never sends POST /mcp.

Part 1 — Backend: Redis Idempotent Token Replay
File: backend/core/oauth_provider/services/token_service.py
Redis client: use existing redis_client from backend/core/redis_client.py — async, env-prefixed, fail-open pattern already established in the codebase.
Current execution order in exchange_authorization_code():

SELECT ... FOR UPDATE — row lock acquired
auth_code.used check — early return if True
Validations (expiry, PKCE, client_id, redirect_uri)
Resource resolution
auth_code.used = True
Issue access + refresh tokens
db.add() + await db.commit() — lock released here
Return token response dict

Two insertion points:
Insertion point A — inside the auth_code.used == True branch (step 2):
if auth_code.used:
    → read Redis key "token_replay:" + sha256(code.encode("utf-8")).hexdigest()
    → if found:
        → parse wrapper JSON: { "client_id": "...", "cached_at": "...", "token_response": {...} }
        → verify wrapper["client_id"] == incoming client_id
        → if match: log oauth.token.idempotent_replay (include masked client_id, jti, replay_age_seconds), return wrapper["token_response"]
        → if mismatch: return ("invalid_grant", "Authorization code already used")
    → if not found or any Redis error: return ("invalid_grant", "Authorization code already used")
Insertion point B — after tokens are built, before db.commit(), while row lock is still held (between steps 6 and 7):
    → build standard OAuth token response dict (no client_id in it)
    → build Redis wrapper:
        {
            "client_id": auth_code.client_id,
            "cached_at": datetime.now(UTC).isoformat(),
            "token_response": { standard OAuth token response dict }
        }
    → serialize wrapper to JSON
    → write to Redis: key="token_replay:" + sha256(code.encode("utf-8")).hexdigest(), TTL=30s
    → if Redis write fails: log oauth.token.replay_write_failed (warning), continue
    → await db.commit()
    → if db.commit() raises: best-effort delete the Redis key, then re-raise normally
    → return token_response dict (not the wrapper — never return wrapper to caller)
Why this ordering is mandatory: The DB row lock is released at db.commit(). Writing Redis after commit leaves a race: concurrent request acquires lock, sees used=True, checks Redis before it is written, returns invalid_grant. Writing before commit guarantees the replay entry exists before any other request can reach the used check.
Redis key: "token_replay:" + sha256(code.encode("utf-8")).hexdigest()
Always hash the raw code string — sha256(code.encode("utf-8")).hexdigest() — no normalization, no trimming, no lowercasing. redis_client automatically adds the environment prefix via _prefix_key().
Security constraint: token_response contains access_token and refresh_token. Neither the wrapper nor the token response may be logged, written to metrics, or persisted outside Redis. The oauth.token.idempotent_replay log event must only include masked client_id, jti, and replay_age_seconds.
Fail-open: Redis errors at write time must be caught and swallowed — must not block commit or raise to caller. Redis errors at read time must fall through to invalid_grant. Follow the existing redis_client pattern.
Log events:

oauth.token.idempotent_replay (info) — fields: client_id (masked), jti, replay_age_seconds
oauth.token.replay_write_failed (warning) — when Redis write fails at insertion point B


Part 2 — MCP Server: Deploy Audience Fix
File: mcp_server/priority_guardian/mcp_auth.py
Already correct locally. Deploy-only, no code change:
pythonvalid_audiences = [MCP_RESOURCE_URL, MCP_SERVER_URL, PG_AUDIENCE]

Pre-Deploy
Read and follow doc/OPERATIONS_PREDEPLOY.md and doc/OPERATIONS_MIGRATIONS.md. No Alembic migration required. Manual redeploy on Render after push.

Unit Tests

Redis available: second call with used=True returns token response with same access_token, refresh_token, expires_in, scope, token_type
Redis available: client_id mismatch in wrapper → invalid_grant
Redis unavailable at read time: invalid_grant, no crash
Redis unavailable at write time: first exchange completes successfully, Redis error swallowed, oauth.token.replay_write_failed logged
Redis TTL expired (key missing on second call): invalid_grant
oauth.token.idempotent_replay logged with correct fields on replay path
DB commit fails after Redis write: Redis key deleted best-effort, exception propagated
Returned token response to caller never contains client_id or wrapper fields

Integration Tests

Full exchange → second identical exchange within 30s → same token response fields
Full exchange → second identical exchange after 30s → invalid_grant
Full exchange → second call with different client_id → invalid_grant
Redis down during exchange → first exchange succeeds, second returns invalid_grant, no 500
Concurrent duplicate requests: no request returns 500; at most one fresh token is issued; duplicate returns either replayed success or invalid_grant — both are acceptable outcomes
