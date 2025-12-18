# Claude Code Briefing: Split load_saved_board into Two Tools

## Goal

Replace `render_widget` parameter with two separate tools. LLMs pick tools more reliably than parameters.

| Tool | Widget | When to use |
|------|--------|-------------|
| `read_saved_board` | Never | "Add X to my board" → get data silently → merge → organize_thoughts |
| `load_saved_board` | Always | "Show my board" → display widget |

---

## 1. Create new file: `mcp_server/clarity/tools/read_saved_board.py`

Copy `load_saved_board.py` and modify as follows:

### NAME
```python
NAME = "read_saved_board"
```

### DESCRIPTION
```python
DESCRIPTION = """
Read user's saved Clarity board data from database. NO WIDGET.

IMPORTANT: This tool MUST NOT include `_meta`, `widget_uri`, or any UI metadata.

WHEN TO CALL:
- User wants to ADD/MODIFY their saved board
- Example: "Add X to my board" → call read_saved_board → merge → call organize_thoughts

DO NOT CALL:
- When user wants to VIEW/SHOW their board (use load_saved_board instead)

FLOW:
1. Call read_saved_board → receive clusters (no UI)
2. LLM merges new thoughts into returned clusters (no DB writes)
3. Call organize_thoughts with merged set → widget renders

EMPTY STATE RESPONSE:
When no saved board exists:
{
  "clusters": [],
  "saved_board_hash": null
}

SAVED STATE RESPONSE:
When saved board exists:
{
  "clusters": [...],
  "saved_board_hash": "abc123..."
}
"""
```

### INPUT_SCHEMA
```python
INPUT_SCHEMA = {
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": False
}
```

### handle()
- Remove all `render_widget` parameter handling
- Always set `meta = None` (no widget metadata)
- Never include `_meta` in CallToolResult
- Keep all persistence and response logic

### Registration
```python
register_tool(ToolDefinition(
    name=NAME,
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=None,  # Never produces widget
    handle=handle,
))
```

---

## 2. Update existing: `mcp_server/clarity/tools/load_saved_board.py`

### DESCRIPTION
```python
DESCRIPTION = """
Load and DISPLAY user's saved Clarity board with widget.

WHEN TO CALL:
- User asks to SEE/SHOW/VIEW/DISPLAY their saved board
- Example: "Show my board", "What's on my board?"

DO NOT CALL:
- When user wants to ADD items (use read_saved_board instead)

EMPTY STATE RESPONSE:
When no saved board exists, widget shows empty state message.

SAVED STATE RESPONSE:
Widget renders showing saved clusters.
"""
```

### INPUT_SCHEMA
```python
INPUT_SCHEMA = {
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": False
}
```

### handle()
- Remove `render_widget` parameter handling
- Always include widget metadata in `_meta`:
```python
meta = {
    "openai/outputTemplate": WIDGET_URI,
    "openai/toolInvocation/invoking": "Loading your saved board...",
    "openai/toolInvocation/invoked": "Here's your saved Clarity board.",
    "openai/widgetAccessible": True,
    "openai/resultCanProduceWidget": True,
}
```

### Registration
```python
register_tool(ToolDefinition(
    name=NAME,
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=WIDGET_URI,  # Always produces widget
    handle=handle,
))
```

---

## 3. Update `mcp_server/clarity/tools/__init__.py`

Add import for new tool:
```python
from . import read_saved_board  # noqa: F401, E402
```

---

## Test Matrix

| User says | Expected tool(s) | Widgets shown |
|-----------|------------------|---------------|
| "Show my board" | load_saved_board | 1 ✓ |
| "Add X to my board" | read_saved_board → organize_thoughts | 1 ✓ |
| "Save my board" | save_board | 0 (updates existing widget) |

---

## Summary of Changes

| File | Action |
|------|--------|
| `read_saved_board.py` | CREATE - new tool, no widget, no `_meta` |
| `load_saved_board.py` | UPDATE - remove render_widget param, always widget |
| `tools/__init__.py` | UPDATE - add import for read_saved_board |