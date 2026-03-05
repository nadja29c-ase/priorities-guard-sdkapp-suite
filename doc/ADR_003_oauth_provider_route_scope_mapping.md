# ADR 003 — OAuth Provider: Route-to-Scope Mapping Strategy

**Date:** March 2026  
**Status:** Accepted  
**Context:** `backend/core/oauth_provider/register_client.py`

---

## Decision

Default OAuth scopes for dynamic client registration are **hardcoded per route** in `register_client.py`:

```python
DEFAULT_SCOPES_FOCUSED = ["focused.read", "focused.write", "focused.notify"]
DEFAULT_SCOPES_PG = ["pg.access"]

if route_path == "/oauth/focused/register":
    default_scopes = DEFAULT_SCOPES_FOCUSED
else:
    default_scopes = DEFAULT_SCOPES_PG
```

Each SDK app gets its own registration route (`/oauth/<app>/register`) with its own hardcoded default scope list.

---

## Rationale

- **Least privilege**: Each route grants only the scopes its app needs. ChatGPT does not send a `scope` parameter during DCR — defaults determine what the client receives.
- **Simplicity at current scale**: Two apps. Explicit is better than automatic when the mapping is trivial.
- **Backward compatibility**: `focused.*` scopes predate the PG suite structure. Hardcoding preserves exact behavior without risk of regression.

---

## Known Technical Debt

This pattern **does not scale** cleanly beyond 3–4 apps. Each new SDK app requires:

1. A new `DEFAULT_SCOPES_<APP>` constant
2. A new `elif route_path == "/oauth/<app>/register":` branch
3. A new route decorator on `register_endpoint`
4. Manual verification that the new scope is in `SCOPES_SUPPORTED` (discovery)

If this is missed, the app either gets wrong scopes silently (too broad) or fails at runtime (scope not in discovery).

**The correct long-term fix** is to derive default scopes from the route namespace automatically:

```python
# Example: derive app name from route, look up scopes from a registry
ROUTE_SCOPE_REGISTRY = {
    "focused": ["focused.read", "focused.write", "focused.notify"],
    "pg":      ["pg.access"],
    "clarity": ["clarity.write"],
    # Add new apps here — single source of truth
}

app_name = request.url.path.split("/")[2]  # e.g. "pg" from "/oauth/pg/register"
default_scopes = ROUTE_SCOPE_REGISTRY.get(app_name)
if default_scopes is None:
    raise HTTPException(status_code=404, detail="Unknown OAuth route")
```

This moves the mapping to a **single dict** — one line per new app, no branching logic, fail-fast on unknown routes.

---

## Trigger for Revisiting

Revisit this ADR when adding a **third authenticated SDK app** to the suite. At that point the if/elif chain becomes a maintenance liability and the registry pattern above should replace it.

---

## What Claude Code Must Know

When adding a new SDK app that requires authentication:

1. **Do not add another `elif` branch** to `register_endpoint`. Migrate to the registry pattern first.
2. **New scopes must be added to `SCOPES_SUPPORTED` in `discovery.py`** before adding them here — discovery is the single source of truth. Adding a scope to the route mapping without adding it to discovery will cause DCR clients to receive scopes that are not advertised, which breaks OpenAI's OAuth flow.
3. **The `SUPPORTED_SCOPES` set in `register_client.py`** is derived from `discovery.SCOPES_SUPPORTED` — do not define scopes in two places.
4. **Resource allowlist (`OAUTH_ALLOWED_RESOURCES`)**: The OAuth provider currently accepts arbitrary `resource` parameter values and will mint JWTs with `aud = <whatever resource was passed>`. This is RFC-compliant but should be locked to known MCP server URLs when a third app is added. Add validation in `token_service.py` before the RFC 9728 resolution rules:
   ```python
   ALLOWED_RESOURCES = {settings.PG_MCP_SERVER_URL, ...}
   if resource and resource not in ALLOWED_RESOURCES:
       return ("invalid_target", "Invalid resource parameter")
   ```

---

## Files Affected

| File | Role |
|------|------|
| `backend/core/oauth_provider/register_client.py` | Route-to-scope mapping (current implementation) |
| `backend/core/oauth_provider/discovery.py` | `SCOPES_SUPPORTED` — single source of truth for valid scopes |
| `backend/core/oauth_provider/services/token_service.py` | Resource parameter handling (RFC 9728 B2-5) |
| `backend/core/config.py` | `OAUTH_ALLOWED_REDIRECT_URIS`, `PG_MCP_SERVER_URL` env vars |
