# Claude Code Briefing: PG MCP Post-Refactoring Fixes

**Context:** PG MCP server was refactored from FastMCP decorators to canonical manual registry. Refactoring is complete and passing. These are three clean-up fixes identified during review.

**Scope:** Fixes only. No behavioral changes. No new features.

---

## Fix 1: Remove shared/google_tools imports — inline descriptions

### Problem

`connect_google_calendar.py` and `disconnect_google_calendar.py` import description strings from `mcp_server/shared/google_tools.py`:

```python
from mcp_server.shared.google_tools import CONNECT_GOOGLE_CALENDAR_DESCRIPTION
from mcp_server.shared.google_tools import DISCONNECT_GOOGLE_CALENDAR_DESCRIPTION
```

The canonical standard requires each tool file to be fully self-contained: *"Each tool gets one file. That file contains everything about that tool."* Importing metadata from a shared module violates this. The shared module also contains legacy logic with hardcoded `/api/focused/` paths — having PG import from it increases coupling risk.

### What to do

Copy the two description strings into the respective PG tool files as local `DESCRIPTION` constants. Remove the `shared/google_tools` imports from both files. PG should have zero imports from `mcp_server.shared`.

The description values (from `shared/google_tools.py`):

- `CONNECT_GOOGLE_CALENDAR_DESCRIPTION`: "Check Google Calendar connection status. If not connected, returns a secure link to connect your Google Calendar."
- `DISCONNECT_GOOGLE_CALENDAR_DESCRIPTION`: "Disconnect Google Calendar and revoke access tokens. No data is deleted — you can reconnect anytime. Requires confirmation to proceed."

### Validation

- `grep -r "mcp_server.shared" mcp_server/priority_guardian/` returns nothing
- All existing unit and integration tests pass unchanged (descriptions are identical)

---

## Fix 2: Consistent `isError` for CONFIRMATION_REQUIRED

### Problem

In `disconnect_google_calendar.py`, when `confirm=False`, the handler returns:

```python
return mcp_types.CallToolResult(
    content=[...],
    structuredContent={
        "success": False,
        "error": {
            "code": "CONFIRMATION_REQUIRED",
            "message": "..."
        }
    },
)
```

This does NOT set `isError=True`. But in `create_priority.py`, backend error responses (MAX_PRIORITIES_REACHED, KEYWORD_CONFLICT, VALIDATION_ERROR) DO set `isError=True`.

Both are handler-level error returns with `structuredContent` containing an `error` object. The inconsistency means the LLM sees CONFIRMATION_REQUIRED as a "successful" call with error content, while MAX_PRIORITIES_REACHED is an error call with error content.

### What to do

Add `isError=True` to the CONFIRMATION_REQUIRED return in `disconnect_google_calendar.py`. The pattern is: if the response contains `"error"` in `structuredContent`, set `isError=True`.

### Validation

- Update `test_tool_roundtrip.py` `test_requires_confirmation` to assert `result.isError is True`
- All other tests pass unchanged

---

## Fix 3: Add `tool.dispatch.executing` to canonical log events

### Problem

The dispatcher logs `tool.dispatch.received` BEFORE auth (step 1), so it cannot include `correlation_id` — which only exists after auth (step 3). The canonical standard specifies `correlation_id` in `tool.dispatch.received`, which is impossible to satisfy.

The dispatcher already logs `tool.dispatch.executing` after auth with `tool_name`, `user_id`, and `correlation_id`. This is the right workaround, but it's logged at `debug` level and isn't in the canonical event name list.

### What to do

Change `tool.dispatch.executing` from `debug` to `info` level. This is already in `handlers/tools.py`.

No other changes needed in PG. The canonical standard update (adding `tool.dispatch.executing` to the event name list) is a documentation change, not a code change — it will be done separately.

### Validation

- All existing tests pass unchanged (no test asserts on log levels)

---

## Unit Test Instructions

No new unit tests needed. Existing tests cover all three fixes:

- Fix 1: `test_tool_registry.py` validates descriptions are non-empty strings
- Fix 2: `test_tool_roundtrip.py::test_requires_confirmation` — update assertion to check `isError is True`
- Fix 3: No test changes needed

Run: `pytest tests/unit/priority_guardian/ -v`

## Integration Test Instructions

No new integration tests needed. Existing tests validate behavior is unchanged.

Run: `pytest tests/integration/priority_guardian/ -v`