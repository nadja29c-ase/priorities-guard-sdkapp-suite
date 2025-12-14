GOAL

oauth_provider_router.py has become a monolith that mixes:

OAuth 2.1 logic

PKCE validation

Dynamic client registration

OIDC discovery

Token issuing

Token refresh

Token revocation

Consent UI rendering

Security headers

Rate limiting

DB access

Internal helpers

This MUST be broken down before Increment 8 and before security audits.

You keep behavior 100% identical.
You DO NOT change any endpoint paths.
You DO NOT change any signatures.
You DO NOT change any table usage.
You DO NOT change any OAuth semantics.

📦 TARGET DIRECTORY STRUCTURE (FINAL)

Claude must create exactly this structure:

backend/
  apps/
    focused/
      oauth/
        __init__.py

        discovery.py            # /.well-known/*
        authorize.py            # /oauth/focused/authorize (GET)
        consent_ui.py           # consent HTML render
        token_endpoint.py       # /oauth/focused/token
        register_client.py      # /oauth/focused/register
        revoke.py               # /oauth/focused/revoke
        jwks.py                 # /oauth/focused/jwks

        validators/
            __init__.py
            pkce.py             # PKCE verification
            token.py            # JWT validation helpers
            rate_limit.py       # rate limiting
            headers.py          # security headers
            client_metadata.py  # validation for register

        services/
            __init__.py
            token_service.py        # issue access + refresh tokens
            refresh_service.py      # refresh rotation
            authorization_service.py# create/validate auth codes
            revoke_service.py       # cascade revocation
            client_service.py       # dynamic client registration persistence
            jwks_service.py         # JWKS rotation + fetch
            consent_service.py      # UI state + consents

      routers/
        oauth_provider_router.py   # becomes a THIN orchestrator

🧨 TOP RISKS DURING REFACTOR (CLAUDE MUST PROTECT AGAINST)

Breaking PKCE validation → catastrophic ("invalid_grant" errors).

Breaking Dynamic Client Registration → ChatGPT SDK tools stop working.

Breaking Token Refresh → all MCP tools stop working after 1 hour.

Breaking revocation → compliance violation.

Changing any endpoint path → discovery documents break.

Error JSON shapes must remain EXACT to OpenAI + OAuth 2.1 requirements.

Must not accidentally log tokens (strict compliance requirement).

JWKS rotation must remain functional.

Rate limiting must stay untouched (Redis keys and formats).

CORS + headers must remain identical.

If Claude cannot guarantee any step, he must STOP and ask you before continuing.

🧱 PHASE 1 — PRE-REFACTOR STABILIZATION (MANDATORY)

Claude must follow these steps before touching code:

✔ 1. Create a test-protection branch

git checkout -b refactor-oauth-provider-safe

✔ 2. Search entire repo for:

oauth_provider_router

@router.get("/oauth/

@router.post("/oauth/

anything importing it.

Claude must generate a complete dependency map.

✔ 3. Write a small automated test:

A new test file:
tests/oauth/test_oauth_regression_baseline.py

It must include:

Authorization code flow → token exchange

Refresh token flow

Invalid PKCE → 400

Expired code → 400

Revoked tokens → 401

JWKS endpoint reachable

/.well-known/openid-configuration → valid JSON

Rate limiting triggers 429

/oauth/focused/register → returns client_id

If this is not present, refactor cannot proceed.

These tests ensure the refactor does not break OAuth.

🪓 PHASE 2 — CODE EXTRACTION ORDER (CRITICAL)

Claude must NOT extract everything at once.
He must follow this exact order to guarantee survivability:

Step 1 — Extract JWKS logic

File: jwks.py
Service: jwks_service.py

Why: JWKS is stateless and lowest risk.
Needed by all other modules.

Step 2 — Extract Discovery Endpoints

File: discovery.py

Endpoints:

/.well-known/openid-configuration

/.well-known/oauth-protected-resource

Why: Simple, no DB writes.

Step 3 — Extract PKCE, Headers, Rate-Limit Validators

Folder: validators/

Why: Stateless, pure utility, safest extraction.

Step 4 — Extract Client Registration

File: register_client.py
Service: client_service.py
Validator: validators/client_metadata.py

Why: Used only by ChatGPT runtime at app install.
Closing over secrets: MUST ENSURE AES encryption stays identical.

Step 5 — Extract Authorization Code Flow

File: authorize.py
Service: authorization_service.py

Content:

Brings together PKCE, state, nonce, generating auth code, storing in DB.

Consent UI redirection MUST stay intact.

Step 6 — Extract Consent Screen HTML

File: consent_ui.py
Service: consent_service.py

MUST keep CSP and no external JS (SDK restriction ).

Step 7 — Extract Token Endpoint

File: token_endpoint.py

Services:

token_service.py

refresh_service.py

Handles:

authorization_code grant

refresh_token grant

token rotation

expiration checks

Redis rate limits

This is the highest-risk part.
Claude must move this LAST among functional flows.

Step 8 — Extract Revocation

File: revoke.py
Service: revoke_service.py

Important:

Must cascade to:

oauth_access_tokens

refresh tokens

core_connections (if inbound ChatGPT)

Must NOT delete Google OAuth tokens (outbound) from other apps.

🧬 PHASE 3 — REBUILD THE ROUTER AS A THIN ORCHESTRATOR

After extraction:

oauth_provider_router.py must shrink from ~1500 lines to ~50-150 lines.

It should contain:

Imports of the new submodules

Router include statements

ZERO business logic

Example structure:

from fastapi import APIRouter
from .oauth.discovery import router as discovery_router
from .oauth.authorize import router as authorize_router
from .oauth.token_endpoint import router as token_router
from .oauth.register_client import router as register_router
from .oauth.revoke import router as revoke_router
from .oauth.consent_ui import router as consent_router
from .oauth.jwks import router as jwks_router

router = APIRouter(prefix="/oauth/focused")

router.include_router(discovery_router)
router.include_router(authorize_router)
router.include_router(token_router)
router.include_router(register_router)
router.include_router(revoke_router)
router.include_router(consent_router)
router.include_router(jwks_router)

🧪 PHASE 4 — REGRESSION TESTING

Claude must run:

pytest -q
pytest tests/oauth/test_oauth_regression_baseline.py
pytest tests/increment_7*
pytest tests/increment_6*


Specifically validate:

Authorization_code → token works

Refresh_token → new tokens returned

JWTs validate

JWKS paths still correct

Consent screen loads in HTML

All error shapes identical

Rate limits unchanged (429)

No additional logs containing tokens

If ANY test fails:
→ revert that module and fix before proceeding.

🛡 PHASE 5 — SECURITY + COMPLIANCE VALIDATION

Claude must check:

✔ Security headers preserved

From compliance master (CSP, HSTS, no external scripts) .

✔ Token non-logging rule enforced

Critical violation if missing:
“No access or refresh tokens may appear in logs.”

✔ PKCE works
✔ RS256 JWKS consistent
✔ Revocation cascade correct
✔ 1-hour access token TTL unchanged
✔ 30-day refresh token TTL unchanged
✔ Client registration rate limit intact
✔ Consent screen HTML:

No external CDNs

No forms

No localStorage (banned)

WCAG 2.1 AA

EN + DE versions

🔧 PHASE 6 — CLEANUP

Once stable:

Remove dead imports

Remove unused helper functions

Add docstrings so future apps (TaskScheduler, Decliner) can reuse the OAuth provider layer

Update architecture docs (optional)

📣 WHAT CLAUDE MUST OUTPUT TO YOU

After each extraction, Claude must send you:

Refactored module: <module_name>
Lines moved: <X>
New file(s): <list>
Tests passing: Yes/No
Notes:
- <any behavioral changes>
- <any discovered bugs>


If any behavior changes → STOP.

