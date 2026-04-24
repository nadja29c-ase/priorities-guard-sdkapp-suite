# Increment 78 — Cross-Device Identity Reconciliation via `openai/subject`

## Revision history

- **v1 (superseded):** reconciliation logic inside `mcp_auth.py` with direct DB access. Violated the architectural invariant "MCP server is stateless, does not access the database." Rejected.
- **v2 (superseded):** moved DB access to backend, used separate `backend/core/services/` directory. Over-engineered; test paths were wrong.
- **v3 (superseded):** inlined reconciliation logic in the router file. Hand-wrote raw SQL in the briefing.
- **v4 (superseded):** rewrote Change 2 to mandate ORM-based queries against real models, added schema-grounding instruction. Fresh-shell defined as "no active Google connection" only — a hole that mis-classifies users with priorities but revoked Google.
- **v5 (superseded):** widened fresh-shell to cover PG-owned state. Split legal/compliance out as an owner-owned pre-publish gate. BUT: kept the endpoint under `backend/core/routers/` while importing `PgPriority` from `backend/apps/priority_guardian/` — a layering violation. Also mixed staging rehearsals into production smoke tests.
- **v6 (this document):** two fixes. (1) Endpoint moved to `backend/apps/priority_guardian/routers/reconcile_router.py`, mounted at `/api/priority-guardian/reconcile-user`. The `core` vs `apps` boundary is respected — "core" no longer imports from an app. (2) Smoke tests split into **post-deploy production smoke tests** (safe, non-invasive) and **pre-prod / staging validation tests** (invasive, includes backend-down and hydrated-collision rehearsals). Do not run staging tests against production.

---

## Context and problem

Priority Guardian's identity model today:

- `/authorize` resolves a user via login_hint → session cookie → new anonymous CoreUser (chain in `_resolve_user_identity`, `authorize.py`).
- ChatGPT never sends login_hint.
- The session cookie is bound to a browser profile.
- JWT `sub` is stamped with the internal CoreUser UUID during `/authorize` and is the authoritative identity at tool-call time.

Consequence: when the same human opens ChatGPT on a second device, the desktop browser has no session cookie, `_resolve_user_identity` falls through to Priority 3 and creates a fresh anonymous CoreUser. The user must re-run OAuth and re-connect Google. Their phone's board is invisible on desktop. Orphan CoreUsers accumulate.

ChatGPT sends `_meta["openai/subject"]` with every authenticated tool call. Empirical testing confirmed the subject is **stable per ChatGPT account across devices** — phone and desktop on the same ChatGPT account produce the same subject value.

OpenAI reference: `_meta["openai/subject"]` — "Anonymized user id sent to MCP servers for the purposes of rate limiting and identification." Source: `developers.openai.com/apps-sdk/reference`. The "don't rely on for authorization decisions" caveat in the reference applies to `openai/userAgent` / `openai/userLocation`, not to `openai/subject`.

This increment uses `openai/subject` as an **identity reconciliation signal** layered on top of the existing OAuth-based identity. The OAuth flow is unchanged. The session cookie path is unchanged. Google connection logic is unchanged. JWT authorization remains the sole gatekeeper.

---

## Architecture-compliant design

**Critical rule: the MCP server does not access the database.** The MCP server is stateless; all persistence lives in the backend. This increment preserves that invariant.

### Why this endpoint belongs under `backend/apps/priority_guardian/`, not `backend/core/`

The reconciliation logic has a PG-specific dependency: the fresh-shell check examines `PgPriority`. That makes the endpoint app-coupled in substance, even though its surface (user_id + openai_subject) looks generic. Putting it under `backend/core/` while importing from `backend/apps/priority_guardian/` reverses the dependency arrow — "core" depends on an app. That's wrong.

**This increment places the endpoint under PG.** If and when MindSort AI (or another app) needs cross-device reconciliation, the right move is one of:

1. A second app-specific endpoint (e.g., `/api/mindsort/reconcile-user`) with MindSort-specific hydration checks, or
2. A refactor to extract a shared `core` reconciliation module that takes app-specific hydration checks as pluggable callbacks.

Either is strictly better than pretending today's endpoint is app-neutral.

**`openai_subject` itself stays on `CoreUser`** because the subject value *is* suite-wide (the same ChatGPT account hits all SDK apps). Only the *reconciliation endpoint* is PG-specific today. Future apps will read/write the same column on the same table.

### Role split

- **MCP server (`mcp_auth.py`):** after JWT validation, read `_meta["openai/subject"]`, call the backend reconciliation endpoint via HTTP, receive the canonical `user_id`, pass it down to the tool handler. No DB access, no SQLAlchemy imports, no new dependencies.
- **Backend (new endpoint `POST /api/priority-guardian/reconcile-user`):** receive `jwt_user_id` and `openai_subject`, run the reconciliation algorithm against `core_users` and PG tables, return the canonical `user_id`.

### Reconciliation algorithm (backend-side)

On every tool call with an `openai/subject` present, after JWT validation on the MCP side, backend receives `(jwt_user_id, openai_subject)` and runs:

1. **Lookup by subject:** find the CoreUser (if any) whose `openai_subject` equals the provided subject. Result: `subject_user_id` (may be `None`).

2. **Case A — no match (`subject_user_id is None`):** first-time bind.
   - Attempt a guarded update: set the target CoreUser's `openai_subject` to the provided value **only if its current `openai_subject` is NULL**. This guard prevents overwriting a subject that a concurrent request just set.
   - If the update affects 1 row → commit, return `jwt_user_id`. Log `reconcile.first_bind`.
   - If the update affects 0 rows → a concurrent request won the race. Re-lookup by subject, fall through to Case B or C with the now-visible row. Do not retry the update.

3. **Case B — match, same user (`subject_user_id == jwt_user_id`):** steady state. No write. Return `jwt_user_id`. Log `reconcile.match`.

4. **Case C — match, different user (`subject_user_id != jwt_user_id`):** cross-device case, requires anomaly guard (below).

### Case C anomaly guard (widened in v5)

The naive rule "subject match → swap user" is unsafe. If the JWT user has meaningful state of any kind, silently swapping can cause cross-user data exposure. The guard:

**Check whether `jwt_user_id` is a "fresh shell":**

A CoreUser is a fresh shell if **ALL** of the following are true:

1. **No active Google connection.** No `CoreConnection` row with `user_id = jwt_user_id AND connection_type = 'google' AND revoked_at IS NULL`.
2. **No Priority Guardian–owned state.** No `PgPriority` row with `user_id = jwt_user_id` (of any `status`, including `'retired'`).

**Why these two and not more:**

- `pg_goals`, `pg_deliverables`, `pg_weekly_snapshots` are all transitively owned through `pg_priorities` (FK `ON DELETE CASCADE`). If there are no priorities, there are no children. Checking priorities is sufficient.
- `core_consents` is **intentionally excluded**. Consent rows are written during the OAuth consent flow before the user has produced any app state. Including consent would make every post-OAuth user non-remappable and defeat the cross-device case.
- `core_tool_audit_log` is not a signal of "state the user owns." It's a compliance artifact that persists through user deletion by design. Excluded.

**Why "of any status" (not just active):**

A user who retired all their priorities still has real historical data. Remapping them to a colliding subject would hide that history. Treat retired priorities as hydrated state.

**Branch:**

- **C1 — JWT user is a fresh shell (no active Google connection AND no priorities):** expected cross-device flow. Return `subject_user_id`. Log `reconcile.cross_device` with `jwt_user_id`, `canonical_user_id`, `subject`. Do NOT merge data, do NOT delete the JWT user — existing 6-month GDPR cleanup reaps it.

- **C2 — JWT user is hydrated (has active Google connection OR any priorities):** ambiguous collision. **Do not swap.** Return `jwt_user_id`. Log `reconcile.ambiguous_collision` at ERROR level with both user IDs, the subject, and which signal triggered the hydrated branch (`has_google_connection` / `has_priorities`). Must be alerted on in Better Stack.

The guard exists because `openai/subject` is request metadata, not a cryptographic claim. OAuth token verification is the authorization gatekeeper; subject reconciliation is a convenience layer. It must never override OAuth by remapping a hydrated user based solely on a client-supplied hint.

### Architectural rule: the fresh-shell check is a permanent invariant

**Whenever a new PG-owned table is added that represents meaningful user state, the fresh-shell check must be extended to cover it.** Missing a table here silently widens the remap blast radius.

- Add a docstring in `_reconcile_user_by_subject` listing the tables currently checked and the rule for when to extend.
- Add an entry to `OPERATIONS_PREDEPLOY.md` under the schema-change checklist: "Adding a new PG-owned table? Extend the fresh-shell check in `reconcile_router.py`."

### What flows back to the MCP server

Backend returns `{"user_id": "<canonical uuid>", "case": "A|B|C1|C2"}`. MCP server uses `user_id` for downstream calls and logs the `case` for observability.

---

## Files to modify

### Backend

- `backend/core/models.py` — add `openai_subject` column to `CoreUser`.
- `backend/alembic/versions/<new>_add_openai_subject_to_core_users.py` — migration.
- `backend/apps/priority_guardian/routers/reconcile_router.py` — **new file** — router + reconciliation logic inline.
- `backend/main.py` — one-line import + `include_router` with prefix `/api/priority-guardian`.

### MCP server

- `mcp_server/priority_guardian/mcp_auth.py` — add call to backend reconciliation endpoint after JWT validation. No DB access.
- `mcp_server/priority_guardian/http_client.py` — add one new helper `reconcile_user()`.

### Tests

- `tests/unit/priority_guardian/test_reconcile_router.py` — **new file** — unit tests for the reconciliation algorithm (uses `async_session` fixture from `tests/conftest.py`).
- `tests/integration/priority_guardian/test_reconcile_endpoint.py` — **new file** — end-to-end HTTP tests.
- `tests/unit/mcp_pg/test_mcp_auth.py` — update to cover the reconciliation call path.
- (If the `tests/unit/priority_guardian/` and `tests/integration/priority_guardian/` directories do not yet exist, create them. They mirror the code layout.)

### Owner-owned (NOT in the Claude Code increment)

See "Pre-publish release gate" section below.

---

## What does NOT change

- `backend/core/oauth_provider/authorize.py` — identity resolution chain untouched.
- `backend/core/oauth_provider/consent_ui.py` — session cookie handling untouched.
- `backend/core/oauth_provider/services/session_service.py` — session cookie unchanged.
- `backend/core/oauth_provider/services/consent_service.py` — auth code creation unchanged.
- `backend/core/repositories/google_connection_repo.py` — Google connection still keyed on `(user_id, provider)`.
- `backend/core/google_oauth.py` / `google_token_management.py` — untouched.
- Token exchange flow — untouched.
- JWT signing, claims, validation logic — untouched.
- `handlers/tools.py` — no change; dispatcher pipes `user_id` to the tool handler as today.
- All tool handler files — no change.

---

## Change 1 — Schema migration

### `CoreUser` model (`backend/core/models.py`)

Add one column. **Use only `nullable=True` on the column declaration.** Do NOT add `unique=True` or `index=True` — uniqueness is enforced by the partial unique index in the migration.

```python
openai_subject: Mapped[str | None] = mapped_column(
    String(128),
    nullable=True,
    comment="Anonymized ChatGPT user id from _meta['openai/subject']. "
            "Used as cross-device identity anchor. NULL for users who have "
            "not yet made a tool call post-Inc 78 deploy, or for CoreUsers "
            "superseded by reconciliation. Uniqueness enforced by partial "
            "index (see migration). Suite-wide field — not PG-specific."
)
```

Length 128: documented format is `v1/<uuid>` (~40 chars). Reserve headroom for future version prefixes.

### Migration

1. **Run `alembic heads` first to determine the current head.** Do NOT infer the down_revision from filename alphabetical order — migration files use hash-based IDs.
2. Create a new Alembic revision with `down_revision` set to the actual current head.
3. Migration filename: follow the existing pattern (hash_snake_case_description).

Upgrade:
```python
op.add_column(
    'core_users',
    sa.Column(
        'openai_subject',
        sa.String(128),
        nullable=True,
        comment="Anonymized ChatGPT user id from _meta['openai/subject']. "
                "Used as cross-device identity anchor."
    )
)
op.create_index(
    'ix_core_users_openai_subject',
    'core_users',
    ['openai_subject'],
    unique=True,
    postgresql_where=sa.text('openai_subject IS NOT NULL'),
)
```

Downgrade: drop index, drop column.

### Backfill

**No explicit backfill.** The algorithm backfills lazily on each user's first tool call post-deploy (Case A — first-time bind).

---

## Change 2 — Backend: reconcile router + logic (in the PG app layer)

### Ground the implementation in the real schema

**Before writing a single line of the reconciliation function, read `backend/core/models.py` AND `backend/apps/priority_guardian/db_models.py` end-to-end** and confirm the fields the algorithm depends on actually exist with the semantics described below. The code is the single source of truth. If anything in this section contradicts the current model files, the model files win — flag the discrepancy back to the owner instead of proceeding.

Schema facts to be verified in the models before implementing:

1. `CoreUser` has a UUID `id` primary key and (after this increment's migration) an `openai_subject` column.
2. `CoreConnection` has: a nullable FK `user_id` → `core_users.id`, a `connection_type` string field (allowed values include `"google"`), a nullable `revoked_at` timestamp.
3. `PgPriority` has a non-nullable FK `user_id` → `core_users.id` with `ON DELETE CASCADE`.

If any of those don't match the current models, stop and flag. Do not work around it.

### No raw SQL — use the ORM exclusively

All DB access in this function must be through SQLAlchemy ORM. Do NOT write `text(...)` SQL strings or raw string queries. Canonical reference patterns:

- **Lookup by column:** `backend/core/oauth_provider/services/session_service.py::get_session_user`.
- **Guarded update with affected-row count:** same file, the sliding-window update — `update(Model).where(...).values(...)` via `db.execute(...)`, then inspect `result.rowcount`.
- **Existence check:** `backend/core/oauth_provider/consent_ui.py::_resolve_user_identity`, or `sqlalchemy.exists` / `select(exists().where(...))`.
- **Concurrent-insert race handling:** see the `IntegrityError` / rollback / re-SELECT pattern in `authorize.py::_resolve_user_identity`.

Use `sqlalchemy.select`, `sqlalchemy.update`, `sqlalchemy.exists` as needed. The service function never calls `session.execute(text(...))`.

### `backend/apps/priority_guardian/routers/reconcile_router.py` (new file)

Single-file module containing:

- the FastAPI router
- Pydantic request/response models
- the reconciliation function (inline, not in a separate service file)

Follow the structure of `backend/apps/priority_guardian/routers/offboarding_router.py` for imports, decorators, and the `Depends(verify_internal_call)` pattern.

### Router setup

- Router tag: `["priority-guardian-reconcile"]`.
- Router-level dependency: `Depends(verify_internal_call)` from `backend.apps.priority_guardian.dependencies` (or wherever PG's `verify_internal_call` currently lives — match what `offboarding_router.py` imports). Enforces `X-Internal-Secret` header.
- Mount in `main.py`: `app.include_router(pg_reconcile_router, prefix="/api/priority-guardian")`. Full path: `POST /api/priority-guardian/reconcile-user`.
- **No `X-User-ID` header on this endpoint.** The whole point is to resolve the canonical user_id — the caller doesn't yet have one.

### Request / response models

```python
class ReconcileUserRequest(BaseModel):
    jwt_user_id: UUID
    openai_subject: str = Field(min_length=1, max_length=128)

class ReconcileUserResponse(BaseModel):
    user_id: UUID
    case: Literal["A", "B", "C1", "C2"]
```

### Endpoint handler

1. Inject `AsyncSession` via `Depends(get_db)`.
2. Extract `correlation_id` from `request.state.correlation_id`.
3. Call `_reconcile_user_by_subject(db, req.jwt_user_id, req.openai_subject, correlation_id)`.
4. Return `ReconcileUserResponse(user_id=..., case=...)`.

On any unexpected exception, log and re-raise — FastAPI returns 500. MCP server treats 5xx as reconciliation failure (see Change 3).

### Reconciliation function signature

```python
async def _reconcile_user_by_subject(
    db: AsyncSession,
    jwt_user_id: UUID,
    openai_subject: str,
    correlation_id: str,
) -> tuple[UUID, Literal["A", "B", "C1", "C2"]]:
    """
    Reconcile JWT-stamped user_id to the canonical CoreUser that owns the given
    openai/subject. See Inc 78 briefing for the algorithm spec.

    Fresh-shell invariant (see Inc 78 briefing, Case C anomaly guard):
    A CoreUser is a fresh shell ONLY when BOTH are true:
      - no active (non-revoked) CoreConnection with connection_type='google'
      - no PgPriority of any status
    When new PG-owned state tables are added, extend the check here.

    Uses the ORM against CoreUser, CoreConnection, and PgPriority models.
    See session_service.py for the canonical patterns.
    """
```

### Algorithm implementation notes (ORM-grounded)

**Step 1 — lookup by subject.** Use `select(CoreUser.id).where(CoreUser.openai_subject == openai_subject)`. Get `scalar_one_or_none()` → `subject_user_id`.

**Step 2 — Case A (subject_user_id is None).** Issue a guarded `update(CoreUser)` with `where(CoreUser.id == jwt_user_id, CoreUser.openai_subject.is_(None))` and `values(openai_subject=openai_subject)`. Execute, commit, inspect `result.rowcount`:
- `rowcount == 1` → log `reconcile.first_bind`, return `(jwt_user_id, "A")`.
- `rowcount == 0` → concurrent write won the race. Log `reconcile.race_lost`. Re-run Step 1 and fall through to Step 3/4.

**Step 3 — Case B (subject_user_id == jwt_user_id).** No write. Log `reconcile.match`. Return `(jwt_user_id, "B")`.

**Step 4 — Case C (subject_user_id != jwt_user_id).** Two independent existence queries:

- **Has active Google connection?** `select(exists().where(CoreConnection.user_id == jwt_user_id, CoreConnection.connection_type == "google", CoreConnection.revoked_at.is_(None)))` → bool.
- **Has any priority?** `select(exists().where(PgPriority.user_id == jwt_user_id))` → bool.

Then branch:

- If BOTH False → **C1 fresh shell.** Log `reconcile.cross_device` with `jwt_user_id`, `canonical_user_id=subject_user_id`, `subject`. Return `(subject_user_id, "C1")`.
- Else → **C2 ambiguous.** Log `reconcile.ambiguous_collision` at ERROR level including both `has_google_connection` and `has_priorities` flags. Return `(jwt_user_id, "C2")`.

### Log events (structlog)

- `reconcile.first_bind` — INFO — fields: `jwt_user_id`, `subject`
- `reconcile.match` — DEBUG — fields: `user_id`
- `reconcile.cross_device` — INFO — fields: `jwt_user_id`, `canonical_user_id`, `subject`
- `reconcile.ambiguous_collision` — ERROR — fields: `jwt_user_id`, `subject_user_id`, `subject`, `has_google_connection` (bool), `has_priorities` (bool)
- `reconcile.race_lost` — INFO — fields: `jwt_user_id`, `subject`

All exceptions propagate. Do not swallow DB errors.

### `backend/main.py`

Add one import and one `include_router` call with prefix `/api/priority-guardian`. Place near the other PG routers in the "Priority Guardian SDK app routers" section. No other changes.

---

## Change 3 — MCP server: call the reconciliation endpoint

### `mcp_server/priority_guardian/http_client.py`

Add one helper. Distinct from `backend_get`/`backend_post` because it does NOT have a canonical `user_id` to put in `X-User-ID`.

```python
async def reconcile_user(
    jwt_user_id: str,
    openai_subject: str,
    correlation_id: str,
) -> dict:
    """
    Call the backend reconciliation endpoint to resolve the canonical user_id
    for a given (jwt_user_id, openai_subject) pair.

    Called BEFORE tool dispatch. Unlike backend_get/backend_post, this endpoint
    does not accept X-User-ID because its purpose is to produce one.

    Returns dict with 'user_id' (str) and 'case' (str).
    Raises httpx.HTTPStatusError on backend error.
    """
```

Implementation mirrors `backend_post` but:
- URL: `{BACKEND_URL}/api/priority-guardian/reconcile-user`.
- Headers: `X-Internal-Secret` (if set) and `X-Correlation-ID`. Do NOT include `X-User-ID`.
- Body: `{"jwt_user_id": jwt_user_id, "openai_subject": openai_subject}`.
- Timeout: 4 seconds (short — reconciliation is on the critical path of every tool call).

### `mcp_server/priority_guardian/mcp_auth.py`

Add one helper function and one integration point.

```python
async def reconcile_user_via_backend(
    jwt_user_id: str,
    meta: Optional[Dict[str, Any]],
    correlation_id: str,
) -> str:
    """
    Reconcile JWT-resolved user_id against openai/subject by calling the backend.

    MCP server does not access the DB. All reconciliation state lives in the backend.

    Returns the canonical user_id. Falls back to jwt_user_id if:
    - subject is absent or empty
    - backend call fails (degrade gracefully — do not block the tool call)

    Does NOT raise on backend failure — logs at WARNING and returns jwt_user_id
    unchanged. Reconciliation failure must not break tool execution.
    """
```

Implementation:

1. `subject = (meta or {}).get("openai/subject")`. If falsy → log `auth.reconcile.subject_absent` at DEBUG, return `jwt_user_id`.
2. Call `reconcile_user(jwt_user_id, subject, correlation_id)` inside try/except.
3. On success: log `auth.reconcile.result` at INFO with `case`, `jwt_user_id`, `canonical_user_id=response["user_id"]`. Return `response["user_id"]`.
4. On any exception: log `auth.reconcile.backend_failed` at WARNING with the error. Return `jwt_user_id` unchanged. **Do not raise.**

### Integration in `authenticate_request`

Insert between JWT validation (Step 4) and scope enforcement (Step 5):

```python
validated = await validate_jwt(token, correlation_id)

user_id = validated["user_id"]
scopes = validated["scopes"]
jti = validated["jti"]
azp = validated["azp"]

# Inc 78: reconcile JWT user_id against openai/subject for cross-device continuity.
# MCP server stays stateless — reconciliation happens in the backend.
user_id = await reconcile_user_via_backend(user_id, meta, correlation_id)

# Step 5: Enforce tool-specific scopes
enforce_tool_scope(tool_name, scopes, correlation_id)
```

### Integrity requirements

- Reconciliation called ONLY after JWT validation succeeds. Never before.
- Backend call timeout is 4s. Reconciliation failure does not block tool execution.
- JWT remains the authorization gatekeeper. `openai/subject` is used only to select which CoreUser to operate on among those this ChatGPT account legitimately owns.

---

## Change 4 — JWT stays authoritative for authorization

`openai/subject` is NOT cryptographically verified. It is a client-supplied hint. Reconciliation uses it only to redirect reads/writes to a different CoreUser that the same ChatGPT account already owns. The anomaly guard (Case C2) prevents redirecting to a hydrated user. OAuth authorization is preserved.

Never grant access or escalate privilege based on `openai/subject` alone. JWT validation remains the gatekeeper.

---

## Unit tests

### `tests/unit/priority_guardian/test_reconcile_router.py` (new)

Use `async_session` fixture from `tests/conftest.py`. Cover every branch of `_reconcile_user_by_subject`:

- **`test_case_a_first_bind_new_subject`** — no CoreUser has subject S. Call with jwt_user_id=X stamps X.openai_subject=S. Returns (X, "A").
- **`test_case_a_race_lost_falls_through_to_b`** — simulate: UPDATE affects 0 rows. Re-SELECT finds the row stamped by the other request. Returns (X, "B").
- **`test_case_b_match_same_user`** — CoreUser(X, openai_subject=S) exists. Call with jwt_user_id=X, subject=S. Returns (X, "B"). No write.
- **`test_case_c1_fresh_shell_returns_canonical`** — CoreUser(A, openai_subject=S) with Google connection. CoreUser(B, openai_subject=NULL) with NO Google connection and NO priorities. Returns (A, "C1").
- **`test_case_c2_refuses_swap_when_google_connection_active`** — CoreUser(B) WITH active Google connection, NO priorities. Returns (B, "C2"). Log: `has_google_connection=True`, `has_priorities=False`.
- **`test_case_c2_refuses_swap_when_priorities_exist`** — CoreUser(B) with NO active Google connection BUT one active PgPriority. Returns (B, "C2"). Log: `has_google_connection=False`, `has_priorities=True`. **Exercises the widened guard.**
- **`test_case_c2_refuses_swap_with_retired_priorities_only`** — CoreUser(B) has NO active Google connection but has a PgPriority with `status='retired'`. Returns (B, "C2"). Confirms retired priorities count as hydrated state.
- **`test_case_c1_revoked_google_connection_treated_as_fresh_when_no_priorities`** — CoreUser(B) has Google connection row but `revoked_at IS NOT NULL`, NO priorities. Returns (A, "C1").
- **`test_db_error_propagates`** — DB raises. Function re-raises.

### `tests/integration/priority_guardian/test_reconcile_endpoint.py` (new)

End-to-end HTTP tests using the `client` fixture from `tests/conftest.py`:

- **`test_endpoint_requires_internal_secret`** — POST without `X-Internal-Secret` → 403.
- **`test_endpoint_rejects_malformed_body`** — missing fields or invalid UUID → 422.
- **`test_full_flow_case_a`** — POST with subject no CoreUser has. Verify DB state after: target CoreUser has openai_subject stamped. Response `{"user_id": X, "case": "A"}`.
- **`test_full_flow_case_c1_cross_device_fresh`** — Hydrated CoreUser_A with subject S and Google connection. Fresh CoreUser_B (no connection, no priorities). POST with jwt_user_id=B, subject=S. Response `{"user_id": A, "case": "C1"}`. B still in DB, unchanged.
- **`test_full_flow_case_c2_priorities_block_remap`** — Hydrated CoreUser_A with subject S. CoreUser_B with no active Google connection BUT with one PgPriority row. POST with jwt_user_id=B, subject=S. Response `{"user_id": B, "case": "C2"}`. Log assertion: `reconcile.ambiguous_collision` fired at ERROR with `has_priorities=True`.

### `tests/unit/mcp_pg/test_mcp_auth.py` (update)

- **`test_authenticate_request_calls_reconcile_when_subject_present`** — mock `reconcile_user` to return `{"user_id": "canonical-uuid", "case": "C1"}`. Verify `auth_context["user_id"]` is `canonical-uuid`.
- **`test_authenticate_request_skips_reconcile_when_subject_absent`** — meta has no openai/subject. Verify `reconcile_user` not called. `auth_context["user_id"]` is the JWT sub.
- **`test_authenticate_request_graceful_degrade_on_backend_failure`** — mock `reconcile_user` to raise `httpx.ConnectError`. Verify `auth_context["user_id"]` is the JWT sub (fallback). Verify `auth.reconcile.backend_failed` log fired at WARNING.

### DB integrity test (standing rule)

- **`test_openai_subject_partial_unique_index`** — insert two CoreUsers with openai_subject=NULL (must succeed). Insert two CoreUsers with openai_subject="v1/abc" (second must fail with unique violation).

Place in `tests/unit/priority_guardian/` alongside the reconcile tests.

---

## Pre-deploy

Read `OPERATIONS_PREDEPLOY.md` before committing.

- Verify single Alembic head: `alembic heads | wc -l` must be `1`.
- Run `alembic upgrade head` locally against test DB first — confirm column + index are created.
- Render pre-deploy runs `alembic upgrade head` on deploy — monitor the log.
- No OAuth discovery changes — discovery verification steps do not apply.

**Deploy order: backend first, then MCP server.** If MCP is deployed first, its reconciliation calls will 404 until backend catches up — gracefully degraded (falls back to jwt_user_id), not broken, but unnecessary.

---

## Pre-prod / staging validation (BEFORE production deploy)

Run these against the staging environment (or a local full-stack setup) before promoting the build to production. These are **invasive** — they deliberately induce failure modes and exercise anomalous states. Do not run them against production.

1. **Backend-down simulation (staging).** Temporarily block `/api/priority-guardian/reconcile-user` on the staging backend (e.g., return 503 via a feature flag, or stop the backend service). Invoke a PG tool via the staging MCP. Expect the tool to still work. Confirm MCP logs: `auth.reconcile.backend_failed` at WARNING, `auth.success` still fires with the JWT-fallback user_id.

2. **Hydrated-collision safety rehearsal (staging).** Seed two staging CoreUsers: User_A with `openai_subject="test-subject-v1"` AND a PgPriority row; User_B with an active Google connection and no priorities. Invoke a tool as User_B with a JWT whose `sub` is User_B's id and meta carrying `openai/subject="test-subject-v1"`. Expect the tool call to run as User_B (no remap). Backend logs: `reconcile.ambiguous_collision` at ERROR with `has_priorities=True`, `has_google_connection=True`. Confirms the widened guard blocks the remap.

3. **Case A → B transition (staging).** Same user invokes tool twice on the same device. First call: case A. Second call: case B. Confirms `openai_subject` is persisted and no duplicate first-binds happen.

If any of these fail, stop the promotion. Fix and re-run. Do not deploy to production until all three pass on staging.

---

## Pre-publish release gate (OWNER responsibility, NOT part of the Claude Code increment)

The code increment is safe to merge and deploy to Render **before** these legal / compliance docs are updated. The migration adds a nullable column; the endpoint is gated by `X-Internal-Secret` and never user-facing; `openai_subject` isn't written until the first tool call through the reconciliation path, which is itself gated by the MCP server being updated. Nothing externally visible changes until the MCP deploy goes live and users invoke tools.

However, **before the new MCP server deploy is made public (i.e., before the Claude/ChatGPT app is announced as cross-device capable in any user-facing channel)**, the owner must complete:

### Privacy policy (`doc/legal/privacy_policy_en.md` and `privacy_policy_de.md`)

Add `openai_subject` to pseudonymous identifiers. Owner writes brand-voice copy. Reference content (neutral starting point, not prescriptive):

> Anonymized ChatGPT user identifier (`openai/subject`) — a pseudonymous identifier provided by ChatGPT with each tool call, used solely to maintain identity continuity across the user's devices. Stored as part of the account record and deleted when the account is deleted.

### Data Retention Strategy document

Add `openai_subject` to the inventory of stored identifiers. Retention rule: tied to `CoreUser` lifecycle.

### Compliance master (`doc/compliance_master_1.3.26.md`)

Add entry under pseudonymous identifier section documenting `openai_subject`, purpose (cross-device continuity), source (ChatGPT `_meta["openai/subject"]`), retention (CoreUser lifecycle).

### Gating rule

The Claude Code increment is **complete** when the code, tests, migration, and production smoke tests pass. The **release is complete** only after the owner has finished the three doc updates above. Do not announce the cross-device feature until both sides are done. No code change blocks on these docs; no user-facing rollout precedes them.

---

## Post-deploy production smoke tests

These run against **production** after the deploy. They are non-invasive and confirm the deploy didn't regress anything. They do NOT deliberately induce failures — that's staging's job.

1. **Existing user, same device.** Open ChatGPT on the device where Google was originally connected. Invoke `get_priorities`. Expect a normal response matching pre-deploy behavior. Backend logs: `reconcile.first_bind` once for this user (first time `openai_subject` is stamped post-deploy).

2. **Same user, second device.** Open ChatGPT on a different device with the same ChatGPT account. Complete OAuth (creates fresh anonymous CoreUser). Invoke `get_priorities`. Expect to see priorities/board from device 1, not empty. Backend logs: `reconcile.cross_device` with `case=C1`. MCP logs: `auth.reconcile.result` with `case=C1`. **This is the success criterion of the whole increment.**

3. **Monitor C2 alerts for the first hour.** Zero `reconcile.ambiguous_collision` events expected in the first hour post-deploy. Any C2 event requires immediate investigation.

Backend-down simulation and hydrated-collision rehearsals are **staging tests**, not production smoke tests. See "Pre-prod / staging validation" section.

---

## Observability

Post-deploy dashboards:

- Counter: `reconcile.*` events by case (A, B, C1, C2). Healthy ratio: A drops off after first week, B dominates, C1 small but present, C2 zero.
- Alert: any `reconcile.ambiguous_collision` (C2) in production. **Must page.** The log includes `has_google_connection` and `has_priorities` flags — use these to triage.
- Alert: sustained `auth.reconcile.backend_failed` rate >1% of calls over 5 minutes.
- Counter: orphan superseded CoreUser count — a CoreUser with no active (non-revoked) Google connection, no priorities, and created more than 30 days ago.

---

## What is explicitly deferred

- **Active deletion of superseded CoreUsers.** 6-month GDPR cleanup catches them.
- **Data merge.** If a user writes data to the fresh-shell CoreUser before reconciliation fires on the first tool call, that data is orphaned. In practice, the widget's first action is `get_priorities` (read tool), which reconciles before any write. Acceptable risk for v1.
- **CMID / future OpenAI identity changes.** Works with today's DCR + `openai/subject`.
- **Generalizing reconciliation across MindSort AI.** MindSort's identity flow is not yet integrated. When it is, either add a parallel endpoint (`/api/mindsort/reconcile-user`) with MindSort-specific hydration checks, or refactor to extract a shared `core` reconciliation module with pluggable hydration callbacks.

---

## Implementation approach — Copy and Adjust, Never Rewrite

For every file touched:

- `backend/core/models.py` — add ONLY the `openai_subject` column to `CoreUser`. Do not refactor other models, columns, indexes, constraints, or comments.
- New migration file — follow exact pattern of most recent migration in `backend/alembic/versions/`.
- `backend/apps/priority_guardian/routers/reconcile_router.py` (new) — follow structure of `backend/apps/priority_guardian/routers/offboarding_router.py` for imports, decorators, dependency pattern. Follow ORM query patterns from `backend/core/oauth_provider/services/session_service.py` and `consent_service.py`. Single-file module with router + Pydantic models + reconciliation function inline. No raw SQL.
- `backend/main.py` — add ONLY the new router import and `include_router` call with prefix `/api/priority-guardian`. Place near other PG routers. Do not reorder or refactor other imports.
- `mcp_server/priority_guardian/http_client.py` — add ONLY the `reconcile_user` helper. Do not change existing `backend_get`/`backend_post`/`backend_put`/`backend_delete` or the `http_client` initialization pattern.
- `mcp_server/priority_guardian/mcp_auth.py` — add ONLY the `reconcile_user_via_backend` helper and the one-line integration into `authenticate_request`. Do not restructure existing function, logging format, or JWT validation logic.

No files require the `_dupl` suffix — this increment's files are app-specific (to PG) or live in `backend/core/models.py` (for the shared `openai_subject` column). The shared-backend `_dupl` pattern applies to files needing per-app copies, which is not the case here.
