Increment 5 — Webhook Reliability Layer

Event-Driven Renewal + Redis Idempotency (No Celery)

Goal:
Establish the reliability foundation for the Google Calendar webhook pipeline by adding:

Redis idempotency (dedupe duplicate webhook notifications)

Inline event-driven webhook renewal (<48h expiration)

Short-lived needs_sync flag for future increments

Proper throttling to prevent renewal spam

Full 200 OK compliance with Google’s webhook delivery rules

This increment does NOT process events yet.
Full event ingestion begins in Increment 6.

1. Files to Modify / Create
backend/core/config.py
    - Add webhook renewal threshold + TTL constants

backend/core/redis_client.py
    - add set_nx_with_ttl()
    - add idempotency helper
    - add renewal throttle helper
    - add needs_sync helper

backend/apps/focused/logic_webhook.py
    - new process_webhook_event() function
    - add should_renew_webhook() helper
    - integrate idempotency + needs_sync + renewal

backend/apps/focused/focused_router.py
    - update webhook endpoint to delegate to logic_webhook

tests/focused/test_increment_5.py
    - new test file


No Celery.
No scheduling.
No new database tables.

2. Redis Keys
2.1 Idempotency Key (Prevent Duplicate Webhooks)

Pattern:

focused:webhook:{user_id}:{message_number}


TTL: 24 hours

Behavior:

If key exists → duplicate → log + return 200 immediately

If key does not exist:

SET NX EX 86400

Continue processing

2.2 needs_sync Flag

Indicates that the user's calendar changed, but is not processed yet (Increment 6 will handle it).

Pattern:

focused:needs_sync:{user_id}


TTL: 5 minutes

Behavior:

Set only on first-time events (non-duplicate)

No additional logic attached yet

2.3 Renewal Throttle Key

Prevents multiple renewals if many webhooks arrive close together.

Pattern:

focused:webhook:renew_throttle:{user_id}


TTL: 24 hours

Behavior:

If throttle key exists → skip renewal

If not → set key → proceed with renewal

3. Webhook Renewal Logic (Event-Driven Only)
Trigger Condition

Inline inside webhook logic:

if connection.google_channel_expires_at <= now + timedelta(hours=48):
    attempt renewal

Renewal Steps

Stop old channel (stop_webhook)

Register new channel (register_calendar_webhook)

Parse expiration_ms → datetime

Update DB:

google_channel_id

google_resource_id

google_channel_expires_at

updated_at

Commit DB changes

Retry Rules (Same as Increment 3 & 4)

Retry only:

429 (respect Retry-After header)

500 / 503

network errors (httpx.Timeout, httpx.RequestError)

Do NOT retry:

400 invalid request

403 quota exceeded

On Renewal Failure

Log error

Do not break the webhook handler

Do not return error to Google

Still return 200 OK

4. Webhook Handler Enhancements

Existing endpoint:

POST /webhook/focused/google_calendar/{user_id}

Full Flow:
1. Extract headers

X-Goog-Channel-ID (required)

X-Goog-Message-Number (required)

X-Goog-Resource-State (optional)

X-Goog-Resource-ID (optional)

Missing headers → log warning → continue → always return 200.

2. Idempotency Check (FIRST)
key = focused:webhook:{user_id}:{message_number}


If exists → log → return 200 OK

If not → set key → continue

3. Set needs_sync Flag
focused:needs_sync:{user_id} = true (TTL 5 minutes)

4. Check Renewal Condition

If channel expires in <48h:

Check throttle key:

focused:webhook:renew_throttle:{user_id}


If key exists → skip renewal

If not:

Set throttle key (TTL 24h)

Perform inline renewal via register_calendar_webhook()

5. Always Return 200 OK

Regardless of:

bad headers

invalid channel

throttle

renewal success or failure

missing fields

Redis errors

Google errors

This is required by Google to avoid channel shutdown.

5. Tests (tests/focused/test_increment_5.py)

You must test at least:

1. Idempotency — New Event

message_number unseen → set key → set needs_sync → return 200

2. Idempotency — Duplicate Event

message_number seen → skip logic → return 200

3. Missing message_number

warn + continue → return 200

4. Renewal Needed (<48h)

throttle absent → renewal attempted → DB updated

5. Renewal Not Needed (>48h)

renewal not triggered

6. Renewal Throttled

throttle key exists → skip renewal

7. Renewal Failure

register_calendar_webhook() raises → log error → still return 200

8. Redis Errors

Redis SET fails → log → continue → return 200

9. Token Refresh Integration

If token expired → ensure token is refreshed during renewal

Use mocks for Redis + httpx + DB.

6. Technical Constraints

All functions must be async

No Celery, no background tasks

No event parsing

No DB event writes

No conflict detection

No run_focus_mode() logic

Use calendar_id = "primary"

All tokens remain encrypted at rest

No token info in logs

Always return 200 OK

Logic in logic_webhook.py, NOT the router

7. Success Criteria
System behavior must satisfy:

Webhook notifications are idempotent

needs_sync flag set only on first-time events

Renewal triggered automatically when expiring

Renewal throttled (max once per 24h)

Renewal failures do not break handler

No Celery involved

Webhook pipeline is stable for production

This increment prepares the system for Increment 6 (event ingestion)

8. Known Limitations (Intentional)

These are expected and will be solved later:

No scheduled renewal (Celery Beat comes later)

No emergency polling

No event parsing

No conflict detection

No Focus Mode triggers

Partial token handling

Only primary calendar is supported

No HMAC validation yet

No multi-region Redis

Throttle logic is simplistic

needs_sync flag is temporary

No request_id tracing

Single-channel architecture

This is intentional.
Increment 5 is about reliability only, not functionality.

✔ Final Summary

Increment 5 delivers a rock-solid, production-safe webhook foundation:

Idempotent

Auto-renewing

Safe

Silent

Compliant

Stateless

Future-proof

This is exactly what the backend must have before event ingestion.