# Code Review Guide: Clarity

**Projekt:** Clarity – KI-gestütztes Tool zur Gedankenstrukturierung
**Repository:** priority-guardian
**Entwicklerin:** Claude Code unter Anleitung von Nadja Carabulea

---

## Projektübersicht

Clarity ist ein MCP-Server mit OAuth 2.1 Authentifizierung, der als ChatGPT-App funktioniert. Das Tool hilft Nutzern, Gedanken zu strukturieren und zu priorisieren durch visuelle Cluster-Boards.

**Kernfunktion:** ChatGPT clustert und strukturiert Gedanken des Nutzers, der MCP-Server validiert und formatiert die Daten, und ein React-Widget rendert die Cluster als visuelle Karten. Auf Basis dieser Cluster, kann der Nutzer priorisieren.

---

## Repository-Struktur

Das Repository enthält mehrere Projekte, die ein shared backend teilen. Für Clarity relevant:

### OAuth 2.1 Provider
```
backend/core/oauth_provider/
├── authorize.py              # Authorization Endpoint
├── token_endpoint.py         # Token Exchange (Authorization Code → Access Token)
├── jwks.py                   # JWKS Endpoint (Public Keys)
├── consent_ui.py             # User Consent UI
├── cookies.py                # Session Cookie Handling
├── discovery.py              # OAuth Discovery Endpoints
├── revoke.py                 # Token Revocation
├── register_client.py        # Dynamic Client Registration
├── models.py                 # SQLAlchemy Models
├── exceptions.py             # OAuth Error Types
├── jwt/                      # JWT Signing/Verification
│   ├── jwt_signer.py
│   └── utils.py
├── services/                 # Business Logic
│   ├── authorization_service.py
│   ├── token_service.py
│   ├── consent_service.py
│   ├── session_service.py
│   ├── revoke_service.py
│   ├── jwks_service.py
│   └── client_service.py
└── validators/               # Input Validation
    ├── pkce.py
    ├── token_validators.py
    └── client_metadata.py
```

### Clarity MCP Server
```
mcp_server/clarity/
├── server.py                 # MCP Server + ASGI App
├── mcp_auth.py               # JWT Validation & JWKS Caching
├── persistence.py            # Datenbank-Operationen (Board CRUD)
├── config.py                 # Environment Configuration
├── discovery.py              # OAuth Protected Resource Metadata
├── tool_logic.py             # Pure Business Logic (Clustering)
├── request_context.py        # Auth Header Context Propagation
├── http_client.py            # Shared HTTP Client
├── handlers/                 # MCP Request Handlers
│   ├── tools.py              # Tool Call Dispatch
│   └── resources.py          # Widget Resource Serving
├── tools/                    # Tool-Definitionen
│   ├── base.py               # ToolDefinition Schema
│   ├── board_utils.py        # Shared Board Utilities
│   ├── organize_thoughts.py  # Cluster Thoughts into Board
│   ├── prioritize_clusters.py# Prioritize Clusters
│   ├── save_board.py         # Persist Board to DB
│   ├── load_saved_board.py   # Load Board from DB
│   ├── read_saved_board.py   # Read Board (no widget)
│   ├── edit_board.py         # Modify Board
│   └── delete_my_data.py     # GDPR Data Deletion
├── widget-react/             # React Widget (TypeScript)
└── tests/                    # Unit Tests
```

---

## Tools

| Tool | Beschreibung | Scope |
|------|--------------|-------|
| `organize_thoughts` | Clustert Gedanken/Tasks in visuelle Boards | clarity.write |
| `prioritize_clusters` | Priorisiert die Cluster  | clarity.write |
| `save_board` | Speichert Board in Datenbank | clarity.write |
| `load_saved_board` | Lädt gespeichertes Board (mit Widget) | clarity.read |
| `read_saved_board` | Liest Board-Daten (ohne Widget) | clarity.read |
| `edit_board` | Bearbeitet bestehendes Board | clarity.write |
| `delete_my_data` | Löscht alle Nutzerdaten (GDPR) | clarity.write |

---

## Architektur-Details

### Request Flow
1. ChatGPT sendet MCP Request an `/mcp` Endpoint
2. Middleware korrigiert ChatGPT Header-Quirks (octet-stream → json)
3. JWT wird aus Authorization Header validiert gegen JWKS
4. Tool Handler verarbeitet Request
5. Response enthält `structuredContent` mit Cluster-Daten für Widget, State-Flags, und `assistant_guidance` (Anweisungen für ChatGPT's Antwortverhalten)

### Middleware
- **MCPContentTypeAndAcceptFixMiddleware**: Korrigiert ChatGPT's `Content-Type: application/octet-stream` zu `application/json`
- **CORS**: Eingeschränkt auf OpenAI/ChatGPT Domains

### Stateless Design
Server ist stateless (`stateless_http=True`). Jeder Request ist selbständig via JWT authentifiziert. Keine Server-seitigen Sessions.

---

## Technologie-Stack

- Python / FastAPI / Starlette
- PostgreSQL / SQLAlchemy
- Redis (Caching)
- OAuth 2.1 / JWT (RS256)
- React / TypeScript (Widget)
- Render (Deployment)
- MCP SDK (Model Context Protocol)

---

## Deployment

- **Production URL:** Render-hosted
- **Config:** `mcp_server/clarity/DEPLOYMENT.md`
- **Environment:** `mcp_server/clarity/ENV_TEMPLATE.md`

---

## Security

- OAuth 2.1 mit PKCE
- RS256 JWT Signing
- Scope-based Access Control (clarity.read, clarity.write)
- CORS auf bekannte Domains beschränkt
- Token Revocation Support
