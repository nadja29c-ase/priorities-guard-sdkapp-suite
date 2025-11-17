# Increment 4: Webhook Registration (watch_calendar)  
**Final Version + Critical Implementation Instructions for Claude Code**

**Goal:** Register Google Calendar push notifications so the app receives real-time updates instead of polling.

**Builds on:** Increments 1A–3 (OAuth, check_calendar, token refresh)

---

# 1. Files to Modify/Create
backend/core/google_calendar.py # Add register_webhook() and stop_webhook()
backend/apps/focused/router.py # Add /api/focused/watch_calendar AND /webhook/... routes
backend/apps/focused/logic.py # Add watch_calendar_logic()
backend/core/models.py # Add webhook fields to CoreConnection
alembic/versions/00X_add_webhook_fields.py

---

# 2. Database Changes

Add the following columns to `core_connections`:

```sql
google_channel_id VARCHAR(255)
google_resource_id VARCHAR(255)
google_channel_expires_at TIMESTAMPTZ

Migration: Create via alembic autogenerate.

---
# 3. Google API: events.watch

Endpoint:
POST https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/watch

Increment 4 rule:
Use calendar_id = "primary" (hardcoded). Multi-calendar support comes in a future increment.

Request Body:
{
  "id": uuid4().hex,  # channel_id (store in DB)
  "type": "web_hook",
  "address": f"https://www.priority-guard.com/webhook/focused/google_calendar/{user_id}"
}


**Note:**
Do not include expiration. Google assigns expiration in the response.

**Headers:**
Authorization: Bearer {access_token}
User-Agent: FocusedApp/1.0 (+https://www.priority-guard.com)

Response Example:
{
  "id": "channel_id",
  "resourceId": "opaque_resource_id",
  "expiration": "1234567890000"  # Unix ms
}

Retry policy:
Retry 429 / 500 / 503 with exponential backoff (same as Increment 3).
Do not retry 400 / 403.

# 4. Backend Endpoint
POST /api/focused/watch_calendar

Request:
{
  "user_id": "test_user"
}

**Flow:**
- Fetch user's connection from DB
- Check token expiration → auto-refresh if needed
- If existing channel:
    - Call events.stop
    - Log warning if stop fails
    - Continue anyway (never fail re-registration because stop failed)
    - Generate new channel_id
    - Call events.watch

- Store the following in DB:**
new google_channel_id
google_resource_id
google_channel_expires_at (converted from ms to UTC timestamp)

- Return success response**
Success Response:
{
  "success": true,
  "data": {
    "channel_id": "...",
    "expires_at": "2024-01-22T10:00:00Z"
  }
}

**Errors:**
- USER_NOT_CONNECTED
- WEBHOOK_REGISTRATION_FAILED
- API_QUOTA_EXCEEDED

# 5. Webhook Receiver (Placeholder)
POST /webhook/focused/google_calendar/{user_id}

Validation Rules:
- Check required headers exist
- Check that X-Goog-Channel-ID matches the one stored in DB
- Log event details (INFO)
- Always return HTTP 200 OK, even if validation fails

Headers from Google:
- X-Goog-Channel-ID: channel UUID
- X-Goog-Resource-State: sync / exists / not_exists
- X-Goog-Resource-ID: resource UUID

On validation failure:
- Log warning
- Still return 200 OK (avoids Google shutting down the channel)

No event processing in this increment.

# 6. Re-Registration Behavior

If an existing webhook is present:
Attempt to stop old channel via events.stop

If stop fails (404 / network error):
Log warning
Continue
Create new channel via events.watch
Update DB with new channel_id, resource_id, expires_at

Never reuse existing channels. Always create a fresh one.

# 7. Edge Cases & Testing

Test 1: First registration
- Registers successfully
- DB populated correctly

Test 2: Re-registration
- Stops old channel
- Registers new one
- DB updated

Test 3: Token expired
- Auto-refresh triggers
- Registration works

Test 4: Quota exceeded (403)
- No retry
- Return API_QUOTA_EXCEEDED

Test 5: Invalid webhook URL
- Google returns 400
- Return WEBHOOK_REGISTRATION_FAILED

Test 6: Valid webhook callback
- Headers correct
- channel_id matches
- Logged as INFO
- Returns 200

Test 7: Invalid channel_id
- Log warning
- Return 200

Test 8: Missing headers
- Log warning
- Return 200

Test 9: Network failure during registration
- Retry up to 3 times
- Return error if all retries fail

Test 10: events.stop fails
- Log warning
- Continue registration

8. Technical Constraints
- All async
- Use shared httpx.AsyncClient
- Exponential backoff for 429/500/503
- No retry for 400/403
- Use calendar_id = "primary" (hardcoded for Increment 4 only)
- Never log tokens or response bodies
- Structured error responses only
- request_id included in logs
- Webhook receiver must always return 200
- events.stop failure must not prevent new registration

9. Success Criteria

✅ watch_calendar endpoint implemented
✅ Channel registration works
✅ Old channel is stopped before creating new
✅ Channel metadata stored (ms → UTC)
✅ Webhook receiver validates headers
✅ Invalid/malformed webhooks return 200
✅ Retry logic implemented
✅ No token leakage in logs
✅ Clear, structured errors
✅ All 10 edge cases pass

10. Out of Scope

❌ Webhook renewal (Increment 5)
❌ Event processing
❌ Redis idempotency
❌ HMAC verification
❌ Conflict detection
❌ Multi-calendar support
❌ “Stop webhook” endpoint

11. Known Limitations
- No renewal → channel expires after ~7 days
- No idempotency → duplicate webhook events processed
- No HMAC → basic channel_id validation only
- Only primary calendar supported
- No event ingestion yet

# ⚠️ Critical Implementation Instructions for Claude Code

These MUST be followed exactly. No deviations.
If a rule contradicts existing code, the rule wins.
A. Do NOT refactor unrelated code

Only modify:
google_calendar.py
focused/router.py
focused/logic.py
the DB model + migration

No other files.

B. Hardcode "primary" inside watch_calendar_logic()

Do not create DB fields for calendar_id.
Do not store calendar_id anywhere.

C. events.stop must NOT block new registration

If events.stop fails:
- Log warning
- Continue with new registration
- Never return an error caused by failing stop

D. Webhook receiver MUST always return 200

Even for:
invalid/missing headers
invalid channel_id
unknown user
mismatched states

Google treats non-2xx as fatal.

E. Use existing patterns from Increment 3

Use shared http_client
Use identical retry/backoff logic
Include User-Agent header
Use token refresh before watch

F. Never log:

- access token
- refresh token
- encrypted token
- Google response body

Only log:
- channel_id
- request_id
- safe metadata

G. Convert expiration from ms → UTC seconds

Use:
expires_at = datetime.fromtimestamp(int(expiration_ms) / 1000, tz=timezone.utc)

Store EXACTLY as TIMESTAMPTZ.

H. Return structured errors

Use:
"WEBHOOK_REGISTRATION_FAILED"
"API_QUOTA_EXCEEDED"
"USER_NOT_CONNECTED"

Do NOT invent new formats.

I. Retry rules (strict)

Retry ONLY:
429
500
503

httpx.RequestError

Do NOT retry:
400
403

J. No HMAC verification yet

Do not add:
WEBHOOK_SECRET
HMAC verification
channel tokens
