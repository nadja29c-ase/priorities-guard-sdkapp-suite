Increment briefing — Add /.well-known/oauth-authorization-server to backend
File to change: backend/core/oauth_provider/discovery.py only.
What to do:
Extract the metadata dict construction into a private helper function _authorization_server_metadata() -> dict that returns the full metadata dict. Both openid_configuration() and the new oauth_authorization_server() route handler call this helper and wrap the result in JSONResponse. This guarantees the two endpoints can never drift.
The metadata dict contains:
python{
    "issuer": settings.OAUTH_ISSUER,
    "authorization_endpoint": f"{settings.OAUTH_ISSUER}/oauth/pg/authorize",
    "token_endpoint": f"{settings.OAUTH_ISSUER}/oauth/pg/token",
    "jwks_uri": f"{settings.OAUTH_ISSUER}/oauth/pg/jwks",
    "registration_endpoint": f"{settings.OAUTH_ISSUER}/oauth/pg/register",
    "scopes_supported": SCOPES_SUPPORTED,
    "response_types_supported": ["code"],
    "grant_types_supported": ["authorization_code", "refresh_token"],
    "code_challenge_methods_supported": ["S256"],
    "token_endpoint_auth_methods_supported": ["none"]
}
The new route is GET /.well-known/oauth-authorization-server. Refactor openid_configuration() to also use the shared helper — do not leave it duplicating the dict inline.
No new imports. No router changes. No config changes. No database changes. No token impact.
Read OPERATIONS_PREDEPLOY.md before committing.
Verification after deploy:
bashcurl -s https://www.priority-guard.com/.well-known/oauth-authorization-server | python3 -m json.tool
# Must return 200 with issuer: "https://www.priority-guard.com"

curl -s https://www.priority-guard.com/.well-known/openid-configuration | python3 -m json.tool  
# Must still return 200 — unchanged behaviour