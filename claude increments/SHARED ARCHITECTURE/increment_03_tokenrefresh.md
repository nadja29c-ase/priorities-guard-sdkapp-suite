# Increment 3 – Token Refresh Automation  
### **Claude Implementation Version (Final, Unambiguous, Zero-Refactor)**

**Purpose:**  
Add Google OAuth token refresh so expired access tokens are automatically renewed before any Google Calendar API call.

This increment ONLY handles Google token refresh.  
**No Redis, no Celery, no distributed locks, no cache invalidation.**

---

# 1. Files to Modify (STRICT LIST)

Claude must modify **only** these two files:
backend/core/google_calendar.py
backend/apps/focused/logic.py

No other files may be created or touched.

---

# 2. New Function (backend/core/google_calendar.py)

Claude must implement exactly:

```python
async def refresh_access_token(
    http_client: httpx.AsyncClient,
    refresh_token: str
) -> dict:

## 2.1 Required constant
url = "https://oauth2.googleapis.com/token"


## 2.2 Required request payload & headers

data = {
    "client_id": settings.GOOGLE_CLIENT_ID,
    "client_secret": settings.GOOGLE_CLIENT_SECRET,
    "refresh_token": refresh_token,
    "grant_type": "refresh_token",
}

headers = {
    "User-Agent": f"FocusedApp/{settings.APP_VERSION} (+https://www.priority-guard.com)"
}

# 3. Required Retry Logic (NO ALTERATIONS)

Claude must implement:

max_retries = 3
base_delay = 1


Backoff formula:

delay = base_delay * (2 ** attempt) + random.uniform(0, 1)

## 3.1 Status code taxonomy (STRICT)
Status	Meaning	Retry?	Required Action
200	OK	n/a	return JSON
400	invalid_grant	❌ No retry	raise ValueError("Refresh token invalid")
403	quotaExceeded	❌ No retry	raise ValueError("API quota exceeded")
429	rateLimitExceeded	✅ Yes	respect Retry-After
500/503	Google server error	✅ Yes	retry
httpx.RequestError	network failure	✅ Yes	retry
3.2 Catch network failures with:
except httpx.RequestError:

**Do NOT attempt to use httpx.NetworkError.**

## 3.3 Final retry failure

Claude must raise after final attempt.
Upper layer will convert it into structured errors.

# 4. Integration (backend/apps/focused/logic.py)

Modify ONLY the Google-token portion of check_calendar_logic().

## 4.1 Expiration check (MANDATED)
now = datetime.now(timezone.utc)
if not connection.token_expires_at or connection.token_expires_at <= now:
    # refresh process

## ## 4.2 Refresh process (MANDATED SHAPE)
refresh_token = decrypt_token(connection.encrypted_refresh_token)

try:
    result = await refresh_access_token(http_client, refresh_token)
except ValueError as e:
    if str(e) == "Refresh token invalid":
        return {"error": "REFRESH_TOKEN_INVALID"}
    if str(e) == "API quota exceeded":
        return {"error": "API_QUOTA_EXCEEDED"}
    return {"error": "TOKEN_REFRESH_FAILED"}
except Exception:
    return {"error": "TOKEN_REFRESH_FAILED"}

## 4.3 Extract values (MANDATED)
new_access_token = result["access_token"]
expires_in = result["expires_in"]

## 4.4 Update DB (MANDATED)
now = datetime.now(timezone.utc)
connection.encrypted_access_token = encrypt_token(new_access_token)
connection.token_expires_at = now + timedelta(seconds=expires_in)
connection.updated_at = now
await session.commit()

Then continue with the existing calendar API call.

# 5. Logging Rules (STRICT)

- Claude must use existing logger and log ONLY:
- INFO: Access token expired, refreshing
- INFO: Token refresh successful
- WARNING: Retry attempt {attempt_number}
- ERROR: Token refresh failed: {reason}
- Never log:
- Access tokens
- Refresh tokens
- Encrypted tokens
- Response bodies

# 6. Structured Error Format (STRICT)

Claude MUST return errors in the existing format:

{"error": "REFRESH_TOKEN_INVALID"}

{"error": "API_QUOTA_EXCEEDED"}

{"error": "TOKEN_REFRESH_FAILED"}

Claude must NOT invent new formats or nested data.

# 7. Required Testing Scenarios

Claude must validate code against:

## 7.1 Manual expiry test

Forcing expiration:

UPDATE core_connections
SET token_expires_at = NOW() - INTERVAL '1 hour'
WHERE user_id = 'test_user';


Expected:

refresh occurs

DB updated

token_expires_at ≈ now + expires_in

calendar logic executes normally

## 7.2 400 invalid_grant

Return:

REFRESH_TOKEN_INVALID

## 7.3 403 quotaExceeded

Return:

API_QUOTA_EXCEEDED

## 7.4 429 rateLimitExceeded

retry using Retry-After header

after 3 failures → TOKEN_REFRESH_FAILED

# 8. Implementation Constraints (MUST FOLLOW)

Claude must NOT:
- refactor unrelated code
- create new files
- change encryption behavior
- modify core schema
- modify MCP server
- add Redis logic
- add background tasks
- modify other OAuth flows

Claude MUST:
- use existing encrypt_token() / decrypt_token()
- use existing http_client
- use existing SQLAlchemy session patterns
- use existing structured response format

# 9. Known Limitations (INTENTIONAL)

Claude must NOT implement:
- Redis locking
- proactive refresh
- Redis cache invalidation
- Celery scheduling
- multi-server coordination
- These are future increments.
____

**Final Instruction to Claude Code**

Implement EXACTLY the behavior described.
No refactoring.
No new abstractions.
Follow the prescribed signatures, error taxonomy, retry logic, DB updates, and logging exactly as written.