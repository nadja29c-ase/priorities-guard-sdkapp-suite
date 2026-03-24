# Increment Claude-04: Adapter Data Serialization

**Goal:** Extend the response adapter to serialize `structuredContent.data` into `content` so Claude's model can read actual tool data — priority names, hours, patterns, events — and narrate meaningfully without a widget.

---

## Context

The current adapter moves `assistant_guidance` into `content` but leaves `structuredContent.data` untouched. Claude reads `content` as its primary model channel. Without the data in `content`, Claude sees only behavioral instructions — it has no priority names, hours, or events to narrate from.

Confirmed by Claude directly:
> "I only received instructions... No actual data: no priority names, no hours, no event titles, nothing numerical beyond the total."

The fix is surgical: after moving `assistant_guidance`, also serialize `structuredContent.data` as JSON into `content`. The guidance tells Claude *how* to narrate; the data gives Claude *what* to narrate.

**One file changes. Nothing else.**

---

## Pre-Implementation

Read `doc/OPERATIONS_PREDEPLOY.md` before starting. No migrations, no backend changes, no tool handler changes.

---

## Implementation Approach — Copy and Adjust, Never Rewrite

`response_adapter_dupl.py` already exists. Make only the listed changes. Do not restructure, rewrite, or improve anything not listed here.

| File | Action |
|---|---|
| `mcp_server/priority_guardian_claude/response_adapter_dupl.py` | Extend — add data serialization to Step 4 only |

---

## Change: `response_adapter_dupl.py`

**Replace Step 4 only.** Steps 1, 2, 3, 5, 6 and the `assistant_guidance is None` branch are all unchanged. The `clean_structured` dict comprehension, `_meta` stripping, and top-level `_meta` passthrough must remain exactly as they are.

**Current Step 4:**
```python
existing_text = result.content[0].text if result.content else ""
new_text = f"{guidance_str}\n\n{existing_text}".strip() if existing_text else guidance_str
new_content = [mcp_types.TextContent(type="text", text=new_text)]
```

**New Step 4:**
```python
# Safely extract existing text — guard for empty list and non-text first block
existing_text = ""
if result.content:
    first = result.content[0]
    if getattr(first, "text", None):
        existing_text = first.text

# Serialize data for Claude's model channel
data = result.structuredContent.get("data")
data_str = json.dumps(data, ensure_ascii=False, indent=2) if data else ""

# Compose content: guidance first (behavior), then summary (natural language), then data (raw facts)
# This order produces better narration — Claude reads guidance before encountering JSON
parts = [p for p in [guidance_str, existing_text, data_str] if p]
new_text = "\n\n".join(parts)
new_content = [mcp_types.TextContent(type="text", text=new_text)]
```

**Nothing else changes.** Specifically:
- `clean_structured` dict comprehension — unchanged
- `_meta` key stripping from `structuredContent` — unchanged
- Top-level `_meta=result.meta` passthrough — unchanged
- `assistant_guidance is None` branch — unchanged
- Steps 1, 2, 3, 5, 6 — unchanged

Note: `render_weekly_report` includes `otherEvents` (20+ events) in `data`. This will appear in `content` as a large JSON block — expected and intentional for this increment. Token size impact is known and accepted. Trimming is deferred to a future increment.

---

## What NOT to Touch

- Any file in `mcp_server/priority_guardian/` — shared tool handlers
- Any file in `backend/`
- Any other file in `mcp_server/priority_guardian_claude/`
- Existing tests — do not modify

---

## Tests

Add to `tests/unit/mcp_pg_claude/test_scaffold.py` (the existing Claude scaffold test file where previous adapter tests live). Do NOT replace existing tests.

**1. `test_adapter_includes_data_in_content`**
```python
result = mcp_types.CallToolResult(
    content=[mcp_types.TextContent(type="text", text="Summary.")],
    structuredContent={
        "success": True,
        "data": {
            "priorities": [{"name": "Ship PG", "calendarKeyword": "P1", "actualHours": 7.0}],
            "timeAllocation": {"totalTrackedHours": 40.25},
        },
        "assistant_guidance": "Do not repeat priority names.",
    },
)
adapted = adapt_tool_result(result)
# Guidance present
assert "Do not repeat priority names." in adapted.content[0].text
# Data present — Claude can read priority name and hours
assert "Ship PG" in adapted.content[0].text
assert "7.0" in adapted.content[0].text
assert "40.25" in adapted.content[0].text
# Summary present
assert "Summary." in adapted.content[0].text
# Order: guidance before data
guidance_pos = adapted.content[0].text.index("Do not repeat priority names.")
summary_pos = adapted.content[0].text.index("Summary.")
data_pos = adapted.content[0].text.index("Ship PG")
assert guidance_pos < summary_pos < data_pos
```

**2. `test_adapter_handles_empty_data`**
```python
result = mcp_types.CallToolResult(
    content=[mcp_types.TextContent(type="text", text="Summary.")],
    structuredContent={
        "success": True,
        "data": {},
        "assistant_guidance": "Some guidance.",
    },
)
adapted = adapt_tool_result(result)
assert "Some guidance." in adapted.content[0].text
# No crash on empty data
```

**3. `test_adapter_handles_missing_data_key`**
```python
result = mcp_types.CallToolResult(
    content=[mcp_types.TextContent(type="text", text="Summary.")],
    structuredContent={
        "success": True,
        "assistant_guidance": "Some guidance.",
        # no "data" key at all
    },
)
adapted = adapt_tool_result(result)
assert "Some guidance." in adapted.content[0].text
# No crash
```

**4. `test_adapter_data_preserved_in_structured_content`**
```python
result = mcp_types.CallToolResult(
    content=[mcp_types.TextContent(type="text", text="Summary.")],
    structuredContent={
        "success": True,
        "data": {"priorities": [{"name": "Test"}]},
        "assistant_guidance": "guidance",
    },
)
adapted = adapt_tool_result(result)
# Data still in structuredContent (unchanged)
assert adapted.structuredContent["data"] == {"priorities": [{"name": "Test"}]}
# Data also in content (serialized)
assert "Test" in adapted.content[0].text
```

---

## Definition of Done

- [ ] Step 4 of `adapt_tool_result` serializes `structuredContent.data` into `content`
- [ ] Content order is: guidance → existing summary → data
- [ ] `getattr(first, "text", None)` guard used for first content block
- [ ] Empty or missing `data` handled without crash
- [ ] `_meta` stripping and `clean_structured` logic unchanged
- [ ] All 4 new tests pass
- [ ] All existing scaffold tests still pass
- [ ] Deploy to Claude Render service and verify: ask Claude "show me my priorities" — Claude should narrate priority names and hours