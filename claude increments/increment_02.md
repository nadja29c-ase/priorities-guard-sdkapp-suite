# Increment 2: MCP Server + check_calendar Tool

**Goal:** Build FastMCP server with check_calendar tool. Identify focus blocks in Google Calendar.

**Builds on:** Increment 1A (database) + 1B (OAuth)

**Status:** Functional increment - authentication and token refresh deferred to later increments.

---

## 🔥 CRITICAL IMPLEMENTATION NOTES

1. **user_id is hardcoded:** Set to "test_user" in this increment. Will be extracted from OAuth token in Increment 6.
2. **No token expiry checking:** Tool will fail if token expired. Refresh logic deferred to Increment 4.
3. **httpx only:** Do NOT use `google-api-python-client`. All API calls via httpx.
4. **FastMCP HTTP transport:** Server mounts at `/mcp` in FastAPI app (correct for ChatGPT Apps SDK).

---

## 1. Files to Create

```
backend/
├── apps/focused/
│   ├── mcp_server.py     # FastMCP server
│   └── tools.py          # check_calendar business logic
└── core/
    └── google_calendar.py  # Google Calendar API client
```

## 3. Google Calendar API Client (core/google_calendar.py)

### Requirements

**Reusable async client for Google Calendar API calls.**

### Function: fetch_events()

```python
async def fetch_events(
    http_client: httpx.AsyncClient,
    access_token: str,
    time_min: str,
    time_max: str,
    max_results: int = 20
) -> dict
```

**API Call:**
- Endpoint: `https://www.googleapis.com/calendar/v3/calendars/primary/events`
- Method: GET
- Query params:
  - `timeMin`: ISO8601 (e.g., "2024-01-15T00:00:00Z")
  - `timeMax`: ISO8601
  - `maxResults`: 1-50 (validated)
  - `singleEvents`: true
  - `orderBy`: "startTime"
- Headers:
  - `Authorization`: `Bearer {access_token}`
  - `User-Agent`: `FocusedApp/1.0 (+https://www.priority-guard.com)`

**Exponential backoff (Backend doc Section 4.3):**
```python
max_retries = 3
base_delay = 1  # second

for attempt in range(max_retries):
    try:
        response = await http_client.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:
            # Rate limit - respect Retry-After header
            retry_after = int(response.headers.get("Retry-After", base_delay * (2 ** attempt)))
            await asyncio.sleep(retry_after + random.uniform(0, 1))
        elif response.status_code == 401:
            # Invalid token - no retry
            raise ValueError("Invalid access token")
        elif response.status_code == 403:
            # Quota exceeded - no retry
            raise ValueError("API quota exceeded")
        else:
            response.raise_for_status()
            
    except (httpx.TimeoutException, httpx.NetworkError):
        if attempt == max_retries - 1:
            raise
        delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
        await asyncio.sleep(delay)
```

**Return format:**
```python
{
  "items": [
    {
      "id": "event_id",
      "summary": "Event title",
      "description": "Event description",
      "start": {"dateTime": "2024-01-15T09:00:00Z"},
      "end": {"dateTime": "2024-01-15T10:00:00Z"}
    }
  ]
}
```

**Error handling:**
- 401 → Raise clear error (token invalid)
- 403 → Raise clear error (quota exceeded)
- 429 → Retry with Retry-After header
- 500/503 → Retry with backoff
- Timeout/Network → Retry with backoff

---

## 4. Tool Business Logic (apps/focused/tools.py)

### Function: check_calendar_impl()

```python
async def check_calendar_impl(
    user_id: str,
    focus_keywords: list[str],
    time_start: str | None,
    time_end: str | None,
    max_results: int,
    session,  # DB session
    http_client: httpx.AsyncClient
) -> dict
```

**Flow:**

1. Fetch connection from DB (user_id + provider='google')
2. If not found → error `USER_NOT_CONNECTED`
3. Decrypt access_token
4. Calculate time_start/time_end defaults:
   - time_start: `datetime.now(timezone.utc)` if not provided
   - time_end: `time_start + 7 days` if not provided
5. Validate max_results (1-50)
6. Call `fetch_events()` from google_calendar.py
7. Match focus blocks via keyword matching
8. Return structured response

**Note:** Token expiry checking and refresh deferred to Increment 4.

**Focus block matching:**
```python
def matches_focus_keywords(event: dict, keywords: list[str]) -> str | None:
    """Return matched keyword or None."""
    summary = event.get("summary", "").lower()
    description = event.get("description", "").lower()
    
    for keyword in keywords:
        keyword_lower = keyword.lower()
        if keyword_lower in summary or keyword_lower in description:
            return keyword
    
    return None
```

**Return format:**
```python
{
  "focus_blocks": [
    {
      "id": "event_id",
      "summary": "Deep Work Session",
      "start": "2024-01-15T09:00:00Z",
      "end": "2024-01-15T11:00:00Z",
      "description": "Focus time for project",
      "matched_keyword": "Deep Work"
    }
  ],
  "conflicts": [],  # Empty in Increment 2
  "free_slots": [],  # Empty in Increment 2
  "total_events_scanned": 15,
  "focus_blocks_found": 3
}
```

---

## 5. MCP Server (apps/focused/mcp_server.py)

### Setup

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("focused-mcp")
```
(No APIRouter, no extra wrappers.)

**Transport:** HTTP (stateless)

### Tool: check_calendar

```python
# NOTE: Increment 2 uses hardcoded user_id="test_user"
# In Increment 6, user_id will be extracted from ChatGPT OAuth token
@mcp.tool()
async def check_calendar(
    focus_keywords: list[str],
    time_start: str = None,
    time_end: str = None,
    max_results: int = 20
) -> str:
    """
    Identify focus blocks in Google Calendar by matching keywords.
    
    Args:
        focus_keywords: Keywords to match (e.g., ["Deep Work", "Focus Time"])
        time_start: Start time (ISO8601), defaults to now
        time_end: End time (ISO8601), defaults to now + 7 days
        max_results: Max events to scan (1-50), defaults to 20
    
    Returns:
        JSON string with focus blocks
    """
    user_id = "test_user"
```

**CRITICAL:** user_id is hardcoded for testing. In production, it will be extracted from validated OAuth token.
**Note**: Inside MCP tools:
- DB: async with app.state.db_session() as session:
- HTTP client: client = app.state.http_client

**Implementation:**

1. Get DB session from app state
2. Get http_client from app state
3. Call `check_calendar_impl()` from tools.py
4. Return JSON string

**Error handling:**
```python
try:
    result = await check_calendar_impl(...)
    return json.dumps({"success": True, "data": result})
except ValueError as e:
    return json.dumps({
        "success": False,
        "error": {
            "code": "VALIDATION_ERROR",
            "message": str(e)
        }
    })
except Exception as e:
    logger.error("check_calendar failed", extra={"error": str(e)})
    return json.dumps({
        "success": False,
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "Failed to check calendar"
        }
    })
```

### Server lifecycle

```python
@mcp.server.on_initialize()
async def on_initialize():
    """Setup connections when server starts."""
    # Get DB engine and http_client from main app
    pass

@mcp.server.on_cleanup()
async def on_cleanup():
    """Cleanup when server shuts down."""
    pass
```

### Mount in main.py

**Update existing lifespan (from 1B):**
```python
from contextlib import asynccontextmanager
from backend.core.database import AsyncSessionLocal

@asynccontextmanager
async def lifespan(app):
    # Existing http_client from 1B
    app.state.http_client = httpx.AsyncClient(timeout=30.0)
    
    # Add for Increment 2
    # AsyncSessionLocal is a sessionmaker, use via: async with db_session() as session:
    app.state.db_session = AsyncSessionLocal
    
    yield
    
    await app.state.http_client.aclose()
```

---

## 6. Input Validation

**focus_keywords:**
- Must be non-empty list
- Each keyword: non-empty string

**time_start/time_end:**
- If provided: valid ISO8601 format
- time_end must be after time_start

**max_results:**
- Integer between 1-50
- Default: 20

---

## 7. Technical Constraints

- All functions async
- Use `httpx.AsyncClient` from app state
- Use the existing AsyncSessionLocal from backend.core.database (do NOT recreate sessionmakers).
- Exponential backoff on Google API
- User-Agent header on all requests
- Never log access tokens
- Include request_id in logs
- Structured JSON responses
- No print() statements
- Return empty arrays for conflicts/free_slots
- Only create these files:
    - backend/apps/focused/mcp_server.py
    - backend/apps/focused/tools.py
    - backend/core/google_calendar.py
    - Modify only: backend/main.py (lifespan block + mount)
---

## 8. Testing with MCP Inspector

**Install:**
```bash
npm install -g @modelcontextprotocol/inspector
```

**Start server:**
```bash
uvicorn backend.main:app --reload --port 8000
```

**Connect Inspector:**
```bash
npx @modelcontextprotocol/inspector http://localhost:8000/mcp
```

**Test flow:**
1. Inspector lists tools → verify check_calendar appears
2. First connect Google Calendar via OAuth (from 1B):
   - Visit `/auth/focused/google/start?user_id=test_user`
   - Complete OAuth flow
3. Call check_calendar:
   ```json
   {
     "focus_keywords": ["Deep Work", "Focus"],
     "time_start": "2024-01-15T00:00:00Z",
     "time_end": "2024-01-22T00:00:00Z",
     "max_results": 20
   }
   ```
4. Verify response has focus_blocks array
5. Test error cases:
   - No connection → USER_NOT_CONNECTED
   - Invalid time format → VALIDATION_ERROR

---

## 9. Logging Requirements

Log:
- "check_calendar called" (INFO) with keyword count
- "Fetching events from Google Calendar" (INFO)
- "Events fetched successfully" (INFO) with count
- "Focus blocks identified" (INFO) with count
- "Retry attempt" (WARNING) with attempt number
- Errors (ERROR) with context

**Never log:**
- Access tokens (encrypted or decrypted)
- Full event content

**Always include:** request_id

---

## 10. Success Criteria

✅ MCP server mounted at `/mcp`  
✅ check_calendar tool listed in Inspector  
✅ Tool fetches user's token from DB  
✅ Tool calls Google Calendar API  
✅ Exponential backoff works  
✅ User-Agent header present  
✅ Focus blocks identified correctly  
✅ Case-insensitive keyword matching  
✅ Empty conflicts/free_slots arrays  
✅ Structured error responses  
✅ No tokens in logs  
✅ All operations async  

---

## 11. Out of Scope

- ❌ Conflict detection logic
- ❌ Free slot analysis 
- ❌ Token refresh automation 
- ❌ Webhooks 
- ❌ ChatGPT OAuth provider 
- ❌ Apple Shortcuts integration 
- ❌ No inbound OAuth
- ❌ No Redis; No Celery

---

## 12. Error Codes

- `USER_NOT_CONNECTED` - No Google Calendar connected
- `VALIDATION_ERROR` - Invalid input parameters
- `API_ERROR` - Google Calendar API error
- `RATE_LIMITED` - API rate limit hit
- `QUOTA_EXCEEDED` - API quota exceeded
- `INTERNAL_ERROR` - Unexpected server error

**Note:** Token expiration handling deferred.

