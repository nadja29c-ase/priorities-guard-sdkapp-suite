Increment 7A — OAuth Provider Skeleton
Foundation for ChatGPT OAuth 2.1 provider (Discovery, JWKS, DB tables, placeholders)
🎯 Goal

Create the minimal working OAuth Provider foundation so the system can:

expose discovery endpoints

expose JWKS

generate and sign dummy JWTs

provide placeholder /authorize, /token, /register endpoints

migrate required DB tables

No PKCE, no scopes, no consent, no real authorization yet.
This sets up everything 7B will build on.

📁 Deliverables
1. RSA Key Management

File: backend/core/crypto.py

Requirements

Generate RSA-2048 key pair on first startup

Private key never exposed via API

Public key exposed via JWKS

Key stored in AES-256 encrypted form if persisted

Support multiple keys (rotation-ready)

Each key must contain a stable kid (e.g., "focused-2025-01")

Helpers to implement
def sign_jwt(payload: dict, kid: str) -> str:
    """Signs RS256 JWT using private key identified by kid."""

def get_current_jwks() -> dict:
    """Returns JWKS with all active public keys."""

Security Rules

No key material in logs

Log only: "Generated RSA keypair with kid=focused-XXXX"

Private key stored encrypted if persisted (AES-256)

Keypair must be loaded from environment on startup (or recreated if missing)

JWKS must include only public key components (n, e, kty, alg, use, kid)

2. Discovery Endpoints

File: backend/apps/focused/oauth_routes.py

Endpoint: GET /.well-known/openid-configuration

Return exactly:

{
  "issuer": "https://www.priority-guard.com",
  "authorization_endpoint": "https://www.priority-guard.com/oauth/focused/authorize",
  "token_endpoint": "https://www.priority-guard.com/oauth/focused/token",
  "jwks_uri": "https://www.priority-guard.com/oauth/focused/jwks",
  "registration_endpoint": "https://www.priority-guard.com/oauth/focused/register",
  "scopes_supported": ["focused.read", "focused.write", "focused.notify"],
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code", "refresh_token"],
  "code_challenge_methods_supported": ["S256"],
  "token_endpoint_auth_methods_supported": ["none"]
}

Endpoint: GET /.well-known/oauth-protected-resource

Return:

{
  "resource": "https://www.priority-guard.com/mcp/focused",
  "authorization_servers": ["https://www.priority-guard.com"],
  "scopes": {
    "focused.read": "Read calendar sync status and focus analytics",
    "focused.write": "Activate Focus Mode and modify settings",
    "focused.notify": "Send push notifications"
  }
}

3. JWKS Endpoint
Endpoint: GET /oauth/focused/jwks

Must return:

{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "focused-2025-01",
      "alg": "RS256",
      "n": "<base64url_modulus>",
      "e": "AQAB"
    }
  ]
}

Requirements

JWKS cached with 24h TTL

JWKS refreshed automatically on key rotation

JWKS must be a valid OIDC JWKS document

4. Database Tables

Migration: alembic revision -m "add_oauth_tables"

Table: oauth_authorization_codes
class OAuthAuthorizationCode(Base):
    __tablename__ = "oauth_authorization_codes"
    
    code = Column(String(128), primary_key=True)
    user_id = Column(UUID, ForeignKey("core_users.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id = Column(String(255), nullable=False)

    code_challenge = Column(String(255), nullable=False)
    code_challenge_method = Column(String(10), nullable=False)  # always 'S256'

    redirect_uri = Column(String(512), nullable=False)
    scope = Column(String(512), nullable=False)
    state = Column(String(255), nullable=True)
    nonce = Column(String(255), nullable=True)

    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

Indices

(user_id) for cascade delete

(expires_at) for cleanup job

Table: oauth_access_tokens
class OAuthAccessToken(Base):
    __tablename__ = "oauth_access_tokens"

    jti = Column(String(128), primary_key=True)
    user_id = Column(UUID, ForeignKey("core_users.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id = Column(String(255), nullable=False)
    scope = Column(String(512), nullable=False)
    token_type = Column(String(20), default="Bearer", nullable=False)

    expires_at = Column(DateTime(timezone=True), nullable=False)

    refresh_token_enc = Column(Text, nullable=True)
    refresh_token_expires_at = Column(DateTime(timezone=True), nullable=True)

    revoked = Column(Boolean, default=False, nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), nullable=True)

Indices

(user_id)

(jti)

(expires_at)

5. Static Placeholder Endpoints
GET /oauth/focused/authorize
<!DOCTYPE html>
<html>
<head><title>Focused - Authorize</title></head>
<body>
  <h1>OAuth Authorization</h1>
  <p>Placeholder - implement in 7B</p>
</body>
</html>

POST /oauth/focused/token

Returns dummy JWT:

async def token_endpoint():
    payload = {
        "sub": "dummy-user-id",
        "aud": "https://www.priority-guard.com",
        "iss": "https://www.priority-guard.com",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
        "jti": str(uuid4()),
        "scope": "focused.read focused.write"
    }
    jwt = sign_jwt(payload, kid="focused-2025-01")
    return {"access_token": jwt, "token_type": "Bearer", "expires_in": 3600}

POST /oauth/focused/register

Return static placeholder:

{
  "client_id": "focused-client-001",
  "client_secret": "auto-generated-secret",
  "scope": "focused.read focused.write"
}


Store in core_connections with connection_type='oauth_provider'.

6. JWT Helper Functions

File: backend/core/jwt_utils.py

Required:
def create_access_token(
    user_id: UUID,
    client_id: str,
    scope: str,
    expires_delta: timedelta = timedelta(hours=1)
) -> tuple[str, str]:
    """Creates signed JWT access token. Returns (token, jti)."""

def create_refresh_token() -> str:
    """Generates cryptographically random opaque refresh token."""

🧪 Success Criteria
Automated (pytest)

Discovery endpoints return valid JSON

JWKS endpoint returns correct RSA public key

Dummy token returns a valid RS256 JWT

Alembic migration applies correctly

Placeholder endpoints return HTTP 200

Manual tests

Visit /.well-known/openid-configuration

Visit /oauth/focused/jwks

Validate dummy JWT at jwt.io

Check DB tables created

⚠️ Limitations (Expected)

7A intentionally does NOT include:

PKCE

Authorization code creation

Consent screen logic

Scope enforcement

Rate limiting

User identity handling

Token refresh

Token revocation

Security checks

These are part of 7B and 7C.

🔥 Critical Claude Code Implementation Instructions

(These are the rules Claude Code MUST follow when implementing 7A.)

1. NEVER infer or create “helpful” abstractions

Claude must implement exactly the files, functions, and schemas specified.
No redesign.
No renaming.
No altering endpoint paths.

2. Keep Increment 7A self-contained

No PKCE logic.
No state creation.
No consent screen beyond static HTML.
No scope validation.
Anything beyond the spec belongs to 7B/7C and must be refused.

3. JWT MUST be RS256 signed using your private key

Use cryptography for RSA

Use python-jose or PyJWT for signing

Headers must contain correct "kid"

4. JWKS MUST contain only public components

If Claude includes private key values → reject and regenerate.

5. Do NOT try to implement token refresh

7A uses dummy tokens only.
Claude must not add refresh token logic, rotation, or lookups.

6. File placement must match exactly

Claude must create files exactly as specified:

backend/core/crypto.py
backend/core/jwt_utils.py
backend/apps/focused/oauth_routes.py
backend/core/oauth_models.py
alembic/versions/xxx_add_oauth_tables.py


Nothing else.

7. Code must run on first try

Claude must ensure imports work and each module is self-contained.

8. No optimization, no enhancements

Claude must not:

Introduce caching

Introduce key rotation

Introduce new fields

Modify DB schema

Use external libraries not already in project

Keep 7A minimal and aligned.

9. Return dummy tokens without validation

In /token, just return a signed JWT.
Real validation belongs to 7B.

10. Never leak private key data in logs or comments

Claude must not print or expose key material.

📦 Final File Structure for Increment 7A
backend/
├── core/
│   ├── crypto.py           # RSA key loading, JWKS, sign_jwt
│   ├── jwt_utils.py        # create_access_token, create_refresh_token
│   └── encryption.py       # existing AES-256-GCM helpers
├── apps/focused/
│   ├── oauth_routes.py     # discovery, authorize, token, register
│   └── models.py           # OAuth models
└── alembic/
    └── versions/
        └── xxx_add_oauth_tables.py
