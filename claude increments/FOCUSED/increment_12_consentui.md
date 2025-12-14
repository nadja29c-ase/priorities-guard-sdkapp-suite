# Increment #12: OAuth Consent UI Implementation

## Context

Priority Guardian's OAuth Provider is 90% complete. All backend logic exists (PKCE validation, token generation, JWKS, registration, revocation). The missing piece: `consent_ui.py` — the module that renders the consent screen and processes user Allow/Deny decisions.

Without this, ChatGPT cannot complete OAuth authorization. This blocks all real-world testing.

## Objective

Implement `/oauth/focused/authorize` (GET) and `/oauth/focused/consent` (POST) endpoints that:
1. Render the consent HTML template
2. Process Allow/Deny user decisions
3. Generate authorization codes and redirect to ChatGPT

## What Exists

```
backend/core/oauth_provider/
├── authorize.py          # Partial - needs to delegate to consent UI
├── consent_ui.py         # ❌ MISSING - this increment
├── discovery.py          # ✅ Complete
├── jwks.py              # ✅ Complete
├── register_client.py   # ✅ Complete
├── token_endpoint.py    # ✅ Complete
├── revoke.py            # ✅ Complete
├── services/            # ✅ Authorization code generation, PKCE validation
├── validators/          # ✅ Request validation
├── jwt/                 # ✅ JWT signing utilities
├── models.py            # ✅ Pydantic models
└── exceptions.py        # ✅ OAuth error handling

backend/templates/
└── oauth_consent_en.html  # ✅ Exists, WCAG compliant, CSP-safe
```

## Deliverables

### 0. Modify `backend/core/oauth_provider/authorize.py`

**Important:** `authorize.py` must delegate to `consent_ui.py` after initial parameter validation. Do NOT duplicate validation logic between the two modules.

Pattern:
- `authorize.py`: Initial request validation (params present, client_id valid, redirect_uri matches)
- `consent_ui.py`: User identity resolution (`login_hint` → user lookup), Redis context storage, template rendering, consent processing

If `authorize.py` currently handles the full flow, refactor it to call into `consent_ui.py` for the consent-specific logic.

### 1. `backend/core/oauth_provider/consent_ui.py`

**GET `/oauth/focused/authorize`**
- Validate required params: `client_id`, `redirect_uri`, `response_type=code`, `scope`, `state`, `code_challenge`, `code_challenge_method=S256`, `login_hint`
- Validate `client_id` exists in the OAuth provider's client registry (the table used in dynamic client registration, e.g., `oauth_clients` or `oauth_registered_clients`)
- Validate `redirect_uri` matches registered redirect URIs
- **User Identity via `login_hint` (REQUIRED):**
  - `login_hint` parameter contains the ChatGPT user ID
  - If `login_hint` is missing → return OAuth error: `error=login_required&error_description=login_hint+parameter+required`
  - Look up user by `login_hint` in `core_users.chatgpt_user_id`
  - If user doesn't exist → create new user record in `core_users`
  - Store the resolved internal `user_id` (UUID) in auth context
  - **Never accept `user_id` directly from query parameters** (security: prevents impersonation)
- Store auth context in Redis with 10-minute TTL:
  ```python
  auth_context = {
      "client_id": ...,
      "redirect_uri": ...,
      "scope": ...,
      "state": ...,
      "code_challenge": ...,
      "code_challenge_method": ...,
      "user_id": str(user.id),  # Internal UUID from database lookup, NOT from query param
      "chatgpt_user_id": login_hint  # Original ChatGPT user ID for audit
  }
  ```
- Generate `auth_context_id` (UUID)
- Key: `oauth:auth_context:{auth_context_id}`
- Render `oauth_consent_en.html` or `oauth_consent_de.html` based on `Accept-Language` header
- Pass `auth_context_id` to template

**POST `/oauth/focused/consent`**
- Read form data: `auth_context_id`, `action` (allow/deny)
- Retrieve auth context from Redis
- If not found or expired → error redirect
- If `action=deny`:
  - Redirect to `redirect_uri?error=access_denied&error_description=User+denied+access&state={state}`
- If `action=allow`:
  - Generate authorization code using existing service (`services/authorization.py` or similar)
  - Store code with PKCE challenge (existing logic)
  - Delete auth context from Redis (single-use)
  - Redirect to `redirect_uri?code={code}&state={state}`

### 2. `backend/templates/oauth_consent_de.html`

Copy `oauth_consent_en.html` with German translations:
- "Permissions Requested" → "Angeforderte Berechtigungen"
- "View focus patterns and calendar sync status" → "Fokus-Muster und Kalender-Synchronisierungsstatus anzeigen"
- "Activate Focus Mode and manage settings" → "Fokus-Modus aktivieren und Einstellungen verwalten"
- "Send notifications" → "Benachrichtigungen senden"
- "By authorizing this application, you agree to our" → "Mit der Autorisierung dieser Anwendung stimmen Sie unserer"
- "Privacy Policy" → "Datenschutzrichtlinie"
- "Allow" → "Erlauben"
- "Deny" → "Ablehnen"
- Update `lang="en"` to `lang="de"`

### 3. Jinja2 Configuration

In `backend/main.py` or appropriate location:
```python
from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory="backend/templates")
```

Pass `templates` to consent_ui router or use dependency injection.

### 4. Language Detection

Simple logic based on `Accept-Language` header:
- If starts with "de" → German template
- Otherwise → English template

## Error Handling

Use existing `backend/core/oauth_provider/exceptions.py` patterns:
- `InvalidClientError` → redirect with `error=invalid_client`
- `InvalidRequestError` → redirect with `error=invalid_request`
- `AccessDeniedError` → redirect with `error=access_denied`

All error redirects must include `state` parameter if provided.

## Security Requirements

### User Identity via `login_hint` (Critical)

**Problem:** Priority Guardian backend has no user authentication system. ChatGPT drives the OAuth flow and knows who the user is, but the backend doesn't.

**Solution:** ChatGPT passes `login_hint` parameter containing the ChatGPT user ID. This is standard OAuth 2.1 behavior.

**Why NOT query param `user_id`:**
- Attack: Attacker crafts `/authorize?user_id=victim_id` → gets tokens for victim
- `login_hint` is expected from the OAuth client (ChatGPT), not arbitrary users
- Combined with `client_id` validation (only registered clients), this ensures only legitimate ChatGPT clients can initiate authorization

**Implementation:**
1. Require `login_hint` parameter (return `login_required` error if missing)
2. Validate `client_id` is registered (from dynamic client registration table)
3. Look up or create user by `login_hint` → `core_users.chatgpt_user_id`
4. Store internal `user_id` (UUID) in Redis auth context
5. Never expose or accept raw `user_id` in URL parameters

### Other Security Requirements

- Auth context TTL: 10 minutes (prevents replay)
- Single-use auth context (delete from Redis after use)
- Validate redirect_uri matches registered URIs exactly
- No tokens or secrets in logs (existing `scrub_sensitive_data` pattern)
- CSRF protection via `auth_context_id` (tied to specific authorization request)

## Rate Limiting

Apply rate limiting to `GET /oauth/focused/authorize`:
- Limit: 20 requests/minute per `login_hint` (ChatGPT user ID)
- Fallback to IP-based limiting if `login_hint` not yet validated
- On exceed: Return 429 Too Many Requests with 5-minute temporary lock
- Use existing `rate_limit.py` patterns (Redis counters with sliding window)
- Key format: `ratelimit:oauth_authorize:{chatgpt_user_id}` or `ratelimit:oauth_authorize:ip:{ip_address}`

## Testing

Unit tests in `tests/core/oauth_provider/test_consent_ui.py`:
1. GET /authorize with valid params (including login_hint) → renders consent HTML
2. GET /authorize with missing login_hint → error response `login_required`
3. GET /authorize with missing other params → error response
4. GET /authorize with invalid client_id → error redirect
5. GET /authorize with login_hint for new user → creates user, renders consent
6. GET /authorize with login_hint for existing user → finds user, renders consent
7. POST /consent with action=allow → generates code, redirects
8. POST /consent with action=deny → error redirect with access_denied
9. POST /consent with expired context → error redirect
10. POST /consent with invalid context_id → error redirect
11. Language detection: Accept-Language: de → German template
12. Language detection: Accept-Language: en-US → English template
13. Rate limiting: 21 requests in 1 minute → 429 response

## Integration Points

- Redis client: `backend/core/redis_client.py`
- Authorization code generation: Look in `services/` for existing logic
- PKCE storage: Existing pattern in token_endpoint.py
- Rate limiting: Apply existing rate limit decorator if available
- Structured logging: Use existing `structlog` patterns with correlation IDs

## Out of Scope

- Privacy policy page content
- notify_user() tool
- Deployment configuration

## Success Criteria

1. `GET /oauth/focused/authorize?client_id=...&redirect_uri=...&response_type=code&scope=focused.read&state=abc&code_challenge=...&code_challenge_method=S256&login_hint=chatgpt_user_123` returns rendered consent HTML
2. `GET /oauth/focused/authorize` without `login_hint` → returns `error=login_required`
3. Allow button → redirects to `redirect_uri?code=...&state=abc`
4. Deny button → redirects to `redirect_uri?error=access_denied&state=abc`
5. German template served when `Accept-Language: de`
6. New users created in `core_users` when `login_hint` references unknown ChatGPT user
7. All tests pass
8. No regressions in existing OAuth tests

# Integration tests
Increment 12 Integration Tests

Write integration tests for the full OAuth Authorization → Consent → Redirect flow using FastAPI’s async TestClient, test Redis, and test database.

Scope

Test Increment 12 end-to-end behavior inside the backend (NOT ChatGPT E2E).
Target modules:

authorize.py

consent_ui.py

authorization_service.py

consent_service.py

Redis auth context handling

Template rendering (EN/DE)

Rate limiting (login_hint & IP fallback)

Test File

Create:

tests/integration/test_increment_12_oauth_flow.py

Fixtures

Use existing fixtures or create minimal ones:

client (FastAPI TestClient or AsyncClient)

db_session

redis_test_client

override settings for:

redis URL

template directory

rate limit window (shortened for tests)

Integration Tests to Implement
1. Full Allow Flow

Call GET /oauth/focused/authorize?client_id=...&login_hint=user123&...

Expect 200 + rendered HTML

Extract auth_context_id from HTML

POST /oauth/focused/consent with action=allow

Expect redirect with code and state

Validate:

auth context deleted from Redis

authorization code stored correctly with PKCE fields

2. Full Deny Flow

Same as above, but POST action=deny

Expect redirect:
?error=access_denied&state=XYZ

3. Unknown User Creation

Use new login_hint

Call /authorize

Assert CoreUser row created (chatgpt_user_id matches)

Assert user_id stored in Redis context

4. Expired/Invalid auth_context_id

POST /consent with invalid ID

Expect error redirect with error=invalid_request or matching error handler behavior

5. Redirect URI Validation (Danger Case)

Call /authorize with unregistered redirect_uri

Expect OAuth error redirect: error=invalid_request

6. Language Detection

Accept-Language: de → returns DE template

Accept-Language: en-US → returns EN template

7. Rate Limiting

Case A (login_hint-based):

21 calls to /authorize with same login_hint inside 60s

Expect 429 on last request

Case B (IP fallback):

Call /authorize without login_hint

Rate limit by IP (short test window)

8. State Parameter Preservation

Provide state=abc123

Allow → final redirect contains &state=abc123

Deny → final redirect contains &state=abc123

9. PKCE Fields Stored Correctly

After /authorize, read Redis context

Validate:

code_challenge

code_challenge_method == “S256”

scope, client_id, redirect_uri

Not Required

Token endpoint testing (already covered in earlier increment)

Live ChatGPT environment tests

UI screenshots or rendering snapshots

Success Criteria

All integration tests pass:

allow flow end-to-end

deny flow end-to-end

language selection

user creation

PKCE correctness

state propagation

rate limits enforced

redirect URIs validated

no regressions to earlier OAuth logic