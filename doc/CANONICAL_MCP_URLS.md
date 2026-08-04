# Canonical MCP Server URLs

**Purpose:** Single source of truth for production MCP server URLs used in platform submissions, OAuth discovery, and compliance testing.

**Last updated:** 2026-07-02

---

## Production URLs

| Server | Platform | Canonical URL | Resource URL |
|--------|----------|---------------|--------------|
| PG-OpenAI | ChatGPT | `https://pg.priority-guard.com` | `https://pg.priority-guard.com/mcp` |
| MindSort-OpenAI | ChatGPT | `https://mindsort.priority-guard.com` | `https://mindsort.priority-guard.com/mcp` |
| PG-Claude | Claude | `https://mcp.priority-guard.com` | `https://mcp.priority-guard.com/mcp` |
| MindSort-Claude | Claude | `https://mindsort-mcp.priority-guard.com` | `https://mindsort-mcp.priority-guard.com/mcp` |

---

## Authorization Server

| Component | URL |
|-----------|-----|
| Issuer | `https://www.priority-guard.com` |
| PG OAuth endpoints | `https://www.priority-guard.com/oauth/pg/*` |
| MindSort OAuth endpoints | `https://www.priority-guard.com/oauth/mindsort/*` |

---

## Usage

These URLs are used in:
- Platform submission forms (OpenAI GPT Store, Anthropic MCP directory)
- OAuth discovery documents (`authorization_servers`, `resource`)
- Live integration tests (`tests/integration/oauth_discovery/`)
- Deployment verification

**Do not use Render's `.onrender.com` URLs in submissions or discovery documents.**

---

## Cross-References

- `doc/ADR/ADR_005_platform_oauth_discovery_contracts.md` — Discovery shape contracts
- `doc/OPERATIONS_PRESUBMISSION.md` — Pre-submission checklist
- `tests/integration/oauth_discovery/test_live_discovery_chain.py` — Live tests using these URLs
