# Increment 1B: Google OAuth Flow (Production-Ready)

## 🔥 CRITICAL IMPLEMENTATION RULES

**Claude MUST follow these:**

1. All functions MUST be async
2. Never use `Flow.fetch_token()` — use `httpx.AsyncClient` only
3. Do NOT create new AsyncClients in `google_oauth.py` — use `request.app.state.http_client`
4. Scopes stored as PostgreSQL ARRAY (`list[str]`), never comma-separated strings
5. `cleanup_expired_states()` only called in `/start` endpoint
6. `user_id` is temporary query parameter — no auth logic yet

---

## Goal

Implement Google OAuth flow for Focused app. User connects Google Calendar, tokens stored encrypted in DB.

**Builds on:** Increment 1A (database, encryption, models exist)

---

## 1. Files to Create

```
backend/
├── core/
│   └── google_oauth.py
└── alembic/versions/
    └── 002_create_oauth_state.py
```

**Modify:**
- `backend/apps/focused/router.py` — Add OAuth endpoints
- `backend/core/config.py` — Add Google OAuth settings
- `backend/core/models.py` — Add OAuthState model
- `backend/main.py` — Add httpx lifespan

---

## 2. Dependencies

Add to `pyproject.toml`:

```toml
google-auth-oauthlib = "^1.2.1"
httpx = "^0.28.1"
```

---

## 3. Config (core/config.py)

Add to Settings:

```python
GOOGLE_CLIENT_ID: str
GOOGLE_CLIENT_SECRET: str
GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/focused/google/callback"
```

Update `.env`:

```
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/focused/google/callback
```

---

## 4. OAuth State Model (core/models.py)

Create table:

```sql
state: VARCHAR(255) PRIMARY KEY
created_at: TIMESTAMPTZ NOT NULL DEFAULT NOW()
expires_at: TIMESTAMPTZ NOT NULL

INDEX idx_oauth_state_expires ON expires_at
```

**CRITICAL:**
- NO `user_id` column
- State is session-scoped, not user-scoped
- Single-use (deleted after verification)
- 10-minute expiration

---

## 5. Migration (002_create_oauth_state.py)

Must include:
- Table creation
- Expiration index
- Schema only (NO cleanup logic)

```bash
alembic revision --autogenerate -m "create oauth_state"
alembic upgrade head
```

---

## 6. OAuth Module (core/google_oauth.py)

### State Management Functions

**store_state(session, state: str)**
- Cleanup expired states first
- Insert state with `expires_at = NOW() + 10 minutes`
- Async DB operation

**verify_and_consume_state(session, state: str) -> bool**
- Check exists and not expired
- Delete state (single-use)
- Return True if valid
- Async DB operation

**cleanup_expired_states(session)**
- `DELETE WHERE expires_at < NOW()`
- Called only in `/start` endpoint

### OAuth Flow Functions

**generate_auth_url() -> tuple[str, str]**

Use `google_auth_oauthlib.flow.Flow` ONLY for URL generation:
- NO network calls (safe in async)
- Scope: `https://www.googleapis.com/auth/calendar.readonly`
- `access_type="offline"`
- `prompt="consent"`
- `include_granted_scopes="true"`
- Return: (auth_url, state)

**exchange_code(code: str, http_client: httpx.AsyncClient) -> dict**

**CRITICAL:** Use httpx ONLY, never `Flow.fetch_token()`

POST to `https://oauth2.googleapis.com/token`:
```python
{
  "code": code,
  "client_id": settings.GOOGLE_CLIENT_ID,
  "client_secret": settings.GOOGLE_CLIENT_SECRET,
  "redirect_uri": settings.GOOGLE_REDIRECT_URI,
  "grant_type": "authorization_code"
}
```

Exponential backoff:
- Max retries: 3
- Base delay: 1 second
- Jitter: `random.uniform(0, 1)`

Return:
```python
{
  "access_token": str,
  "refresh_token": str | None,
  "expires_in": int,
  "scopes": list[str]  # Parse from response["scope"].split()
}
```

---

## 7. OAuth Endpoints (apps/focused/router.py)

Both endpoints need `request: Request` parameter for `request.app.state.http_client`

### GET /auth/focused/google/start

Query param: `user_id`

Flow:
1. Cleanup expired states
2. Generate auth URL
3. Store state in DB
4. Log request with request_id
5. Return 307 redirect to Google

### GET /auth/focused/google/callback

Query params: `code`, `state`, `user_id`

Flow:
1. Validate all params present
2. Verify and consume state (CSRF check)
3. Exchange code using `request.app.state.http_client`
4. Calculate `token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)`
5. Encrypt both tokens
6. Upsert to `core_connections`:
   ```python
   from sqlalchemy.dialects.postgresql import insert
   
   stmt = insert(CoreConnection).values(...)
   stmt = stmt.on_conflict_do_update(
       constraint='uq_user_provider',
       set_={
           'encrypted_access_token': ...,
           'encrypted_refresh_token': ...,
           'token_expires_at': ...,
           'scopes': ...,
           'updated_at': datetime.utcnow()
       }
   )
   ```
7. Commit transaction
8. Return success

**Success response:**
```json
{
  "success": true,
  "data": {
    "connected": true,
    "provider": "google",
    "scopes": ["calendar.readonly"]
  }
}
```

**Error responses:**
- Missing params → `MISSING_PARAMETERS`
- Invalid/expired state → `INVALID_STATE`
- Exchange failed → `OAUTH_ERROR`
- DB error → `DATABASE_ERROR`

**Never log tokens.**

---

## 8. httpx Client via Lifespan (main.py)

Replace deprecated startup/shutdown events:

```python
from contextlib import asynccontextmanager
import httpx

@asynccontextmanager
async def lifespan(app):
    # Startup
    app.state.http_client = httpx.AsyncClient(timeout=30.0)
    
    yield
    
    # Shutdown
    await app.state.http_client.aclose()

app = FastAPI(lifespan=lifespan)
```

Access in endpoints: `client = request.app.state.http_client`

---

## 9. Technical Constraints

- All functions async
- No sync library calls
- httpx client from lifespan
- DB-backed OAuth state
- CSRF protection via state
- Single-use state deletion
- Postgres upsert pattern
- Exponential backoff on token exchange
- No token logging
- Scopes as `list[str]`
- Structured error responses
- `request_id` in all logs

---

## 10. Manual Testing

1. Start server
2. Visit: `http://localhost:8000/auth/focused/google/start?user_id=test_user`
3. Authorize with Google
4. Verify callback succeeds
5. Check DB:
   ```sql
   SELECT user_id, provider, scopes FROM core_connections;
   SELECT * FROM oauth_state;  -- Should be empty
   ```
6. Verify tokens encrypted
7. Test invalid state → `INVALID_STATE`
8. Test expired state → `INVALID_STATE`

---

## 11. Success Criteria

✅ `oauth_state` table exists  
✅ State stored, verified, consumed  
✅ Redirect flow works  
✅ Token exchange with backoff  
✅ Tokens encrypted and stored  
✅ Upsert prevents duplicates  
✅ No tokens in logs  
✅ Everything async  
✅ Scopes as PostgreSQL array  
✅ Expired states cleaned in `/start`  

---

## 12. Out of Scope

- ❌ Token refresh automation
- ❌ DELETE endpoint (Increment 1C)
- ❌ Calendar API calls
- ❌ MCP server
- ❌ User authentication

---

## References

- Backend doc Section 10.1A: Google OAuth
- Backend doc Section 4.3: Exponential backoff
- Google OAuth: https://developers.google.com/identity/protocols/oauth2