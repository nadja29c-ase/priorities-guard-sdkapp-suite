**Project:** Focused (part of the Priority Guardian suite)
Focused is a lightweight SDK app in the Priority Guardian Suite that connects your Google Calendar with your Apple Focus Mode. 

Whenever a calendar event labeled “Focus,” “Deep Work,” or any chosen keyword begins, Focused automatically activates Focus Mode on user’s iPhone. Focused also learns when the user concentrates best and helps the user leverage their focus pattern.
Designed primarily for Apple / Google Calendar users.

**Goal:** Build a production-ready, privacy-first MVP that connects Google Calendar → Shared Backend → ChatGPT SDK App, following OAuth 2.1 + GDPR compliance.
All SDK apps share one verified domain:
`https://www.priority-guard.com/<function>/<app_name>/`

# Focused App Requirements
- Detect "Focus Block" events in Google Calendar 
- Trigger Apple Focus Mode via [specify mechanism] 
- Track and analyze focus patterns (successful focus times, optimal durations)
- Store user preferences and focus patterns 
- Handle webhook notifications from Google
- System Architecture Summary

*** This project will be delivered incrementally and iteratively. This project brief is for big-picture overview purpose to ensure consistency and compliance of increments! ***

# System Architecture
Priority Guardian consists of six clearly separated layers:

1. **AI Runtime (ChatGPT)**
Hosts user interaction and invokes tools defined by each SDK app's manifest
2. **Manifest (per SDK app)**
Declares the tools, parameters, and permissions for each SDK app
3. **MCP Server (per SDK app)**
Implements those tools by calling backend APIs. Each app runs in its own sandbox. Each MCP Server uses OAuth 2.1 tokens issued by the Priority Guardian provider to authenticate tool requests.
4. **Shared Backend (=Core)**:
- One FastAPI backend serves multiple MCP servers (one per app)
- FastAPI with **Pydantic v2** models.
- Shared OAuth provider for ChatGPT (issues tokens to all apps)
- Shared Google OAuth client (all apps use calendar.readonly)
- Shared database tables for users, connections, consents, audit logs
- App-specific tables (focused_, decliner_, scheduler_*)
5. **App-Specific Modules**
Separate logic for each SDK app (Focused, sdk app 2, sdk app 3)
6. **External APIs**
Google Calendar (events, webhooks, OAuth) and Apple Shortcuts


**Core Infrastructure:**
- Python as the primary language
- FastMCP for building backend MCP servers
- PostgreSQL for data persistence (11 database tables with detailed retention policies)
- Redis for caching (RDB persistence) and job queues
- Celery for background task processing

**Database & Migrations:**
- SQLAlchemy for ORM and database management (with connection pooling)
- Alembic for database migrations

**External Integrations:**
- Google Calendar API as the core integration point
- Google Cloud Console for OAuth configuration and API access
- OAuth with calendar.readonly scope

**Hosting & Compliance:**
- AWS Frankfurt for deployment (EU GDPR compliance)
- Stateless API design for horizontal scaling
- Architecture validated for 3K-100K users with clear scaling paths

**Key Architectural Patterns:**
- Redis-only caching strategy
- SHA256-based conflict detection
- Multi-layer webhook renewal strategy
- Webhook idempotency with exponential backoff for Google API calls

**Configuration Management:**
- All config via environment variables
- `core/config.py` centralizes access

**Data Architecture:**
- Shared tables: `core_*` (users, connections, audit)
- App-specific tables: `<app>_*` (sessions, patterns, preferences)

## Project Structure
```
priority-guardian/
├── backend/
│   ├── core/                   # "shared" backend infra
│   │   ├── config.py
│   │   ├── db.py               # later: SQLAlchemy + Alembic
│   │   ├── oauth_provider.py   # inbound ChatGPT OAuth 2.1 provider
│   │   ├── google_client.py    # outbound Google OAuth client
│   │   ├── redis_client.py
│   │   └── celery_app.py       # background jobs (token/webhook renewal)
│   │
│   ├── apps/
│   │   ├── focused/
│   │   │   ├── __init__.py
│   │   │   ├── server.py       # Focused MCP FastAPI router
│   │   │   ├── tools.py        # run_focus_mode(), check_calendar(), etc.
│   │   │   └── models.py       # focused_* tables
│   │   └── sdk app 2/   # future SDK app
│   │
│   ├── main.py                 # mounts OAuth + app routers
│   └── __init__.py
│
├── pyproject.toml
├── .env.example
└── README.md
```
## Error Handling Strategy:
- Centralized exception handler in `main.py`
- Custom exception classes per error type (OAuth, Google API, validation)
- Exponential backoff for Google API calls (max 5 retries)
- Webhook idempotency via unique event IDs
- Graceful degradation (cache stale data if APIs fail)
- User-facing errors never expose internal details

**Logging Pattern:**
- Structured JSON logs
- Include: user_id, request_id, app_name, timestamp
- Levels: DEBUG (dev), INFO (prod), ERROR (always)

# Claude Code: Output & Artifact Rules
- All generated code must follow the structure defined under **Project Structure**.
- Each new artifact (script, module, or endpoint) must:
  - Reside inside the correct module path (e.g., backend/apps/focused/).
  - Include docstrings describing purpose, inputs, and outputs.
  - Use backend/core/config.py for all configuration values.
  - Never hard-code secrets or URLs.
- Return all responses in JSON with success, error, and data fields.
- For async endpoints, use async def and await FastAPI conventions.
- Unit tests should be placed in tests/<app_name>/.

**Code Style:**
- Type hints on all functions
- Follow PEP 8 naming (snake_case functions, PascalCase classes)
- Keep functions focused (single responsibility)

## Coding Conventions
- Framework: **FastAPI** with **Pydantic v2** models.
- ORM: **SQLAlchemy 2.x** with `AsyncSession`.
- **All endpoints and DB/API calls: async/await.** Blocking ops → Celery.
- Background jobs: **Celery 5.x** with Redis broker.

**Security:**
  - Validate all input data with Pydantic models.
  - Verify OAuth token before executing any tool logic.
  - Apply rate limiting via Redis counter pattern.