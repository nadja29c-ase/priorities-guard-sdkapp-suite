markdown# Increment 10: /disconnect Endpoint + User Offboarding

## Purpose
Enable users to revoke app access and delete their data per GDPR Art. 17 and OpenAI SDK compliance (Checklist B21, B23, C39).

---

## Prerequisites (Verify Before Implementation)
```sql
-- Verify actual DB values and adjust WHERE clauses accordingly
SELECT DISTINCT client_id FROM oauth_access_tokens WHERE scope LIKE '%focused%';
SELECT DISTINCT provider FROM core_connections WHERE connection_type = 'oauth_provider';
SELECT google_channel_id, google_resource_id FROM core_connections LIMIT 1; -- confirm columns exist
```

---

## Endpoints

### 1. POST /api/focused/disconnect

**Sequence (order matters):**

1. **Cancel all Celery jobs for user**
   - Token refresh jobs
   - Webhook renewal jobs
   - Scheduled focus deactivations
   - Pattern recompute jobs
   - Use `celery.control.revoke(task_id, terminate=True)` for each
   - Query `focused_scheduled_jobs` for pending task IDs

2. **Stop Google webhook channel**
```
   POST https://www.googleapis.com/calendar/v3/channels/stop
   Headers: Authorization: Bearer <access_token>
   Body: {"id": "<channel_id>", "resourceId": "<resource_id>"}
```
   - Retrieve `google_channel_id` and `google_resource_id` from `core_connections`
   - If stop fails → log warning, continue

3. **Revoke Google OAuth**
   - Call `POST https://oauth2.googleapis.com/revoke?token={refresh_token}`
   - **Must use refresh_token** (invalidates both access + refresh)
   - If revoke fails → log warning, continue

4. **Revoke ALL ChatGPT OAuth tokens for this user**
```sql
   UPDATE oauth_access_tokens 
   SET revoked = TRUE, revoked_at = NOW() 
   WHERE user_id = ? AND scope LIKE '%focused.%'
   
   DELETE FROM oauth_authorization_codes 
   WHERE user_id = ? AND scope LIKE '%focused.%'
```
   - Do NOT delete `oauth_access_tokens` rows (need revocation audit trail)
   - Mark revoked, don't delete

5. **Update core_connections (Google only)**
```sql
   UPDATE core_connections 
   SET status = 'revoked', revoked_at = NOW(),
       google_channel_id = NULL, google_resource_id = NULL
   WHERE user_id = ? AND connection_type = 'oauth_client' AND provider = 'google'
```
   - **Do NOT revoke** `connection_type = 'oauth_provider'` (ChatGPT client registration stays for potential reconnect)

6. **Clear Redis cache**
```python
   # Use SCAN + DEL (not pattern DELETE)
   patterns = [
       f"focused:user:{user_id}:*",
       f"focused:webhook:{channel_id}",
       f"focused:pattern:{user_id}"
   ]
   for pattern in patterns:
       for key in redis.scan_iter(match=pattern):
           redis.delete(key)
```

7. **Return 200** with `{"status": "disconnected", "revoked_at": "<timestamp>"}`

**Idempotency:** Calling twice returns 200 (already disconnected state)

---

### 2. DELETE /api/focused/delete-data

**Sequence:**

1. **Call /disconnect logic first** (if not already disconnected)

2. **Delete from focused_* tables (cascade order):**
```sql
   DELETE FROM focused_scheduled_jobs WHERE user_id = ?;
   DELETE FROM focused_conflict_cache WHERE user_id = ?;
   DELETE FROM focused_consent_preferences WHERE user_id = ?;
   DELETE FROM focused_notification_settings WHERE user_id = ?;
   DELETE FROM focused_onboarding_state WHERE user_id = ?;
   DELETE FROM focused_focus_pattern_cache WHERE user_id = ?;
   DELETE FROM focused_focus_sessions WHERE user_id = ?;
```

3. **Delete Focused-specific consents:**
```sql
   DELETE FROM core_consents WHERE user_id = ? AND app_name = 'focused';
```

4. **Delete Focused OAuth tokens (now safe to hard-delete after disconnect marked them revoked):**
```sql
   DELETE FROM oauth_access_tokens WHERE user_id = ? AND scope LIKE '%focused.%';
```

5. **Delete Focused client registration (if exists):**
```sql
   DELETE FROM core_connections 
   WHERE user_id = ? AND connection_type = 'oauth_provider' AND provider = 'chatgpt_focused';
```
   - Adjust `provider` value based on prerequisite verification

6. **Write audit log:**
```sql
   INSERT INTO core_tool_audit_log (user_id, app_name, tool_name, result_status, created_at)
   VALUES (?, 'focused', 'delete_data', 'success', NOW());
```

7. **Return 200** with `{"status": "deleted", "tables_affected": 7}`

**Note:** Do NOT update `core_users.deleted_at` — this is app-specific deletion, not full account deletion. The `core_users` row stays untouched (shared across SDK apps).

**Idempotency:** Calling twice returns 200 (no data to delete)

---

## Database Changes

**Migration required:**
```sql
ALTER TABLE core_connections ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMP NULL;
-- core_users.deleted_at is NOT added in this increment (reserved for full account deletion)
```

**Existing columns (verify from Increment 4):**
- `core_connections.google_channel_id`
- `core_connections.google_resource_id`

---

## Celery Tasks

### delete_user_data_task(user_id)
- Async wrapper for delete-data logic
- Retry: 3 attempts, exponential backoff (5s, 25s, 125s)
- On final failure: log to `core_tool_audit_log` with `result_status='failed'`

### Job Cancellation Helper
```python
def cancel_user_jobs(user_id: str) -> int:
    """Cancel all pending Celery jobs for user. Returns count cancelled."""
    jobs = db.query(FocusedScheduledJob).filter_by(user_id=user_id, status='pending').all()
    for job in jobs:
        celery.control.revoke(job.celery_task_id, terminate=True)
        job.status = 'cancelled'
    db.commit()
    return len(jobs)
```

---

## MCP Behavior After Revocation

- MCP server validates JWT against JWKS (stateless)
- Revoked tokens have `revoked=TRUE` in DB but MCP doesn't check DB
- JWT expires naturally (1hr TTL)
- **Known limitation:** Revoked tokens remain usable up to 1hr until JWT expires
- For stricter revocation: add `/oauth/introspect` endpoint (future increment)

---

## Error Handling

| Scenario | Response |
|----------|----------|
| User not found | 404 |
| No active connection (disconnect) | 200 (idempotent) |
| Google revoke fails | Log warning, continue, return 200 |
| Google channel stop fails | Log warning, continue, return 200 |
| DB transaction fails | 500, rollback, log error |
| Celery job cancel fails | Log warning, continue |

---

## Security Requirements

- Require valid ChatGPT OAuth token
- Extract user_id from JWT `sub` claim
- Never log tokens
- Audit log: only `user_id`, `action`, `timestamp`, `tables_affected_count`

---

## Test Plan

### Unit Tests (10)
1. Disconnect with active Google connection → tokens revoked
2. Disconnect already disconnected → 200 (idempotent)
3. Disconnect when Google revoke fails → local cleanup succeeds
4. Delete-data cascades all focused_* tables
5. Delete-data idempotent (no data) → 200
6. Audit log written after delete
7. Celery job cancellation returns correct count
8. Redis cache cleared (SCAN + DEL)
9. Webhook channel stop called with correct channel_id + resource_id
10. Google revoke uses refresh_token (not access_token)

### Integration Tests (12)
11. Full disconnect → DB state validation (revoked flags set correctly)
12. Full disconnect → Redis keys deleted (verify with SCAN)
13. Full delete-data → all focused_* tables empty for user
14. Full delete-data → core_consents for focused deleted
15. Full delete-data → core_users row untouched (no deleted_at)
16. Google API mock: channel stop receives correct channel_id + resource_id
17. Google API mock: revoke receives refresh_token
18. Celery eager mode: job cancellation prevents execution
19. Multi-token revocation: user with 3 access tokens → all marked revoked
20. Cross-app isolation: disconnect Focused → other app connections unchanged
21. MCP tool call after disconnect → 401 (after token expires)
22. Concurrent disconnect + token refresh → no race condition (use Redis lock)

### E2E Lifecycle Test (1)
23. Full cycle:
    - User authorizes (Google + ChatGPT)
    - Events sync
    - Webhook registered
    - User disconnects
    - Verify: tokens revoked, webhook stopped, Redis cleared
    - User reconnects
    - Verify: fresh state, no stale data

### Celery-Specific Tests (4)
24. Webhook renewal task skips revoked users
25. Token refresh task skips revoked connections
26. Pattern recompute task skips deleted users
27. Scheduled deactivation cancelled on disconnect

---

## Files
```
backend/apps/focused/routers/offboarding_router.py
backend/apps/focused/logic/offboarding.py
backend/apps/focused/tasks/offboarding_tasks.py
backend/core/google_oauth.py  # add revoke_token(refresh_token)
backend/core/google_calendar.py  # add stop_channel(channel_id, resource_id)
alembic/versions/xxx_add_revoked_at_column.py
tests/focused/test_10_offboarding_unit.py
tests/focused/test_10_offboarding_integration.py
tests/focused/test_10_offboarding_e2e.py
```

---

## Known Limitations

- MCP stateless: revoked tokens valid until JWT expires (max 1hr)
- No UI disconnect button (future widget increment)
- No data export before deletion (data portability separate feature)
- `core_users` row retained (shared across SDK apps)
- No email notification on deletion
- App-specific deletion only; full account deletion is future increment

---

## Dependencies
- Increment 1B (Google OAuth) ✅
- Increment 4 (Webhook registration with channel_id/resource_id storage) ✅
- Increment 7B (ChatGPT OAuth Provider) ✅RetryClaude can make mistakes. Please double-check responses.