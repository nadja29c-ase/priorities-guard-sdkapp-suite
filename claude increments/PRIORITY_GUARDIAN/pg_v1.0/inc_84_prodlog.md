# Increment: Ship Priority Guard Suite logs to Better Stack via Python source

## Context

Better Stack source `priority-guard-suite` (Python type) has been created in
the Better Stack workspace. The source token will be provided as a Render
environment variable `BETTER_STACK_SOURCE_TOKEN`.

Today, all suite services log structured JSON to stdout (via structlog →
JSONRenderer). Render captures stdout but does **not** ship it anywhere —
nothing reaches Better Stack. This increment closes that gap by adding a
`logtail.LogtailHandler` to the Python logging pipeline, mirroring the pattern
already in production for Unpack v1.1 (see `apps/unpack/logging_config.py`
in the `fulfilling-productivity` repo for reference — same library,
`logtail-python`, same source-token-from-env-var approach).

The widget-error endpoint (`POST /api/priority-guardian/widget-error`) and
the widget-side reporter (`widgetErrorReporter.ts`) are already in place
and produce structured `widget.client_error` log events. Once this transport
layer ships, those events become visible in Better Stack alongside all
other backend and MCP logs.

This is **observability infrastructure for the backend and PG OpenAI MCP
server**. Once shipped, every `logger.info/warning/error` call from
those two services will be visible in Better Stack. Other services in
the repo (deprecated PG Claude MCP, focused, sharpen, clarity) do not
ship anything until they explicitly call `configure_logging()` — that
is out of scope for this increment.

## Scope

**Two services need to ship logs:**
1. **Backend** (`priorities-guard-sdkapp-suite` Render service)
2. **PG OpenAI MCP server** (`pg.priority-guard.com` Render service)

The PG Claude MCP server (`mcp_server/priority_guardian_claude/`) is
**deprecated and not actively shipping**. Do not modify `server_dupl.py`
in this increment. When PG is eventually submitted to the Claude MCP
Directory and that service is reactivated, the same logging setup must
be applied — note this in the changelog as a follow-up dependency.

Files to edit:
- `pyproject.toml` — add `logtail-python` dependency
- `poetry.lock` — regenerate after dependency change
- `.env.example` — add `BETTER_STACK_SOURCE_TOKEN=` (empty value, for
  documentation only)
- `backend/core/config.py` — **(optional)** may expose
  `BETTER_STACK_SOURCE_TOKEN` as a documented Settings field, but
  shared logging does NOT consume it (reads via `os.getenv` directly).
  Skip unless a backend module other than logging needs to reference
  the value. See R2.
- **NEW: `shared/logging.py`** at repo root — extract `configure_logging`
  here so both backend and MCP server import from a neutral location
  (location chosen for neutrality: not under `backend/` or
  `mcp_server/`, signals shared ownership)
- `backend/core/logging.py` — re-export `configure_logging` from the
  shared module to preserve the existing import path; or update
  `backend/main.py` to import from the new shared location directly
- `mcp_server/priority_guardian/server.py` — call `configure_logging`
  from the shared module inside `create_app()`
- `doc/OPERATIONS_PREDEPLOY.md` — document the new env var and the
  per-service deployment requirement

## What MUST be preserved

The existing logging configuration includes processors that are critical
for compliance:

- `add_correlation_id` — propagates request correlation IDs through async logs
- `scrub_sensitive_data` — redacts OAuth tokens, refresh tokens, client
  secrets, code verifiers, encrypted fields **before logs leave the
  process**. This is a GDPR-critical layer. **Without this scrubber, raw
  OAuth tokens would be shipped to Better Stack on every error.**
- `TimeStamper(fmt="iso")` — ISO 8601 timestamps
- `StackInfoRenderer` and `format_exc_info` — proper exception formatting
- `JSONRenderer` — final JSON serialization

**Do not remove, reorder, or weaken any of these.** The move to the
shared module (R1.5) is a pure relocation — the function bodies stay
identical. The LogtailHandler addition (R3) is purely additive — it
attaches another handler to the root logger; it does not change how
processors run or what they emit.

The integration relies on the fact that structlog's
`stdlib.LoggerFactory()` routes records through stdlib logging. Every
JSON-rendered log line reaches every stdlib root handler — both the
existing `StreamHandler` (stdout) and the new `LogtailHandler`
(Better Stack). Both receive the same already-scrubbed, already-rendered
JSON. R3's verification step ensures this assumption holds in practice,
not just in theory.

## Requirements

### R1 — Add `logtail-python` to dependencies

In `pyproject.toml`, under `[tool.poetry.dependencies]`, add:

```
logtail-python = "^0.3.0"
```

Run `poetry lock` and commit the updated `poetry.lock` together with
`pyproject.toml`. This is required by `OPERATIONS_PREDEPLOY.md` →
"Poetry Lock File Consistency".

### R1.5 — Extract `configure_logging` to a shared module

Currently `configure_logging` and its supporting helpers
(`scrub_sensitive_data`, `add_correlation_id`) live in
`backend/core/logging.py`. The MCP server needs the same setup, but
having `mcp_server/...` import from `backend/core/...` creates a layering
violation (the MCP server should not depend on backend internals).

**Move the following from `backend/core/logging.py` to a new shared
module at `shared/logging.py`** (repo root, alongside `backend/`,
`mcp_server/`, `doc/`):

- `scrub_sensitive_data` (function)
- `add_correlation_id` (function)
- `configure_logging` (function)
- `get_logger` (function)
- `mask_client_id` (function)

Create `shared/__init__.py` (empty) so it's an importable package.

Leave `backend/core/logging.py` as a **thin re-export shim** for
backwards compatibility:

```python
# backend/core/logging.py
"""Backwards-compatible re-exports. All logic lives in shared.logging."""
from shared.logging import (  # noqa: F401
    scrub_sensitive_data,
    add_correlation_id,
    configure_logging,
    get_logger,
    mask_client_id,
)
```

Existing call sites (`backend/main.py`, `backend/apps/.../routers/...`,
etc.) continue working without changes. The MCP server imports directly
from the shared module:

```python
# In mcp_server/priority_guardian/server.py inside create_app()
from shared.logging import configure_logging
configure_logging()
```

**Critical: `shared/logging.py` must not import from `backend/` at all.**
Specifically, do NOT do `from backend.core.config import settings` to
read the Better Stack token — that reintroduces the exact backend
coupling R1.5 exists to remove. See R3 for the correct token-read
pattern (`os.getenv` directly).

This removes the asymmetry, prevents future tangling, and keeps
backend → shared and MCP → shared as clean unidirectional dependencies.

### R2 — Add `BETTER_STACK_SOURCE_TOKEN` to `.env.example` (mandatory)

In `.env.example`, add (with empty value — never commit a real token):

```
# Better Stack log shipping. Get token from Better Stack source settings.
# Leave empty for local dev (logs go to stdout only).
BETTER_STACK_SOURCE_TOKEN=
```

**Do NOT add `BETTER_STACK_SOURCE_TOKEN` to `backend/core/config.py`
Settings.** The shared logging module reads the token directly via
`os.getenv("BETTER_STACK_SOURCE_TOKEN", "")` — see R3. Adding it to
backend Settings would force `shared/logging.py` to import from
`backend.core.config`, reintroducing the backend coupling that R1.5
exists to remove.

**Optional (for code that needs to reference the value elsewhere in the
backend):** if any backend module other than logging needs to read this
env var (e.g., a future health check that reports whether log shipping
is configured), then `backend/core/config.py` may expose it as:

```python
BETTER_STACK_SOURCE_TOKEN: str = ""  # documented; logging reads via os.getenv
```

This is purely documentary — `shared/logging.py` does not consume it.
For this increment, the optional addition is not required; skip it
unless there's a concrete consumer.

### R3 — Wire LogtailHandler into the shared logging module

The `configure_logging()` function lives in `shared/logging.py` (per
R1.5). After the `logging.basicConfig(...)` call, add a conditional
block that:

1. Reads the Better Stack token directly via
   `os.getenv("BETTER_STACK_SOURCE_TOKEN", "")` — **not** via
   `backend.core.config.settings`. The shared module must remain
   independent of backend internals.
2. If non-empty: imports `LogtailHandler` from `logtail`, instantiates it,
   and adds it to `logging.root.handlers` — **wrapped in try/except AND
   guarded for idempotency** (see safety requirements below)
3. If empty: logs an info message that Better Stack shipping is disabled
   (so it's visible in stdout at startup whether shipping is active)

The handler must be added to the **stdlib root logger**, not to structlog
directly. Because the existing structlog setup uses
`structlog.stdlib.LoggerFactory()`, structlog routes records through
stdlib logging. The final `JSONRenderer()` produces a JSON string which
becomes the `LogRecord.msg` passed to every stdlib handler — including
the `LogtailHandler`.

**Verification belongs in tests, not in production startup.** Do NOT
add an inline assertion in `configure_logging()` that checks
`record.msg` shape. Such an assertion would fire on legitimate
non-structlog logs (uvicorn startup messages, sqlalchemy connection
notes, asyncpg events) and crash deploys. The behavioral guarantees
(scrubber runs before LogtailHandler, payload is JSON, sensitive
fields are redacted) are verified by the unit tests in R4.

**Safety requirement 1 — wrap LogtailHandler init in try/except:**

A Better Stack outage, malformed token, network unreachability at boot,
or any other `LogtailHandler` initialization failure MUST NOT prevent
service startup.

**Safety requirement 2 — idempotency guard:**

`configure_logging()` may be called more than once in a process lifetime
(e.g., during test setup, or if both backend `main.py` and MCP
`create_app()` call it independently). Without a guard, each call adds
another `LogtailHandler` to the root logger, multiplying ingestion
volume to Better Stack and inflating costs.

The required pattern combining both safety requirements:

```python
import os

token = os.getenv("BETTER_STACK_SOURCE_TOKEN", "")
if token:
    # Idempotency: skip if a LogtailHandler is already attached
    from logtail import LogtailHandler
    already_attached = any(
        isinstance(h, LogtailHandler) for h in logging.root.handlers
    )
    if already_attached:
        logger.info("logging.betterstack.already_configured")
    else:
        try:
            logtail_handler = LogtailHandler(source_token=token)
            logging.root.addHandler(logtail_handler)
            logger.info("logging.betterstack.enabled")
        except Exception as e:
            # DO NOT raise — service must start even if Better Stack is unreachable.
            # Log the failure so it's visible in stdout (and any other handlers
            # already attached) for diagnostic purposes.
            logger.warning(
                "logging.betterstack.init_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
else:
    logger.info("logging.betterstack.disabled")
```

This makes Better Stack a **best-effort transport**, not a startup
dependency. Failure to ship logs is a degraded mode, not an outage.
And duplicate calls are safe — each process attaches at most one
`LogtailHandler` regardless of how many times `configure_logging()` runs.

### R4 — Verify scrubber and payload shape via unit tests

After the change, write a unit test (`tests/unit/shared/test_logging_with_logtail.py`)
covering:

1. **Scrubber runs before LogtailHandler:** mock `logtail.LogtailHandler`
   to capture `LogRecord` objects. Log a structlog event containing a
   fake `access_token` field. Assert the captured `record.msg` is a
   JSON string and contains `[REDACTED]`, not the raw token value.

2. **Payload is JSON, not Python dict:** for any application-level
   structlog event reaching the handler, assert `record.msg` is a
   string and parses as valid JSON via `json.loads(record.msg)`.
   This is the verification that R3 explicitly does NOT do at runtime
   (because it would crash on legitimate non-structlog logs); it
   belongs here in tests where we control which logger fires.

These two assertions are the safety net against accidentally shipping
tokens to Better Stack and against silent regressions in the structlog
→ stdlib bridge. **Both must pass before deploy.**

### R5 — MCP server logging setup

The MCP server (`mcp_server/priority_guardian/server.py`) currently calls
`structlog.get_logger(__name__)` at module level with no prior structlog
configuration. This means structlog uses its built-in default
configuration — no JSON output, no scrubber, no correlation IDs, and
no LogtailHandler.

Add a call to `configure_logging()` (imported from the shared module
created in R1.5) inside the `create_app()` function in the MCP server,
before any other imports/setup that might produce log output. This
applies the same processors and the LogtailHandler to MCP server logs.

**Critical fast-startup contract — placement is mandatory, not advisory:**

The MCP server has an explicit fast-startup contract documented in its
own source comments:

> "All heavy imports are done here (not at module level) so that uvicorn
> can bind to the port quickly before loading dependencies. This is
> critical for Render's free tier port scan timeout."

The `configure_logging()` call and its `from shared.logging import
configure_logging` statement MUST be placed **inside `create_app()`**,
NOT at module top-level. Placing it at module top would:
- Force the shared logging module (and its transitive imports including
  pydantic settings, structlog, the scrubber, etc.) to load at module
  import time
- Break the port-bind window
- Risk Render marking the service as failed-to-start during deploy

Verify this constraint after the change by checking that:
- `python -c "import mcp_server.priority_guardian.server"` completes in
  under ~200ms (use `time` to measure)
- The first log line produced after server startup uses the configured
  JSON format, not structlog defaults

Use the import path `from shared.logging import configure_logging`
consistently in both backend and MCP server.

### R6 — Update `OPERATIONS_PREDEPLOY.md`

Add a new section "Better Stack Log Shipping" documenting:
- The env var `BETTER_STACK_SOURCE_TOKEN` is required on **two Render
  services** currently: backend (`priorities-guard-sdkapp-suite`) and
  PG OpenAI MCP (`pg.priority-guard.com`). Each runs as a separate
  process and needs the env var set independently — Render does not
  propagate env vars across services.
- The token is in the team's password manager / Better Stack source
  settings (do not document the actual value).
- If the env var is unset, the service runs normally but logs only to
  stdout — fine for local dev, not desired in production.
- Pre-deploy verification: after setting the env var, restart each
  service and verify in Better Stack live tail that the
  `logging.configured` startup log appears within ~30 seconds.
- **Deferred services (apply when reactivated):** the PG Claude MCP
  server (`mcp_server/priority_guardian_claude/`) is currently
  deprecated. When PG is submitted to the Claude MCP Directory and
  this service is reactivated, `BETTER_STACK_SOURCE_TOKEN` must also
  be set on it — and `server_dupl.py` must have the same
  `configure_logging()` call added inside its `create_app()` (mirroring
  R5). Cross-reference this with the existing Schema Change Checklist
  "Resuming a suspended Render service" section.
- Same applies to any future MCP service in the suite (Focused,
  Sharpen, MindSort, etc.).

## Out of scope

- Better Stack alerts, views, or dashboards (these are configured in the
  Better Stack UI, not in code)
- Render workspace-level log streaming (the Python-source approach
  bypasses this entirely)
- Migrating any non-PG service (Unpack already has its own setup; do not
  touch it)
- Removing the existing `python-json-logger` dependency (still used
  elsewhere; leave it in place)

## Implementation Approach

Read these files before making changes:
1. `apps/unpack/logging_config.py` from the `fulfilling-productivity` repo
   — reference pattern for `LogtailHandler` integration (use as inspiration
   only; do not copy structure verbatim — PG's existing setup is more
   sophisticated)
2. The current `backend/core/logging.py` — preserve every existing
   processor when moving to the shared module
3. `backend/main.py` — verify `configure_logging()` is called before any
   other code that might log; the call site stays the same after the
   shared-module move (the re-export shim handles backwards compatibility)

Order of operations:
1. R1.5 first: extract logging code to shared module, add re-export shim
   in `backend/core/logging.py`. Verify backend still works (run unit
   tests, start the backend locally).
2. R1, R2: dependency + `.env.example` documentation entry. Do NOT
   add the token to `backend/core/config.py` Settings (R2 mandates
   `os.getenv` instead).
3. R3: add LogtailHandler block to `shared/logging.py`. **Do not add
   any runtime assertions** — payload shape verification belongs in
   unit tests (R4), not in production startup code.
4. R4: scrubber + payload-shape tests. Must pass before continuing.
5. R5: wire `configure_logging` into the MCP server's `create_app()`.
   Verify fast-startup contract.
6. R6: docs.

Apply changes additively. Do not remove or reorder existing structlog
processors. Do not change log levels, formatters, or the JSONRenderer.
The only behavioral change is "logs that previously went to stdout now
also go to Better Stack."

## Pre-Deploy Checks

Before pushing:

1. **Read `doc/OPERATIONS_PREDEPLOY.md`** in full and complete all listed
   pre-deploy tasks (Alembic head check, Poetry lock consistency, etc.).
2. Run `poetry lock` and verify `poetry.lock` is updated and committed
   alongside `pyproject.toml`.
3. Run all unit tests: `pytest tests/unit/`. The new scrubber and
   payload-shape tests under `tests/unit/shared/` must pass.
4. **Verify safety guards are in place:**
   - Read the LogtailHandler init block in `shared/logging.py` (or
     wherever R1.5 placed it) and confirm it is wrapped in `try/except`
     with `logger.warning(...)` on failure (R3 safety requirement). A
     bare `LogtailHandler(...)` call without try/except is a red flag
     and must be fixed before deploy.
   - Confirm the idempotency guard is present (the
     `any(isinstance(h, LogtailHandler) ...)` check). Without it,
     repeated `configure_logging()` calls multiply Better Stack volume.
   - Read the top of `mcp_server/priority_guardian/server.py` and
     confirm `from shared.logging import configure_logging` is NOT at
     module level. It must be inside `create_app()`. Module-level import
     breaks the fast-startup contract.
   - Time the MCP server module import:
     ```
     time python -c "import mcp_server.priority_guardian.server"
     ```
     Should complete in under ~200ms. If significantly slower than
     before this change, R5's fast-startup contract was violated.
   - Confirm `backend/core/logging.py` is now a thin re-export shim
     and that all existing call sites (`backend/main.py`, routers, etc.)
     still resolve their imports correctly.
5. Local smoke test: set `BETTER_STACK_SOURCE_TOKEN=<test-token>` in
   local `.env`, start the backend, hit `/api/priority-guardian/health`,
   verify in Better Stack live tail that the request log appears within
   ~30 seconds. Then unset the token, restart, and verify the startup
   log says "Better Stack shipping disabled" and no logs ship.
6. **Verify graceful degradation (loose smoke test):** set
   `BETTER_STACK_SOURCE_TOKEN` to an obviously invalid value (e.g.,
   `BROKEN_TOKEN_FOR_TEST`), restart the backend, and verify only:
   - The service starts successfully (no startup crash)
   - Stdout logging continues normally
   - Hitting the health endpoint returns 200

   Do **not** assert that `logging.betterstack.init_failed` appears.
   `LogtailHandler` may accept a malformed token at construction time
   and only fail later when shipping — that's `logtail-python`'s
   internal behavior, not something we control. The deterministic
   verification of the safety guard happens in the unit tests (R4 +
   the dedicated graceful-degradation unit test in the test list
   below), where we mock `LogtailHandler.__init__` to raise and assert
   `configure_logging()` does not re-raise. This smoke test is just a
   sanity check that the real-world path doesn't crash.

After deploy to each Render service:

7. Set `BETTER_STACK_SOURCE_TOKEN` env var on **both Render services**:
   - `priorities-guard-sdkapp-suite` (backend)
   - PG OpenAI MCP server (`pg.priority-guard.com`)
   Each needs the env var set independently — Render does not propagate
   env vars across services. Do **not** set this on the deprecated PG
   Claude MCP service.
8. Restart each service and verify in Better Stack live tail that the
   `logging.betterstack.enabled` startup event appears for each service
   within 30 seconds of restart. The `service` field in the log entry
   should distinguish them (`priority-guardian-backend`,
   `priority-guardian-mcp`).
9. Trigger one widget error per the manual smoke test from the prior
   widget reporter increment, and verify the `widget.client_error`
   event appears in Better Stack with the correct payload.
10. Verify scrubber works in production: trigger any OAuth flow and
    confirm no `access_token` or `refresh_token` values appear in
    Better Stack logs (look for `[REDACTED]` instead).

If any of these post-deploy checks fail, do **not** consider the
increment complete. Revert if necessary and debug.

## Test Separation

**Unit tests** (`tests/unit/shared/test_logging_with_logtail.py`):

- **Scrubber redacts sensitive fields before LogtailHandler receives data.**
  Mock the handler to capture `LogRecord`s; assert the captured `record.msg`
  contains `[REDACTED]` not the raw token value. (GDPR safety net — must pass.)
- **Payload reaching handler is a JSON string, not a Python dict.**
  For an application-level structlog event, assert `record.msg` is a
  string and `json.loads(record.msg)` succeeds. (Verifies the structlog
  → stdlib bridge works as documented.)
- LogtailHandler is added when `BETTER_STACK_SOURCE_TOKEN` env var is set.
- LogtailHandler is NOT added when the env var is empty/unset.
- Existing structlog processors still run (correlation_id, timestamp,
  JSON renderer).
- **Idempotency:** calling `configure_logging()` twice with the same
  token attaches exactly one `LogtailHandler` to the root logger, not
  two. Use `logging.root.handlers` count check before/after.
- **Graceful degradation (deterministic):** mock
  `LogtailHandler.__init__` to raise an exception. Confirm
  `configure_logging()` does not re-raise, the
  `logging.betterstack.init_failed` warning is logged, and
  `logging.root.handlers` does not contain a `LogtailHandler`. **This
  is the test that proves the safety guard works** — the loose smoke
  test in pre-deploy step 6 is just a sanity check, not a verification.
- **No backend coupling:** verify `shared/logging.py` imports nothing
  from `backend.*`. Either by code review at PR time, or by a simple
  test that reads `shared/logging.py` as text and asserts no line
  matches `from backend` or `import backend` (or, equivalently, walks
  the module's AST imports). Token is read via
  `os.getenv("BETTER_STACK_SOURCE_TOKEN", "")`, not via
  `backend.core.config`.

**Integration tests** — none required. Better Stack is an external
service; mocking it at the integration level adds noise without value.
The unit tests above cover all failure modes that matter (PII leak,
duplicate handlers, init failure, payload shape). Real-world correctness
is verified via the manual post-deploy smoke test in steps 8–10 above.

## Out of scope reminders (do not expand)

- Do not add Better Stack-specific log enrichment (e.g., custom fields
  for Better Stack dashboards). Standard structlog output is sufficient.
- Do not add error retries or buffering for failed Better Stack
  shipments. `logtail-python` handles this internally.
- Do not change Render's log retention or any Render-side configuration.
