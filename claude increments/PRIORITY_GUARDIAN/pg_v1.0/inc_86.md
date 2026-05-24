# Increment: Standardize logging levels for tool failures + add success field to tool.timing

## Context

Two related logging cleanups in PG MCP, done in one increment because they touch
the same dispatcher and tool files:

1. Several user-visible failure events are logged at `level=info` instead of
   `level=warning`. This breaks downstream Better Stack metrics that filter on
   `level IN ('warning', 'error')` to count tool failures, and makes failures
   invisible in Live Tail when filtering by warning level.

2. The `tool.timing` log line is emitted in three branches (success, rejected,
   unexpected_error) but does not include a `success` field, making it
   impossible to distinguish failed calls from successful ones in metrics.

This is a logging-only correction. No behavior change. No control flow change.
No change to event names, structured payloads, message text, or return values.

## Files to change

1. `mcp_server/priority_guardian/handlers/tools.py` (dispatcher)
2. `mcp_server/priority_guardian/tools/create_priority.py`
3. `mcp_server/priority_guardian/tools/inspect_adapt.py`
4. `mcp_server/priority_guardian/tools/get_priority_events.py`
5. `mcp_server/priority_guardian/tools/render_weekly_report.py`
6. `mcp_server/priority_guardian/tools/onboarding_calendar_setup.py`

---

## Change 1: handlers/tools.py — dispatcher

### 1a — `tool.dispatch.rejected` log level

Find:
```python
        logger.info("tool.dispatch.rejected",
                   tool_name=name,
                   correlation_id=correlation_id,
                   reason=str(e))
```

Replace with:
```python
        logger.warning("tool.dispatch.rejected",
                       tool_name=name,
                       correlation_id=correlation_id,
                       reason=str(e))
```

### 1b — Add `success=False` to `tool.timing` in the rejected path

Locate the `tool.timing` log call inside the `except ToolUsageError as e:` block
(immediately after the `tool.dispatch.rejected` log). Add `success=False` as a
keyword argument.

Find:
```python
        logger.info("tool.timing",
                   tool_name=name,
                   correlation_id=correlation_id,
                   auth_ms=round(auth_ms, 1),
                   tool_ms=round(tool_ms, 1),
                   total_ms=round(total_ms, 1),
                   user_id=user_id)

        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=str(e),
            )],
            isError=True,
        )
```

Replace with:
```python
        logger.info("tool.timing",
                   tool_name=name,
                   correlation_id=correlation_id,
                   auth_ms=round(auth_ms, 1),
                   tool_ms=round(tool_ms, 1),
                   total_ms=round(total_ms, 1),
                   user_id=user_id,
                   success=False)

        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=str(e),
            )],
            isError=True,
        )
```

### 1c — Add `success=False` to `tool.timing` in the unexpected_error path

Locate the `tool.timing` log call inside the `except Exception:` block
(immediately after `logger.exception("tool.dispatch.unexpected_error", ...)`).

The `tool.timing` log call appears in three places in this file. This one is
inside the `except Exception:` block — identify by surrounding context (the
preceding `logger.exception("tool.dispatch.unexpected_error", ...)` call), NOT
by occurrence count.

Find:
```python
        logger.info("tool.timing",
                   tool_name=name,
                   correlation_id=correlation_id,
                   auth_ms=round(auth_ms, 1),
                   tool_ms=round(tool_ms, 1),
                   total_ms=round(total_ms, 1),
                   user_id=user_id)
```

Replace with:
```python
        logger.info("tool.timing",
                   tool_name=name,
                   correlation_id=correlation_id,
                   auth_ms=round(auth_ms, 1),
                   tool_ms=round(tool_ms, 1),
                   total_ms=round(total_ms, 1),
                   user_id=user_id,
                   success=False)
```

### 1d — Add success field to `tool.timing` in the success path, derived from result.isError

**This is the most important change in this increment. Read the rationale carefully.**

The dispatcher's success path (after `# Step 9: Log timing`) runs whenever
`tool.handle()` returns a `CallToolResult` directly without raising. That CAN
include `CallToolResult(isError=True)` — multiple PG tools return error results
directly via helpers like `_build_provenance_error()` instead of raising
`ToolUsageError`.

The `success` field MUST reflect the actual error state of the returned result,
NOT just "we got here without an exception." Setting `success=True`
unconditionally on this path would silently misclassify every direct
`isError=True` return as a success, defeating the entire purpose of the
`success` field for the largest category of failures.

Find:
```python
    tool_ms = (time.perf_counter() - start_tool) * 1000

    # Step 9: Log timing
    total_ms = (time.perf_counter() - start_total) * 1000

    logger.info("tool.timing",
                tool_name=name,
                correlation_id=correlation_id,
                auth_ms=round(auth_ms, 1),
                tool_ms=round(tool_ms, 1),
                total_ms=round(total_ms, 1),
                user_id=user_id)

    # Step 10: Return result
    return result
```

Replace with:
```python
    tool_ms = (time.perf_counter() - start_tool) * 1000

    # Step 9: Log timing
    total_ms = (time.perf_counter() - start_total) * 1000

    # success reflects the actual result.isError, not just "no exception was raised"
    # — handlers may return CallToolResult(isError=True) directly without raising
    # (e.g., _build_provenance_error in create_priority.py and inspect_adapt.py,
    # or direct CallToolResult(isError=True) returns in render_weekly_report.py,
    # get_priority_events.py, onboarding_calendar_setup.py)
    success = not getattr(result, "isError", False)

    logger.info("tool.timing",
                tool_name=name,
                correlation_id=correlation_id,
                auth_ms=round(auth_ms, 1),
                tool_ms=round(tool_ms, 1),
                total_ms=round(total_ms, 1),
                user_id=user_id,
                success=success)

    # Step 10: Return result
    return result
```

Note on `getattr(result, "isError", False)`: defensive against the rare case
where `result` lacks the attribute. `CallToolResult` always has it, but using
`getattr` with a default avoids a crash if the type guard upstream is ever
loosened. Returns `False` (treated as success) by default — safer than crashing
the timing log on a malformed result.

---

## Change 2: create_priority.py — promote provenance_failed to warning

There are 8 `logger.info("tool.create_priority.provenance_failed", ...)` call
sites in this file. Change the log method on EVERY occurrence from
`logger.info` to `logger.warning`.

Do NOT change the event name. Do NOT change the kwargs. Do NOT touch the
surrounding return statement (`return _build_provenance_error(...)`) or any
other code.

Pattern to find (repeats 8 times — kwargs vary per site):
```python
        logger.info(
            "tool.create_priority.provenance_failed",
            correlation_id=correlation_id,
            field="<field_name>",
        )
```

Pattern to replace with:
```python
        logger.warning(
            "tool.create_priority.provenance_failed",
            correlation_id=correlation_id,
            field="<field_name>",
        )
```

---

## Change 3: inspect_adapt.py — promote provenance_failed to warning

Same as Change 2, but for `tool.inspect_adapt.provenance_failed`. There are 4
call sites in this file. Change `logger.info` → `logger.warning` on every
occurrence. Do NOT change anything else.

---

## Change 4: get_priority_events.py — promote functional rejections to warning

Two events to promote. Both currently log at `info` but their handler returns
`CallToolResult(isError=True)`. They are user-visible failures.

### 4a — `tool.get_priority_events.breakdown_unavailable`

Find:
```python
        logger.info(
            "tool.get_priority_events.breakdown_unavailable",
            correlation_id=correlation_id,
            user_id=user_id,
            week_start=data.get("week_start"),
            semantic_target=semantic_target,
        )
```

Replace with:
```python
        logger.warning(
            "tool.get_priority_events.breakdown_unavailable",
            correlation_id=correlation_id,
            user_id=user_id,
            week_start=data.get("week_start"),
            semantic_target=semantic_target,
        )
```

### 4b — `tool.get_priority_events.no_priorities`

Find:
```python
        logger.info(
            "tool.get_priority_events.no_priorities",
            correlation_id=correlation_id,
            user_id=user_id,
        )
```

Replace with:
```python
        logger.warning(
            "tool.get_priority_events.no_priorities",
            correlation_id=correlation_id,
            user_id=user_id,
        )
```

---

## Change 5: render_weekly_report.py — promote functional rejections to warning

Two events to promote.

### 5a — `tool.render_weekly_report.semantic_breakdown_unavailable`

Find:
```python
        logger.info(
            "tool.render_weekly_report.semantic_breakdown_unavailable",
            correlation_id=correlation_id,
            user_id=user_id,
            week_start=data.get("week_start"),
        )
```

Replace with:
```python
        logger.warning(
            "tool.render_weekly_report.semantic_breakdown_unavailable",
            correlation_id=correlation_id,
            user_id=user_id,
            week_start=data.get("week_start"),
        )
```

### 5b — `tool.render_weekly_report.no_priorities`

Find:
```python
        logger.info(
            "tool.render_weekly_report.no_priorities",
            correlation_id=correlation_id,
            user_id=user_id,
            week_start=data.get("week_start"),
            is_current_week=data.get("is_current_week"),
        )
```

Replace with:
```python
        logger.warning(
            "tool.render_weekly_report.no_priorities",
            correlation_id=correlation_id,
            user_id=user_id,
            week_start=data.get("week_start"),
            is_current_week=data.get("is_current_week"),
        )
```

---

## Change 6: onboarding_calendar_setup.py — promote functional rejections to warning

Three events to promote. Note that `onboarding.no_connection` and
`onboarding.no_priorities` may appear MULTIPLE times in this file across
different phase handlers — change EVERY occurrence.

### 6a — `onboarding.no_connection` (every occurrence)

Find each occurrence of:
```python
        logger.info(
            "onboarding.no_connection",
            user_id=user_id,
            correlation_id=correlation_id,
        )
```

Replace with:
```python
        logger.warning(
            "onboarding.no_connection",
            user_id=user_id,
            correlation_id=correlation_id,
        )
```

### 6b — `onboarding.no_priorities` (every occurrence)

Find each occurrence of:
```python
        logger.info(
            "onboarding.no_priorities",
            user_id=user_id,
            correlation_id=correlation_id,
        )
```

Replace with:
```python
        logger.warning(
            "onboarding.no_priorities",
            user_id=user_id,
            correlation_id=correlation_id,
        )
```

### 6c — `onboarding.zero_keyword_hours` (every occurrence)

Find each occurrence (kwargs may vary per site):
```python
        logger.info(
            "onboarding.zero_keyword_hours",
            user_id=user_id,
            correlation_id=correlation_id,
            ...
        )
```

Replace with:
```python
        logger.warning(
            "onboarding.zero_keyword_hours",
            user_id=user_id,
            correlation_id=correlation_id,
            ...
        )
```

(Preserve all existing kwargs — only change `logger.info` to `logger.warning`.)

---

## Implementation Approach — Copy and Adjust, Never Rewrite

All changes are single-token edits: `info` → `warning`, or adding one keyword
argument (`success=...`). Make ONLY these listed changes. Do NOT refactor,
restructure, "improve," or reformat any surrounding code. Do NOT touch other
`logger.info` or `logger.warning` calls anywhere in the codebase. Do NOT add
new fields beyond `success`. Do NOT change function signatures, control flow,
or return values.

If a `logger.info(...)` call you encounter is not in the explicit list above,
do NOT change it. Leave all `*.start`, `*.success`, `*.complete`, `*.received`,
`*.executing` and other non-failure events at their current level.

---

## Out of scope

- Any `logger.info` → `logger.warning` changes for events not explicitly listed
- Any change to log event names
- Any new metrics or instrumentation beyond the `success` field on `tool.timing`
- Any change to functional behavior, control flow, or return values
- Adding `success` field to log lines other than `tool.timing`
- Adding logging to the runtime type guard branch (the
  `not isinstance(result, mcp_types.CallToolResult)` path, which currently
  returns without logging timing — separate increment)
- Changes to other PG MCP tools not listed (`get_priorities.py`,
  `get_patterns.py`)

---

## Test instructions

### Unit tests

Run the existing PG MCP unit test suite and confirm all tests pass:

```
cd /Users/nadja/Desktop/Priority Guard Suite/priority-guardian
poetry run pytest tests/ -v
```

No new unit tests required for the logging-level changes themselves — they
have no behavioral impact, and existing tests do not assert on log levels.

If any existing test asserts on the exact kwargs of `tool.timing` log calls,
update the assertion to include `success=True/False` accordingly. Do NOT add
new behavioral assertions.

If any existing test mocks the logger and asserts on call signatures
(`logger.info(...)` vs `logger.warning(...)`) for any of the events listed
in Changes 1a, 2, 3, 4a, 4b, 5a, 5b, 6a, 6b, 6c — update the assertion to
match the new level.

### Integration tests (manual, post-deploy)

After deploy, perform these checks against the deployed MCP server in Better
Stack Live Tail:

1. **Successful tool call → `success=true`**
   - Trigger a `get_priorities` call (or any successful tool).
   - Find the `tool.timing` log line.
   - Confirm `"success": true`.
   - Confirm `"level": "info"`.

2. **ToolUsageError rejection → `success=false`, level warning**
   - Trigger a path that raises `ToolUsageError` (e.g., `inspect_adapt` with
     an invalid `derived_from_id`).
   - Confirm `tool.dispatch.rejected` appears with `"level": "warning"` (was
     `"info"`).
   - Confirm `tool.timing` appears with `"success": false`, `"level": "info"`.

3. **Direct isError=True return (provenance failure) → `success=false`**
   - Trigger a `create_priority` call with empty `user_priority_name_verbatim`.
   - Confirm `tool.create_priority.provenance_failed` appears with
     `"level": "warning"` (was `"info"`).
   - Confirm `tool.timing` appears with `"success": false`, `"level": "info"`.
     **This is the critical case** — the tool returned `isError=True` directly
     via `_build_provenance_error` without raising. `success` MUST be `false`.
     If `success=true` here, change 1d is broken.

4. **Direct isError=True return (functional rejection) → `success=false`**
   - Trigger a `render_weekly_report` call for a user with no priorities, or a
     `get_priority_events` call for a past week.
   - Confirm the corresponding rejection event (`*.no_priorities` or
     `*.breakdown_unavailable`) appears with `"level": "warning"`.
   - Confirm `tool.timing` appears with `"success": false`, `"level": "info"`.

5. **Provenance failure path does NOT skip tool.timing**
   - Confirm test 3 above DID produce a `tool.timing` line. Provenance failures
     in `create_priority.py` and `inspect_adapt.py` return through the
     dispatcher's success path, so `tool.timing` IS emitted (with `success=false`).
     If it's missing, something else has changed — investigate.

6. **Unexpected error path** (cannot easily trigger; verify via code review only)
   - The change is symmetric with the rejected path.

---

## Pre-deployment checklist

Before committing, read `OPERATIONS_PRESUBMISSION.md` and any other
`OPERATIONS_*.md` for PG MCP. Check for additional pre-deploy tasks specific
to PG MCP.

---

## Why this matters

**Without the `success` field on `tool.timing`**, the cleanest "any tool failed"
metric in Better Stack would require unioning multiple disjoint event filters:
unauthorized, forbidden, dispatch.rejected, unexpected_error, provenance_failed
(per tool), backend_error (per tool), timeout (per tool), and several
tool-specific functional rejection events. Easy to miss one. Easy to drift as
new failure modes are added.

**With `success` correctly derived from `result.isError`**, a single Better
Stack metric — `tool.timing AND success=false` — captures all dispatcher-
observed failures regardless of which specific failure mode occurred. New
failure modes are automatically counted as long as they go through the
dispatcher.

**The level corrections** are required for the existing `failures_<tool>` and
umbrella failure metrics that filter on `level IN ('warning', 'error')` to
count provenance/gate rejections at all. Without this fix, those metrics
silently undercount the most common failure mode (LLM calling tool without
verbatim fields populated, or asking for breakdowns of past weeks).

That's the full revised briefing — copy verbatim into your Claude Code session. Two things to verify before you hand it off:

Search for any other logger.info calls I might have missed. I read every file but did so manually; if you want a grep-based double-check, run grep -n "logger.info" mcp_server/priority_guardian/tools/*.py mcp_server/priority_guardian/handlers/*.py and compare against the events listed in this briefing. Anything *.failed, *.rejected, *.unavailable, *.no_*, *.zero_* not on the list deserves a second look.
Check OPERATIONS_PRESUBMISSION.md yourself before deploy — the briefing tells Claude Code to read it, but you should also verify it doesn't have new pre-deploy items relevant to logging changes specifically.