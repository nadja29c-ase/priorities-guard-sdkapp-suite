# ADR 003 — OAuth Provider: Route-to-Scope Mapping Strategy

**Date:** March 2026 (Amended: April 21, 2026)
**Status:** Accepted — migrated to registry April 21, 2026
**Context:** `backend/core/oauth_provider/register_client.py`

---

## Decision

Default OAuth scopes for dynamic client registration are derived from a **registry dict** in `register_client.py`:

```python
ROUTE_SCOPE_REGISTRY: dict[str, list[str]] = {
    "focused":  ["focused.read", "focused.write", "focused.notify"],
    "pg":       ["pg.access"],
    "mindsort": ["clarity.write"],
}

# Derive app name from route: "/oauth/<app>/register" -> "<app>"
route_parts = request.url.path.split("/")
app_name = route_parts[2] if len(route_parts) >= 3 else None
default_scopes = ROUTE_SCOPE_REGISTRY.get(app_name)
if default_scopes is None:
    raise HTTPException(status_code=404, detail="Unknown OAuth registration route")
```

Each SDK app gets its own registration route (`/oauth/<app>/register`) with its own entry in the registry. Route decorators remain explicit — the registry is only for scope lookup, not route generation.

---

## Rationale

- **Least privilege**: Each route grants only the scopes its app needs. ChatGPT does not send a `scope` parameter during DCR — defaults determine what the client receives.
- **Simplicity at current scale**: Two apps. Explicit is better than automatic when the mapping is trivial.
- **Backward compatibility**: `focused.*` scopes predate the PG suite structure. Hardcoding preserves exact behavior without risk of regression.

---

## Implementation

To add a new authenticated SDK app:

1. Add the scope to `SCOPES_SUPPORTED` in `discovery.py` (or keep the union pattern used by `SUPPORTED_SCOPES` for app-specific scopes).
2. Add one entry to `ROUTE_SCOPE_REGISTRY` in `register_client.py`.
3. Add one `@router.post("/oauth/<app>/register")` decorator on `register_endpoint`.

That's it — one dict entry, one route decorator. No branching logic, fail-fast on unknown routes.

---

## Trigger for Revisiting

Revisit if route structure fundamentally changes (e.g., dynamic route registration, multi-tenant scope derivation, or scopes no longer deducible from URL path).

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
