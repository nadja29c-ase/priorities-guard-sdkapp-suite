Increment 7B: Authorization Code Flow + PKCE + Scopes
Goal: Complete OAuth 2.1 authorization with PKCE, scope validation, token exchange, refresh rotation, revocation, and client registration.

Deliverables
1. Authorization Endpoint
GET /oauth/focused/authorize
Query params:

response_type=code (required)
client_id (required)
redirect_uri (required, must be in client's registered array)
code_challenge (required, SHA256 hash)
code_challenge_method=S256 (required)
scope (required, space-separated)
state, nonce (optional)

Process:
python1. Validate client_id exists in core_connections 
   WHERE connection_type='oauth_provider'
2. Validate redirect_uri IN client.redirect_uris (array field)
3. Validate scopes (only: focused.read, focused.write, focused.notify)
4. Generate auth_context_id = uuid4()
5. Store in Redis: oauth:auth:{auth_context_id}
   {
     "client_id": "...",
     "code_challenge": "...",
     "scope": "...",
     "state": "...",
     "nonce": "...",
     "redirect_uri": "...",
     "expires_at": now + 10min
   }
6. Render consent screen with auth_context_id
```

**Errors:**
- Invalid client_id → 401
- Invalid redirect_uri → 400
- Invalid scope → 400

---

### 2. Consent Screen
**Files:** 
- `backend/templates/oauth_consent_en.html`
- `backend/templates/oauth_consent_de.html`

**Requirements:**
- **WCAG 2.1 AA:** Color contrast ≥4.5:1, keyboard navigation, ARIA labels
- **CSP:** `<meta http-equiv="Content-Security-Policy" content="default-src 'self'; style-src 'unsafe-inline'">`
- **Mobile responsive:** 320px-1920px
- **No external CDNs:** All CSS inline

**Content:**
```
App: Focused (Priority Guardian)
Permissions requested:
- focused.read: View focus patterns and calendar sync status
- focused.write: Activate Focus Mode and manage settings
- focused.notify: Send notifications

Privacy Policy: https://www.priority-guard.com/privacy
[Allow] [Deny]
POST /oauth/focused/consent
pythonif action == "allow":
    1. Load auth context from Redis
    2. Generate authorization code (cryptographically random, 128 chars)
    3. Store in oauth_authorization_codes:
       - code, user_id, client_id
       - code_challenge, scope
       - redirect_uri, state, nonce
       - expires_at = now + 10min
    4. Redirect: {redirect_uri}?code={code}&state={state}
    
elif action == "deny":
    Redirect: {redirect_uri}?error=access_denied&state={state}

3. Token Endpoint
POST /oauth/focused/token
Authorization Code Grant
json{
  "grant_type": "authorization_code",
  "code": "...",
  "code_verifier": "...",
  "client_id": "...",
  "redirect_uri": "..."
}
Validation (fail-fast):
python1. Load code from DB
2. Check not expired (10min)
3. Check not used
4. PKCE: SHA256(code_verifier) == code.code_challenge
5. client_id matches
6. redirect_uri matches
Success:
python1. Mark code.used = True
2. Create access token:
   jwt = create_jwt({
     "sub": str(user_id),
     "aud": settings.OAUTH_ISSUER,
     "iss": settings.OAUTH_ISSUER,
     "exp": now + 3600,
     "iat": now,
     "jti": uuid4(),
     "scope": code.scope,
     "client_id": client_id
   })
   
3. Create refresh token:
   refresh_token = secrets.token_urlsafe(64)
   
4. Store in oauth_access_tokens:
   - jti (PK)
   - user_id, client_id, scope
   - expires_at, refresh_token_enc
   - revoked=False, last_used_at=now
   
5. Return:
   {
     "access_token": jwt,
     "refresh_token": refresh_token,
     "token_type": "Bearer",
     "expires_in": 3600,
     "scope": code.scope
   }
Refresh Token Grant
json{
  "grant_type": "refresh_token",
  "refresh_token": "...",
  "client_id": "..."
}
Process:
python1. Find token in oauth_access_tokens by refresh_token_enc (decrypt + match)
2. Check not expired (30 days)
3. Check not revoked
4. Check client_id matches

5. Revoke old tokens (cascade):
   - Mark old access token revoked=True
   - Mark old refresh token revoked=True
   
6. Issue new tokens (same scope)
7. Return new access_token + new refresh_token

4. Revocation Endpoint
POST /oauth/focused/revoke
json{
  "token": "...",
  "client_id": "..."
}
Process:
python1. Identify token type:
   - If JWT → parse jti → find by jti
   - If opaque → decrypt → find by refresh_token
   
2. Mark revoked=True, revoked_at=now

3. If refresh token → cascade revoke all access tokens with same refresh_token

4. Always return 200 (per RFC 7009)

5. Client Registration
POST /oauth/focused/register
json{
  "redirect_uris": ["https://chatgpt.com/callback"],
  "client_name": "ChatGPT",
  "grant_types": ["authorization_code", "refresh_token"]
}
Response:
json{
  "client_id": "focused-client-{uuid}",
  "client_secret": "{generated}",
  "redirect_uris": ["https://chatgpt.com/callback"],
  "scope": "focused.read focused.write focused.notify"
}
Store in core_connections:
pythonCoreConnection(
    user_id=None,  # Not user-specific
    provider="chatgpt",
    connection_type="oauth_provider",
    client_id=client_id,
    client_secret_enc=encrypt(client_secret),
    redirect_uris=request.redirect_uris,  # ARRAY field
    scopes="focused.read focused.write focused.notify"
)

6. Backend Token Validation
NEW FILE: backend/core/oauth_logic.py
pythonasync def validate_access_token(jti: str, db: AsyncSession) -> OAuthAccessToken:
    """
    Validates access token by JTI.
    
    Checks:
    1. Token exists
    2. Not expired
    3. Not revoked
    
    Updates last_used_at on success.
    """
    token = await db.get(OAuthAccessToken, jti)
    
    if not token:
        raise InvalidTokenError("Token not found")
    
    if token.expires_at < datetime.now(UTC):
        raise InvalidTokenError("Token expired")
    
    if token.revoked:
        raise InvalidTokenError("Token revoked")
    
    # Track usage
    token.last_used_at = datetime.now(UTC)
    await db.commit()
    
    return token
Call from all backend endpoints:
python@router.post("/api/focused/sync_calendar")
async def sync_calendar(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
):
    # Parse Authorization header
    jti = parse_jwt(authorization)["jti"]
    
    # Validate token (real-time revocation check)
    token = await validate_access_token(jti, db)
    user_id = token.user_id
    
    # Execute logic...
```

---

### 7. Rate Limiting
**Keys (Redis):**
```
ratelimit:oauth:authorize:{ip}              (20/min)
ratelimit:oauth:token:{client_id}:{ip}      (5/min)
ratelimit:oauth:revoke:{client_id}:{ip}     (10/min)
ratelimit:oauth:register:{ip}               (10/min)
Implementation:
pythonasync def check_rate_limit(key: str, limit: int, window: int = 60):
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window)
    
    if count > limit:
        raise RateLimitExceeded(retry_after=window)

8. Cleanup Job
NEW: backend/jobs/oauth_cleanup.py
python@celery_app.task
def cleanup_expired_oauth_codes():
    """Delete authorization codes older than 10 minutes."""
    with Session() as db:
        db.query(OAuthAuthorizationCode).filter(
            OAuthAuthorizationCode.expires_at < datetime.now(UTC)
        ).delete()
        db.commit()

# Schedule: every 15 minutes

Database Changes
Modify core_connections:
python# Add redirect_uris array field
redirect_uris = Column(ARRAY(String), nullable=True, 
                      comment="Allowed redirect URIs for OAuth clients")
Migration:
python# Add column
op.add_column('core_connections', 
    sa.Column('redirect_uris', postgresql.ARRAY(sa.String()), nullable=True)
)

# Set default for existing ChatGPT connections
op.execute("""
    UPDATE core_connections 
    SET redirect_uris = ARRAY['https://chatgpt.com/callback']
    WHERE connection_type = 'oauth_provider'
""")
Modify oauth_access_tokens:
python# Add last_used_at tracking
last_used_at = Column(DateTime(timezone=True), nullable=True,
                     comment="Last time token was validated")
Add index:
sqlCREATE INDEX idx_oauth_access_tokens_last_used 
ON oauth_access_tokens(last_used_at);

Security Requirements
PKCE:

Reject code_challenge_method=plain
Reject missing code_verifier
Store SHA256(verifier) only

Scopes:

Whitelist: focused.read, focused.write, focused.notify
Reject unknown scopes
No scope escalation

Tokens:

Authorization code: 10min TTL, single-use
Access token: 1hr TTL, RS256 signed
Refresh token: 30d TTL, encrypted, rotated on use
All timestamps: UTC

Rate limits:

Per endpoint
Composite keys (IP + client_id where applicable)
Return 429 with Retry-After header

Revocation:

Cascade delete (refresh → all access tokens)
Always return 200 (don't leak token existence)


Error Responses
OAuth errors (per RFC 6749):
json{
  "error": "invalid_request|invalid_grant|invalid_client|unsupported_grant_type|access_denied",
  "error_description": "Human-readable message"
}
```

**HTTP status codes:**
- 400: Bad request (invalid params)
- 401: Invalid client/token
- 403: Forbidden (scope mismatch)
- 429: Rate limit exceeded

---

## File Structure
```
backend/
├── templates/
│   ├── oauth_consent_en.html          # NEW
│   └── oauth_consent_de.html          # NEW
├── apps/focused/
│   └── oauth_routes.py                # MODIFY: add 5 endpoints
├── core/
│   ├── oauth_logic.py                 # NEW: validation helpers
│   ├── rate_limit.py                  # NEW: Redis counters
│   └── models.py                      # MODIFY: add redirect_uris
└── jobs/
    └── oauth_cleanup.py               # NEW: Celery task

Success Criteria
Automated tests (50+ scenarios):

Valid end-to-end flow
PKCE mismatch → 401
Expired code → 401
Code reuse → 401
Invalid scope → 400
Multiple redirect_uri validation
Refresh rotation + old token revoked
Revocation cascades
Rate limits enforced
Client registration works
Backend revocation check blocks revoked JTI

Manual validation:

Browser: authorize → consent → code redirect
Token exchange with PKCE → JWT + refresh
Parse JWT at jwt.io → claims correct
Refresh exchange → new tokens, old revoked
Revoke token → backend rejects on next use
Rate limit: 6th token request → 429


Known Limitations (7B)

✅ No MCP integration (7D)
✅ No correlation ID logging (7C)
✅ Consent screen: basic styling (production polish later)
✅ No token introspection endpoint
✅ No JWKS rotation yet


Time estimate: 4-5 days
Next: 7C (correlation IDs, structured logging), 7D (MCP validation)RetryClaude can make mistakes. Please double-check responses.