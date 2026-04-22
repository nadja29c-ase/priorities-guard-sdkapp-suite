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
- **Single source of truth**: One registry dict replaces per-app branching. Adding a new app is a one-line change.
- **Explicit routing preserved**: Route decorators remain the source of reachable paths; the registry is only default-scope lookup. This separation prevents accidental auto-registration of routes from dict entries.

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

1. **Add new apps to `ROUTE_SCOPE_REGISTRY`** — one dict entry plus one route decorator. No branching logic needed.
2. **New scopes must be added to `SCOPES_SUPPORTED` in `discovery.py`** before adding them here — discovery is the single source of truth. Adding a scope to the route mapping without adding it to discovery will cause DCR clients to receive scopes that are not advertised, which breaks OpenAI's OAuth flow.
3. **The `SUPPORTED_SCOPES` set in `register_client.py`** is derived from `discovery.SCOPES_SUPPORTED` — do not define scopes in two places.
4. **Resource allowlist — not implemented, decision 2026-04-22:**

   The OAuth provider accepts arbitrary `resource` parameter values and mints JWTs with `aud = <resource>`. This is RFC-compliant. An earlier version of this ADR flagged this as work to be done "when a third app is added" (MindSort AI, added April 2026).

   **Risk reassessment (April 22, 2026):** No live attack surface exists.
   - DCR redirect URI allowlist (`OAUTH_ALLOWED_REDIRECT_URIS`) constrains which clients can even register
   - Every MCP server in the suite enforces its own `aud` allowlist during JWT validation — a forged `aud` cannot be consumed by any MCP server in this architecture
   - No external MCP server federates with `iss = https://www.priority-guard.com`
   - The theoretical threat (attacker-chosen `aud` usable against a future trusting MCP server) requires architectural changes that are not on the roadmap

   **Decision:** Do not implement. The over-permissive `resource` behavior is accepted as RFC-compliant with no exploitation path in the current architecture.

   **Revisit only if:**
   - OAuth provider is opened to third-party clients beyond ChatGPT/Claude/MCP Inspector
   - An external MCP server begins federating with this issuer
   - A security audit specifically flags it

   No backlog ticket. This item is closed unless one of the above triggers fires.

---

## Files Affected

| File | Role |
|------|------|
| `backend/core/oauth_provider/register_client.py` | Route-to-scope mapping (current implementation) |
| `backend/core/oauth_provider/discovery.py` | `SCOPES_SUPPORTED` — single source of truth for valid scopes |
| `backend/core/oauth_provider/services/token_service.py` | Resource parameter handling (RFC 9728 B2-5) |
| `backend/core/config.py` | `OAUTH_ALLOWED_REDIRECT_URIS`, `PG_MCP_SERVER_URL` env vars |
