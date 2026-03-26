Claude Code Briefing: MindSort AI OAuth Route Family (Final)
Before starting: Read OPERATIONS_PREDEPLOY.md and OPERATIONS_MIGRATIONS.md. No DB migrations required.
Risk contract (verified against actual code):

/oauth/pg/* — untouched
/.well-known/oauth-authorization-server (root, shared) — untouched, stays ["pg.access"]
SCOPES_SUPPORTED in shared discovery.py — untouched
settings.OAUTH_ISSUER = https://www.priority-guard.com — untouched, shared JWT issuer
JWKS signing key — untouched, shared across all apps
All existing PG routes and handlers — untouched

Purely additive.

Critical invariants (do not violate):

1. `authorization_servers: ["https://www.priority-guard.com/oauth/mindsort"]` — must be exact. One character wrong and ChatGPT falls back to PG's route.

2. `issuer: https://www.priority-guard.com` — must stay the shared root. If this ever becomes path-qualified, every JWT validation in every app breaks simultaneously.

Files to change — backend
1. New file: backend/core/oauth_provider/mindsort_discovery.py
python"""
MindSort AI OAuth Discovery Endpoints.

Per-app authorization server discovery for MindSort AI.
Mounted at /oauth/mindsort by oauth_provider_router.

Issuer: shared root domain (https://www.priority-guard.com) — same JWT signer.
Endpoints: /oauth/mindsort/* — app-specific.
Scopes: clarity.write only.

ChatGPT flow:
  mindsort.priority-guard.com/.well-known/oauth-protected-resource
  → authorization_servers: ["https://www.priority-guard.com/oauth/mindsort"]
  → www.priority-guard.com/oauth/mindsort/.well-known/oauth-authorization-server  ← this document
  → registration_endpoint: .../oauth/mindsort/register
  → DCR assigns clarity.write scope
  → MindSort consent screen shown
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.core.config import settings

router = APIRouter(tags=["oauth-provider"])

SCOPES_SUPPORTED_MINDSORT = ["clarity.write"]


def _mindsort_authorization_server_metadata() -> dict:
    return {
        "issuer": settings.OAUTH_ISSUER,  # DO NOT change per app — shared JWT issuer for all apps. Changing this breaks token validation across PG and MindSort AI.
        "authorization_endpoint": f"{settings.OAUTH_ISSUER}/oauth/mindsort/authorize",
        "token_endpoint": f"{settings.OAUTH_ISSUER}/oauth/mindsort/token",
        "jwks_uri": f"{settings.OAUTH_ISSUER}/oauth/mindsort/jwks",
        "registration_endpoint": f"{settings.OAUTH_ISSUER}/oauth/mindsort/register",
        "scopes_supported": SCOPES_SUPPORTED_MINDSORT,
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
    }


@router.get("/.well-known/oauth-authorization-server")
async def mindsort_oauth_authorization_server():
    return JSONResponse(_mindsort_authorization_server_metadata())


@router.get("/.well-known/openid-configuration")
async def mindsort_openid_configuration():
    return JSONResponse(_mindsort_authorization_server_metadata())
2. backend/core/routers/oauth_provider_router.py
Add import and mount with prefix:
pythonfrom backend.core.oauth_provider.mindsort_discovery import router as mindsort_discovery_router

# Add after existing router includes:
router.include_router(mindsort_discovery_router, prefix="/oauth/mindsort")
This makes www.priority-guard.com/oauth/mindsort/.well-known/oauth-authorization-server live — which is the URL ChatGPT will actually fetch.
3. backend/core/oauth_provider/register_client.py
Add constant and route:
pythonDEFAULT_SCOPES_MINDSORT = ["clarity.write"]

@router.post("/oauth/focused/register")
@router.post("/oauth/pg/register")
@router.post("/oauth/mindsort/register")
Add routing:
pythonif route_path == "/oauth/focused/register":
    default_scopes = DEFAULT_SCOPES_FOCUSED
elif route_path == "/oauth/mindsort/register":
    default_scopes = DEFAULT_SCOPES_MINDSORT
else:
    default_scopes = DEFAULT_SCOPES_PG
Expand validation superset — safe only because: (a) shared discovery.py SCOPES_SUPPORTED is untouched, (b) route defaults remain app-specific, (c) per-app discovery documents are separated:
python# Before
SUPPORTED_SCOPES = set(SCOPES_SUPPORTED)

# After — validation superset only, does not affect discovery output
SUPPORTED_SCOPES = set(SCOPES_SUPPORTED) | {"clarity.write"}
4. backend/core/oauth_provider/authorize.py
Add route decorator:
python@router.get("/oauth/focused/authorize", response_class=HTMLResponse)
@router.get("/oauth/pg/authorize", response_class=HTMLResponse)
@router.get("/oauth/mindsort/authorize", response_class=HTMLResponse)
Update clarity.write scope descriptions:
python"clarity.write": "Save and organize your MindSort AI boards.",
# DE:
"clarity.write": "Deine MindSort AI Boards speichern und organisieren.",
Update consent routing — rename Clarity branch to MindSort:
pythonif any(s.startswith("clarity.") for s in requested_scopes):
    template_name = f"oauth_consent_mindsort_{language}.html"
    client_name = "MindSort AI"
    display_scopes = {s for s in requested_scopes if s.startswith("clarity.")}
5. backend/core/oauth_provider/token_endpoint.py
Add route decorator only — no other changes:
python@router.post("/oauth/focused/token")
@router.post("/oauth/pg/token")
@router.post("/oauth/mindsort/token")
6. backend/core/oauth_provider/jwks.py
Add route decorator only:
python@router.get("/oauth/focused/jwks")
@router.get("/oauth/pg/jwks")
@router.get("/oauth/mindsort/jwks")
7. backend/core/oauth_provider/consent_ui.py
Add route decorator:
python@router.post("/oauth/focused/consent")
@router.post("/oauth/pg/consent")
@router.post("/oauth/mindsort/consent")
Update _derive_app_name_from_scopes:
pythondef _derive_app_name_from_scopes(scopes: list[str]) -> str:
    for scope in scopes:
        if scope.startswith("pg."):
            return "priority_guardian"
        if scope.startswith("clarity."):
            return "mindsort"
    return "focused"
8. backend/core/oauth_provider/revoke.py
Add route decorator only:
python@router.post("/oauth/focused/revoke")
@router.post("/oauth/pg/revoke")
@router.post("/oauth/mindsort/revoke")
9. New consent templates
backend/templates/oauth_consent_mindsort_en.html — copy from oauth_consent_clarity_en.html, two changes only:

purpose-sentence: "This app helps you sort your thoughts into clusters so you can find focus when you feel overwhelmed."
Form action: action="/oauth/mindsort/consent"

backend/templates/oauth_consent_mindsort_de.html — copy from oauth_consent_clarity_de.html, two changes only:

purpose-sentence: "Diese App hilft dir, deine Gedanken zu sortieren, damit du Fokus findest, wenn du dich überwältigt fühlst."
Form action: action="/oauth/mindsort/consent"


MindSort AI MCP server — code change
mcp_server/clarity/discovery.py — oauth_protected_resource() only:
pythonasync def oauth_protected_resource():
    return {
        "resource": f"{MCP_SERVER_URL}/mcp",
        "authorization_servers": [OAUTH_ISSUER_URL],  # ← was CLARITY_ISSUER
        "scopes_supported": SCOPES_SUPPORTED,
    }
```

`OAUTH_ISSUER_URL` is already imported. `CLARITY_ISSUER` stays in `openid_configuration()` and `oauth_authorization_server()` for the `issuer` field — do not change those.

After this code change deploys, update Render env var:
```
CLARITY_OAUTH_ISSUER_URL = https://www.priority-guard.com/oauth/mindsort
This makes OAUTH_ISSUER_URL = https://www.priority-guard.com/oauth/mindsort, so authorization_servers in oauth_protected_resource() returns ["https://www.priority-guard.com/oauth/mindsort"].

Verification after deploy — exact sequence
Step 1: Verify backend MindSort discovery exists and is correct
bashcurl https://www.priority-guard.com/oauth/mindsort/.well-known/oauth-authorization-server
Expected:

issuer: https://www.priority-guard.com
registration_endpoint: https://www.priority-guard.com/oauth/mindsort/register
scopes_supported: ["clarity.write"]

Step 2: Verify DCR assigns correct scope
bashcurl -X POST https://www.priority-guard.com/oauth/mindsort/register \
  -H "Content-Type: application/json" \
  -d '{"client_name":"test","redirect_uris":["https://chatgpt.com/connector_platform_oauth_redirect"]}'
Expected: "scope": "clarity.write"
Step 3: Verify JWKS is serving
bashcurl https://www.priority-guard.com/oauth/mindsort/jwks
Expected: same keys as /oauth/pg/jwks
Step 4: After MCP env var update and redeploy — verify MindSort protected resource
bashcurl https://mindsort.priority-guard.com/.well-known/oauth-protected-resource
Expected:

resource: https://mindsort.priority-guard.com/mcp
authorization_servers: ["https://www.priority-guard.com/oauth/mindsort"]

Step 5: Verify settings.OAUTH_ISSUER is the shared root
bashcurl https://www.priority-guard.com/oauth/mindsort/.well-known/oauth-authorization-server | grep issuer
Must return "issuer": "https://www.priority-guard.com" — not a path-qualified URL.
Step 6: PG regression — must be identical to before deploy
bashcurl https://www.priority-guard.com/.well-known/oauth-authorization-server
# scopes_supported must be ["pg.access"] only
curl https://pg.priority-guard.com/.well-known/oauth-protected-resource
# authorization_servers must be ["https://www.priority-guard.com"]
curl https://www.priority-guard.com/oauth/pg/jwks
# same keys as before

Do not modify backend/core/oauth_provider/services/client_service.py. The default scopes fallback in create_oauth_client is never hit by this increment — register_client.py always passes explicit scopes. Leave it unchanged. Flag it with a # TODO: remove legacy default scopes comment as a post-submission cleanup task.