# Increment Claude-05: Adapter Size-Based Data Trimming

**Goal:** Fix Claude's inability to process large tool responses by trimming oversized list fields from `content` serialization. Uses a size threshold — not hardcoded field names — so the adapter stays generic and doesn't break tool-specific flows.

---

## Context

Increment Claude-04 serializes all of `structuredContent.data` into `content`. This caused a real failure:

- `render_weekly_report` returns `otherEvents` (23 events) in `data`
- Adapter serialized all 23 events into `content` as JSON
- Claude received a payload too large to process reliably
- Claude reported a "timeout" (misleading — tool returned HTTP 200 in ~700ms)
- Claude fabricated a P1 breakdown rather than admitting it couldn't read the data

**Why hardcoded field names are wrong:**

`get_priority_events` returns `priorityEvents` specifically for Claude to read and group before calling `render_weekly_report` with `semantic_groupings`. If the adapter hardcodes `priorityEvents` as a strip target, that two-call breakdown flow breaks. The adapter must not contain business logic about individual tools.

**Why size-based trimming is correct:**

- `otherEvents`: 23 items → stripped ✅
- `priorityEvents` from `get_priority_events`: typically 4-8 items (confirmed in logs: `priority_event_count=4`) → passes through ✅
- `priorities`, `timeAllocation`, `slices`: compact objects → passes through ✅
- No field name coupling, no tool-specific logic

**One file changes. Nothing else.**

---

## Pre-Implementation

Read `doc/OPERATIONS_PREDEPLOY.md` before starting. No migrations, no backend changes, no tool handler changes.

---

## Implementation Approach — Copy and Adjust, Never Rewrite

`response_adapter_dupl.py` already exists. Make only the listed change to Step 4. Do not restructure, rewrite, or improve anything not listed here.

| File | Action |
|---|---|
| `mcp_server/priority_guardian_claude/response_adapter_dupl.py` | Adjust Step 4 only — add size-based list filtering before data serialization |

---

## Change: `response_adapter_dupl.py`

**Replace the data serialization lines in Step 4 only.**

**Current (Increment Claude-04):**
```python
# Serialize data for Claude's model channel
data = result.structuredContent.get("data")
data_str = json.dumps(data, ensure_ascii=False, indent=2) if data else ""
```

**New:**
```python
# Serialize data for Claude's model channel.
# Strip list fields exceeding MAX_LIST_ITEMS — these are widget-only event arrays
# that Claude does not need for narration. Size threshold is generic: no field
# name coupling, no tool-specific logic. Small lists (e.g. priorityEvents with
# 4-8 items from get_priority_events) pass through so the breakdown flow works.
MAX_LIST_ITEMS = 10
data = result.structuredContent.get("data")

if isinstance(data, dict):
    data_for_claude = {
        k: v for k, v in data.items()
        if not (isinstance(v, list) and len(v) > MAX_LIST_ITEMS)
    }
    data_str = json.dumps(data_for_claude, ensure_ascii=False, indent=2) if data_for_claude else ""
else:
    # data is non-dict (list, primitive, etc) — serialize as-is, no filtering possible
    data_str = json.dumps(data, ensure_ascii=False, indent=2) if data else ""
```

**Nothing else changes.** The rest of Step 4 (parts composition, order, `getattr` guard) stays identical. Steps 1, 2, 3, 5, 6 unchanged. `clean_structured`, `_meta` stripping, and top-level meta passthrough unchanged.

`MAX_LIST_ITEMS` is defined inline in the function — do not make it a module-level constant. The `data_for_claude` dict is a new object — do not mutate `data` in place.

---

## What NOT to Touch

- Any file in `mcp_server/priority_guardian/` — shared tool handlers
- Any file in `backend/`
- Any other file in `mcp_server/priority_guardian_claude/`
- Existing tests — do not modify

---

## Tests

Add to `tests/unit/mcp_pg_claude/test_scaffold.py`. Do NOT replace existing tests.

**1. `test_adapter_strips_large_lists_from_content`**
```python
result = mcp_types.CallToolResult(
    content=[mcp_types.TextContent(type="text", text="Summary.")],
    structuredContent={
        "success": True,
        "data": {
            "priorities": [{"name": "Ship PG"}],
            "otherEvents": [{"title": f"Event {i}"} for i in range(23)],
        },
        "assistant_guidance": "guidance",
    },
)
adapted = adapt_tool_result(result)
# Priority data present — small list passes through
assert "Ship PG" in adapted.content[0].text
# Large event list stripped from content
assert "Event 0" not in adapted.content[0].text
assert "Event 22" not in adapted.content[0].text
# structuredContent.data unchanged — large list still there for any downstream consumer
assert len(adapted.structuredContent["data"]["otherEvents"]) == 23
```

**2. `test_adapter_keeps_small_lists_in_content`**
```python
# Simulates get_priority_events returning 4 priorityEvents — must pass through
result = mcp_types.CallToolResult(
    content=[mcp_types.TextContent(type="text", text="Summary.")],
    structuredContent={
        "success": True,
        "data": {
            "priorityEvents": [
                {"title": "P1: Deep work", "matchedKeywords": ["P1"]},
                {"title": "P1: Planning", "matchedKeywords": ["P1"]},
                {"title": "P1: Review", "matchedKeywords": ["P1"]},
                {"title": "P1: Build", "matchedKeywords": ["P1"]},
            ],
        },
        "assistant_guidance": "Group events and call render_weekly_report.",
    },
)
adapted = adapt_tool_result(result)
# Small list (4 items) passes through — Claude needs these to group
assert "P1: Deep work" in adapted.content[0].text
assert "P1: Build" in adapted.content[0].text
```

**3. `test_adapter_threshold_boundary`**
```python
# Exactly 10 items — should pass through (threshold is > 10, not >= 10)
result = mcp_types.CallToolResult(
    content=[mcp_types.TextContent(type="text", text="Summary.")],
    structuredContent={
        "success": True,
        "data": {"items": [{"id": i} for i in range(10)]},
        "assistant_guidance": "guidance",
    },
)
adapted = adapt_tool_result(result)
assert '"id": 0' in adapted.content[0].text  # 10 items passes through

# 11 items — should be stripped
result2 = mcp_types.CallToolResult(
    content=[mcp_types.TextContent(type="text", text="Summary.")],
    structuredContent={
        "success": True,
        "data": {"items": [{"id": i} for i in range(11)]},
        "assistant_guidance": "guidance",
    },
)
adapted2 = adapt_tool_result(result2)
assert '"id": 0' not in adapted2.content[0].text  # 11 items stripped
```

**4. `test_adapter_handles_non_dict_data`**
```python
# data is a list, not a dict — adapter must not crash
result = mcp_types.CallToolResult(
    content=[mcp_types.TextContent(type="text", text="Summary.")],
    structuredContent={
        "success": True,
        "data": [{"id": 1}, {"id": 2}],
        "assistant_guidance": "guidance",
    },
)
adapted = adapt_tool_result(result)
# No crash — serialized as-is
assert "guidance" in adapted.content[0].text
```

---

## Definition of Done

- [ ] Lists with more than 10 items excluded from `content` serialization
- [ ] Lists with 10 or fewer items pass through into `content`
- [ ] Non-dict `data` handled without crash — serialized as-is
- [ ] Stripped lists remain unchanged in `structuredContent.data`
- [ ] `MAX_LIST_ITEMS = 10` defined inline in the function
- [ ] `data` never mutated in place — new dict created
- [ ] All 4 new tests pass
- [ ] All existing scaffold tests still pass
- [ ] Deploy to Claude Render service and verify: ask "show me my weekly report" — Claude narrates priority names and hours without fabricating or reporting a timeout
- [ ] Ask "break down my P1" — Claude receives `priorityEvents` (4 items) and groups them correctly