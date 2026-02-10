# PG Inc 02 — `create_priority` Tool + `pg_priorities` Table

**Increment:** 02 of N  
**Prerequisite:** Inc 01 (PG pipes) deployed — PG MCP server on port 8003, PG backend app module at `/api/priority-guardian/`, `pg.access` scope in OAuth provider, JWT auth on MCP server  
**Output:** Working `create_priority` tool validated in MCP Inspector + `pg_priorities` + `pg_deliverables` tables with passing tests

---

## Pre-flight Check

Before starting, verify Inc 01 state:

1. PG MCP server starts and `tools/list` returns `connect_google_calendar` + `disconnect_google_calendar`
2. PG backend health returns OK at `/api/priority-guardian/health`
3. JWT auth works (`authenticate_request` in `mcp_server/priority_guardian/mcp_auth.py`)
4. `backend_post()` and `backend_get()` helpers exist in `mcp_server/priority_guardian/server.py`

If any fail → STOP and report. Do not build on broken pipes.

---

## Context

Priority Guardian helps freelancers/solopreneurs protect time for their top 3 priorities. During **onboarding**, the LLM coaches the user through declaring 1–3 priorities conversationally (one at a time). Each priority gets a calendar keyword (P1, P2, or P3) — assigned by the backend — that the user tags their Google Calendar events with. This is how PG calculates time allocation.

Two priority types exist:

- **Deadline**: has a hard end date (e.g., "Launch marketing site by March 15"). Deliverables are tracked separately in a later increment — not part of priority creation.
- **Flexible**: ongoing time investment toward a 1-month goal (e.g., "Spend 10h/week on client outreach")

`create_priority` is the **first business logic tool** in PG. It is a **public** tool — the LLM calls it during onboarding. In later increments, the widget will also call it (post-onboarding, marked widgetAccessible).

---

## Architecture: Two Layers

PG combines two patterns. Claude Code must understand both:

### Execution Architecture (PG thin-wrapper pattern — NOT Sharpen)

```
ChatGPT → MCP Server (port 8003) → Backend REST API (port 8000) → PostgreSQL
              ↑                         ↑
         JWT validation            Business logic + DB
         Forwards HTTP             Validation + persistence
         No DB access              Returns structured JSON
```

- **MCP server**: validate JWT, forward to backend via `backend_post()`, return response. No business logic, no validation, no DB access.
- **Backend**: validate input, enforce constraints, persist, return structured response.

Study existing tools in `mcp_server/priority_guardian/server.py` (`connect_google_calendar`, `disconnect_google_calendar`) for the exact forwarding pattern.

### Tool UX Design (Sharpen's goal-oriented pattern)

- **DESCRIPTION**: behavioral contract with call preconditions, tells LLM WHEN to call and WHEN NOT to call
- **INPUT_SCHEMA**: field descriptions as quality gates, tells LLM what each field means in context, prevents LLM from inventing data
- **`assistant_guidance`** in structuredContent: controls WHAT LLM says after tool returns

Study these Sharpen files for the design language:
- `mcp_server/sharpen/tools/frame_initiative_intent.py` — CALL PRECONDITIONS, verbatim fields, confirmation booleans
- `mcp_server/sharpen/tools/identify_e2e_deliverables.py` — CONFIDENCE EXAMPLES, CRITICAL BOUNDARY rules

**What NOT to adopt from Sharpen**: self-registration pattern, inline business logic in MCP server, `tool_logic.py` validation in MCP layer. All validation lives in the backend for PG.

---

## Shared Database Convention

All PG tables live in the **same PostgreSQL instance** as shared tables. This is how the shared backend architecture works:

- `core_*` tables = shared across all SDK apps (core_users, core_connections, core_consents, etc.)
- `pg_*` tables = Priority Guardian app-specific
- `focused_*` tables = Focused app-specific
- `clarity_*` tables = Clarity app-specific

The FK `pg_priorities.user_id → core_users.id` works because they share the same database. Do NOT create a separate database for PG tables.

---

## Trust Boundary: X-User-ID

**Architectural assumption — document in code comments at the auth extraction point in both MCP server and backend router:**

The backend trusts the `X-User-ID` header because:
- Only the PG MCP server calls backend tool endpoints
- The MCP server validates the JWT (signature, expiry, scope) and extracts `user_id` from the `sub` claim
- Backend tool endpoints are not directly internet-accessible for tool operations
- The MCP server sets `X-User-ID` from the validated JWT — never from client input

**If this assumption changes** (e.g., backend becomes directly accessible, another service calls the backend, or direct client → backend calls are added), add backend-side JWT validation.

**Hard requirements to enforce:**

1. **Network-level restriction**: Backend tool endpoints must not be directly reachable from the internet. They are internal service endpoints called only by the MCP server.
2. **Header hygiene in the backend router**:
   - Reject missing `X-User-ID` → 401
   - Reject malformed (non-UUID) `X-User-ID` → 401
   - Never accept user IDs from request bodies — only from the `X-User-ID` header
3. **Code comments**: Place the trust boundary documentation as a comment block next to the auth extraction code in both `mcp_server/priority_guardian/server.py` (where JWT is validated and X-User-ID is set) and in the backend priority router (where X-User-ID is read and trusted).

---

## Data Lifecycle for Priorities

Understanding how priority data lives and dies — critical for getting the data model right:

- **Creation** (this increment): inserts a `pg_priorities` row. Row persists until explicitly deleted or retired.
- **Edits** (later increment): user can modify name, deadline, hour target, desired result, deliverable status via tool calls. Edits **update the row in place** — `updated_at` tracks when. No version history on the priority row itself.
- **Historical lookback** comes from `pg_weekly_snapshots` (later increment) — point-in-time aggregated state captured weekly. Retained for lifetime of parent priority, max 90 days after retirement.
- **Running aggregates** (`streak_count`, `avg_hours_week`, `total_hours_invested`) are columns on `pg_priorities` — computed from snapshots during weekly reflection. Frozen at retirement. Default to 0 in Inc 02, no code reads or writes them.
- **Retirement**: priority marked `status = retired`, `retired_at = now()`. Data retained but frozen and read-only. Snapshots auto-deleted 90 days after retirement via Celery cleanup.
- **Deletion**: priority record deleted, all dependent data (deliverables, snapshots, checkpoint history) cascade deleted.
- **Full account deletion**: Celery job deletes all PG data in order (checkpoints → snapshots → deliverables → priorities → onboarding state), then shared tables.

**GDPR note:** No PII in `pg_priorities` or `pg_deliverables`. `name`, `desired_result` are user-authored free text. Users are instructed not to include personal or sensitive data in free-text fields (UX-level guidance, not backend-enforced). See Data Retention Policy for full retention schedule and cascade rules.

---

## Deliverables

### 1. Database Migration (Alembic)

Use `TIMESTAMP WITH TIME ZONE` for all timestamp columns. Implement `updated_at` auto-update via SQLAlchemy `onupdate=func.now()` on the column definition — Postgres does not auto-update this without explicit implementation.

**Table: `pg_priorities`**

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, server-generated | |
| `user_id` | UUID | FK → core_users.id, NOT NULL, indexed | Same DB — see Shared Database Convention |
| `name` | VARCHAR(100) | NOT NULL | User-authored, max 100 chars |
| `type` | VARCHAR(10) | NOT NULL, CHECK IN ('deadline', 'flexible') | |
| `calendar_keyword` | VARCHAR(2) | NOT NULL, CHECK IN ('P1', 'P2', 'P3') | Assigned by backend, never by LLM or client |
| `status` | VARCHAR(10) | NOT NULL, DEFAULT 'active', CHECK IN ('active', 'retired') | |
| `deadline` | DATE | NULLABLE | Required when type=deadline |
| `weekly_hour_target` | NUMERIC | NULLABLE | Required when type=flexible, > 0 |
| `checkpoint_date` | DATE | NULLABLE | Required when type=flexible |
| `desired_result` | VARCHAR(200) | NULLABLE | Required when type=flexible |
| `streak_count` | INTEGER | NOT NULL, DEFAULT 0 | Future aggregate — do NOT read/write in Inc 02 |
| `avg_hours_week` | NUMERIC | NULLABLE | Future aggregate — do NOT read/write in Inc 02 |
| `total_hours_invested` | NUMERIC | NOT NULL, DEFAULT 0 | Future aggregate — do NOT read/write in Inc 02 |
| `retired_at` | TIMESTAMPTZ | NULLABLE | Set when status changes to retired (later increment) |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now(), onupdate=func.now() | Explicit SQLAlchemy onupdate |

**Constraints:**
- `UNIQUE(user_id, calendar_keyword) WHERE status = 'active'` — partial unique index
- Max 3 active priorities per user — enforced in application logic within a transaction (see Transactional Safety below)

**Note on aggregate columns:** `streak_count`, `avg_hours_week`, `total_hours_invested` exist in the schema for migration simplicity (avoids future backfill migration) but are NOT authoritative in Inc 02. No code in this increment reads or writes them. They will be populated by weekly reflection tools in later increments. Do not treat them as authoritative.

**Table: `pg_deliverables`**

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, server-generated | |
| `priority_id` | UUID | FK → pg_priorities.id ON DELETE CASCADE, NOT NULL, indexed | |
| `name` | VARCHAR(200) | NOT NULL | |
| `done` | BOOLEAN | NOT NULL, DEFAULT false | Binary only |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, DEFAULT now(), onupdate=func.now() | |

**Index:** `priority_id` on pg_deliverables (for CASCADE lookups)

### 2. Backend: SQLAlchemy Models

Location: `backend/apps/priority_guardian/models/`

Create SQLAlchemy models for `PgPriority` and `PgDeliverable`. Follow existing patterns in `backend/apps/focused/` for model conventions (Base class import, naming, relationships). The `PgDeliverable` model exists for schema completeness — no code in Inc 02 creates deliverables.

### 3. Backend: Validation Layer

**All input validation lives in one place.** Create a Pydantic request model (e.g., `CreatePriorityRequest`) in `backend/apps/priority_guardian/models/requests.py`. This model handles:

- Field presence and type validation
- Type-conditional required fields (deadline fields for deadline type, flexible fields for flexible type)
- Value constraints (future dates, positive hours, string length limits)
- Enum validation (type must be deadline|flexible)

The **router** orchestrates only: parse request → validate via Pydantic → transactional DB logic → return response. No validation logic scattered in the router itself. This keeps validation testable in isolation and reusable when Inc 03+ adds update/edit endpoints.

### 4. Backend: Priority Creation Router

Location: `backend/apps/priority_guardian/routers/` (new file, e.g., `priorities_router.py`)

**Endpoint:** `POST /api/priority-guardian/priorities`

**Auth:** `X-User-ID` header. Validate as UUID — reject 401 if missing or malformed. See Trust Boundary section for code comment requirements.

**Request body:**

```json
{
  "name": "string (required, max 100)",
  "type": "deadline | flexible (required)",
  "deadline": "YYYY-MM-DD (required if deadline)",
  "weekly_hour_target": "number > 0 (required if flexible)",
  "checkpoint_date": "YYYY-MM-DD (required if flexible)",
  "desired_result": "string, max 200 (required if flexible)"
}
```

**No `calendar_keyword` in request.** Backend assigns it deterministically.

#### Transactional Safety (Critical)

The create endpoint MUST wrap keyword assignment + max-3 enforcement in one DB transaction:

1. `SELECT ... FOR UPDATE` on user's active priorities (locks rows, prevents concurrent races)
2. Count active priorities — if ≥ 3, return 409
3. Compute next available keyword: query existing active keywords, assign first unused from [P1, P2, P3] in order
4. If no keywords available (shouldn't happen if count < 3, but defensive) → 409
5. INSERT new priority with assigned keyword
6. COMMIT

This prevents two concurrent requests both seeing 2 active priorities and both trying to create P3.

**IntegrityError fallback:** Even with transactional locking, catch `sqlalchemy.exc.IntegrityError` from the partial unique index. If caught, map it explicitly to 409 `KEYWORD_CONFLICT`. Do NOT let it bubble as 500. This is the race condition safety net.

#### `available_keywords` Computation

`available_keywords` in the response MUST reflect **post-commit state**. Compute it after the successful insert by querying the user's current active keywords and returning the complement against [P1, P2, P3]. Never pre-compute before the insert.

#### Error Responses (Consistent)

| Condition | Status | Code | Notes |
|-----------|--------|------|-------|
| Missing/invalid X-User-ID | 401 | `UNAUTHORIZED` | Non-UUID or missing header |
| Schema validation failure | 422 | `VALIDATION_ERROR` | Missing required fields, wrong types, past dates, negative hours, string too long |
| Max 3 active priorities exceeded | 409 | `MAX_PRIORITIES_REACHED` | |
| Duplicate active keyword (race fallback) | 409 | `KEYWORD_CONFLICT` | Caught from IntegrityError |

All error responses include a human-readable `message` field for `assistant_guidance` to relay.

#### Success Response (201 Created)

```json
{
  "success": true,
  "data": {
    "priority": {
      "id": "uuid",
      "name": "...",
      "type": "deadline|flexible",
      "calendar_keyword": "P1|P2|P3",
      "status": "active",
      "deadline": "2026-03-15 or null",
      "weekly_hour_target": 10.0,
      "checkpoint_date": "2026-03-08 or null",
      "desired_result": "... or null",
      "deliverables": [],
      "created_at": "ISO datetime with timezone"
    },
    "active_priority_count": 1,
    "available_keywords": ["P2", "P3"]
  }
}
```

**Mount** the new router in `backend/main.py` under the PG app prefix (follow existing pattern for how health_router, google_connection_router, offboarding_router are mounted).

### 5. MCP Tool: `create_priority`

Location: `mcp_server/priority_guardian/server.py` (add to existing file)

**Thin wrapper.** Follow the exact pattern of `connect_google_calendar` in this file:

1. `@mcp.tool()` decorator with name, description, annotations
2. `@handle_mcp_errors("create_priority")` decorator
3. `authenticate_request()` → extract user_id, correlation_id
4. `backend_post("/api/priority-guardian/priorities", ...)` with request payload
5. Transform backend response into MCP tool response with `structuredContent` + `assistant_guidance`

**The MCP server does NOT validate input.** It forwards the request as-is. Backend validates.

---

## Tool DESCRIPTION (Controls WHEN LLM Calls)

```
Records a user's declared priority so Priority Guardian can track their time investment against it. The backend assigns a calendar keyword (P1, P2, or P3) — the user tags their Google Calendar events with this keyword so PG knows which hours count toward which priority.

CALL PRECONDITIONS — DO NOT CALL unless ALL are true:
- User has clearly stated a priority name (their exact words — NEVER rephrase or embellish)
- You have confirmed the type (deadline or flexible) based on user's description
- You have gathered ALL required fields for that type (see schema)
- User has confirmed the details are correct

If ANY required field is missing or vague → ask the user. NEVER invent defaults.

ONBOARDING CONTEXT: User is setting up 1–3 priorities. Call this tool once per priority after gathering all fields. After the tool returns, tell the user their assigned calendar keyword and remind them to tag calendar events with it (e.g., "Tag your calendar events with P1 to track time — like 'P1: Design review'").

KEYWORD ASSIGNMENT: The backend assigns the next available keyword automatically. Do not ask the user to choose a keyword. Just communicate the assigned keyword from the response.
```

---

## Tool INPUT_SCHEMA (Quality Gates)

```json
{
  "type": "object",
  "properties": {
    "name": {
      "type": "string",
      "description": "Priority name exactly as stated by user. NEVER invent, rephrase, or embellish. If longer than 100 chars, ask user to shorten. Max 100 chars.",
      "maxLength": 100
    },
    "type": {
      "type": "string",
      "enum": ["deadline", "flexible"],
      "description": "deadline = hard end date (deliverables tracked separately, not part of creation). flexible = ongoing time investment toward a 1-month goal. Determine from user's description — if they mention a due date or launch date, it's deadline. If they mention ongoing effort or habit, it's flexible."
    },
    "deadline": {
      "type": "string",
      "format": "date",
      "description": "REQUIRED when type=deadline. ISO date (YYYY-MM-DD). Must be in the future. Ask user: 'When does this need to be done by?'"
    },
    "weekly_hour_target": {
      "type": "number",
      "description": "REQUIRED when type=flexible. Hours per week. Must be > 0. Ask user: 'How many hours per week do you want to dedicate to this?'",
      "exclusiveMinimum": 0
    },
    "checkpoint_date": {
      "type": "string",
      "format": "date",
      "description": "REQUIRED when type=flexible. ISO date ~1 month from now. When user will evaluate if time investment is paying off. Suggest ~4 weeks from today, confirm with user."
    },
    "desired_result": {
      "type": "string",
      "description": "REQUIRED when type=flexible. Concrete outcome in ~1 month. Must come from user's own words — NEVER invent. If longer than 200 chars, ask user to shorten. Max 200 chars.",
      "maxLength": 200
    }
  },
  "required": ["name", "type"],
  "additionalProperties": false
}
```

---

## Tool Annotations

```json
{
  "readOnlyHint": false,
  "destructiveHint": false,
  "openWorldHint": false
}
```

Security: `{ "securitySchemes": [{ "type": "oauth2", "scopes": ["pg.access"] }] }`

---

## MCP Tool Response Format

The MCP tool transforms the backend response into MCP format with `structuredContent` and `content`:

### Success

```python
{
    "structuredContent": {
        "priority": { ... },  # from backend response data.priority
        "active_priority_count": 1,
        "available_keywords": ["P2", "P3"],
        "assistant_guidance": "..."  # see below
    },
    "content": [
        {
            "type": "text",
            "text": "Created priority: [name] (assigned [calendar_keyword])"
        }
    ]
}
```

### Error

Forward backend error JSON as-is in `structuredContent`, with appropriate `assistant_guidance` for each error type.

---

## `assistant_guidance` Values

**Success (priority created):**
```
Priority created. Tell the user: "[name] is now tracked as [calendar_keyword]."
Remind them: "Tag your calendar events with [calendar_keyword] to track time — for example, '[calendar_keyword]: Meeting name'."

If active_priority_count < 3: Ask "Do you have another priority you'd like to track? You can have up to [3 - count] more."
If active_priority_count == 3: Say "You've set up all 3 priorities. Let me show you your dashboard." Then call get_priorities to render the widget.
```

**Error — MAX_PRIORITIES_REACHED (409):**
```
User already has 3 active priorities. Tell the user they've reached the maximum. If they want to add a new one, they'll need to retire or delete an existing priority first (available in their dashboard).
```

**Error — KEYWORD_CONFLICT (409):**
```
A race condition occurred assigning the keyword. Retry the request — the backend will assign the next available keyword.
```

**Error — VALIDATION_ERROR (422):**
```
Tell the user what's missing or invalid based on the error message. Ask them to provide the correct information. Do not guess or fill in defaults.
```

---

## Unit Tests

Location: `tests/unit/test_pg_priorities.py`

Test the **Pydantic validation model** (`CreatePriorityRequest`) in isolation — no DB, no HTTP:

1. **Type-conditional required fields:**
   - Deadline type with `deadline` date → valid
   - Deadline type missing `deadline` → rejected
   - Flexible type with all 3 required fields → valid
   - Flexible type missing `weekly_hour_target` → rejected
   - Flexible type missing `checkpoint_date` → rejected
   - Flexible type missing `desired_result` → rejected

2. **Field validation:**
   - `deadline` date in the past → rejected
   - `checkpoint_date` in the past → rejected
   - `weekly_hour_target` = 0 → rejected
   - `weekly_hour_target` < 0 → rejected
   - `name` empty string → rejected
   - `name` exceeds 100 chars → rejected
   - `desired_result` exceeds 200 chars → rejected

3. **Enum validation:**
   - `type` not in ["deadline", "flexible"] → rejected

---

## Integration Tests

Location: `tests/integration/test_pg_priorities_integration.py`

Test the **full endpoint** with test DB:

1. **Happy path — deadline priority:**
   - POST with valid deadline data → 201
   - Response contains priority with correct fields
   - `calendar_keyword` is "P1" (first created)
   - `active_priority_count` = 1
   - `available_keywords` = ["P2", "P3"]
   - `available_keywords` reflects post-commit state

2. **Happy path — flexible priority:**
   - POST with valid flexible data → 201
   - Response contains all flexible-specific fields
   - `calendar_keyword` assigned by backend

3. **Keyword auto-assignment order:**
   - Create first priority → gets P1
   - Create second → gets P2
   - Create third → gets P3
   - Verify each response has correct `available_keywords`

4. **Max 3 enforcement:**
   - Create 3 priorities → all succeed
   - Create 4th → 409 with `MAX_PRIORITIES_REACHED`

5. **Auth enforcement:**
   - Request without X-User-ID header → 401
   - Request with invalid (non-UUID) X-User-ID → 401
   - Request with valid header → 201

6. **Validation enforcement:**
   - Deadline type without deadline field → 422
   - Flexible type without desired_result → 422
   - Past deadline date → 422

7. **(Optional) IntegrityError fallback:**
   - Manually insert a priority with P1 keyword for the test user (bypassing the transaction)
   - Attempt to create another priority that would also get P1
   - Assert response is 409 `KEYWORD_CONFLICT`, not 500

8. **(Optional) Idempotency sanity check:**
   - Create a priority → 201
   - Retry exact same payload → second request gets next available keyword (not a conflict), OR if max reached, returns 409
   - Verify no duplicate data or 500 errors

---

## Known Limitations (Acceptable for Inc 02)

1. **No deliverable creation during priority creation.** `pg_deliverables` table exists for schema completeness. Deliverables are added post-onboarding via widget CRUD tools (later increment).
2. **No widget rendering.** `get_priorities` tool (Inc 03) will render the dashboard widget.
3. **No onboarding state tracking.** `pg_onboarding_state` table is a later increment.
4. **Aggregate columns are placeholders.** `streak_count`, `avg_hours_week`, `total_hours_invested` default to 0. No code in Inc 02 reads or writes them. Do not treat as authoritative.
5. **No retirement or deletion flow.** `status` defaults to 'active'. Retirement, deletion, and edit tools are later increments.
6. **No structuredContent with widget rendering.** MCP tool returns JSON for LLM to narrate. Widget rendering comes with `get_priorities` in a later increment.
7. **No version history on priority rows.** Edits overwrite in place. Historical lookback will come from `pg_weekly_snapshots` in a later increment.

---

## Stop Conditions

Inc 02 is DONE when:

- [ ] `pg_priorities` and `pg_deliverables` tables exist (migration runs clean, TIMESTAMPTZ used, `updated_at` auto-updates via `onupdate=func.now()`)
- [ ] Tables use `pg_*` prefix and live in the shared PostgreSQL instance alongside `core_*` tables
- [ ] `POST /api/priority-guardian/priorities` creates priorities with correct type-conditional validation
- [ ] All input validation lives in a single Pydantic model (`CreatePriorityRequest`), router orchestrates only
- [ ] Backend assigns `calendar_keyword` deterministically (P1 → P2 → P3, no client input)
- [ ] Keyword assignment + max-3 check wrapped in a single transaction with `SELECT ... FOR UPDATE` row locking
- [ ] `IntegrityError` from partial unique index caught and mapped to 409 `KEYWORD_CONFLICT` (never 500)
- [ ] `available_keywords` in response computed post-commit from actual DB state
- [ ] Max 3 active priority enforcement returns 409 `MAX_PRIORITIES_REACHED`
- [ ] Partial unique index on `(user_id, calendar_keyword) WHERE status='active'` exists
- [ ] Error responses use consistent status codes: 401 auth, 422 validation, 409 domain conflicts
- [ ] Trust boundary documented in code comments at auth extraction point in MCP server AND backend router
- [ ] Backend router rejects missing/malformed X-User-ID as 401, never accepts user IDs from request body
- [ ] `create_priority` MCP tool registered and visible in `tools/list`
- [ ] MCP tool authenticates JWT and forwards to backend (no validation in MCP layer)
- [ ] MCP tool response includes `structuredContent` with `assistant_guidance`
- [ ] All unit tests pass (Pydantic model validation)
- [ ] All integration tests pass (full endpoint with test DB)
- [ ] MCP Inspector can call `create_priority` with test JWT and get valid response