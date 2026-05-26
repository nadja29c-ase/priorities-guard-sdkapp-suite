# (duplicate) — exists only because tool responses embed ChatGPT-specific fields.
# Tool handlers in mcp_server/priority_guardian/tools/ are never modified.
# Post-OpenAI-approval refactor: move to mcp_server/shared/ and delete this file.

import json
from mcp import types as mcp_types

from mcp_server.priority_guardian_claude.handlers.resources_dupl import WIDGET_APP_DOMAIN

# Widget resource URI (matches resources_dupl.py)
WIDGET_URI = "ui://pg-claude/dashboard-v1.html"


def adapt_tool_result(result: mcp_types.CallToolResult) -> mcp_types.CallToolResult:
    """
    Adapt tool result for Claude.

    Moves assistant_guidance from structuredContent to content so Claude's model
    sees behavioral guidance. Strips _meta from structuredContent (OpenAI-specific).
    Preserves top-level _meta unchanged.

    Always returns a new CallToolResult — never mutates the original.
    """
    # Step 1: Guard — return new object if no structuredContent
    if result.structuredContent is None:
        return mcp_types.CallToolResult(
            content=list(result.content) if result.content else [],
            structuredContent=None,
            isError=result.isError,
            _meta=result.meta,
        )

    # Step 2: Extract assistant_guidance
    assistant_guidance = result.structuredContent.get("assistant_guidance")

    # If no guidance, still build clean structuredContent (strip _meta)
    if assistant_guidance is None:
        clean_structured = {
            k: v for k, v in result.structuredContent.items()
            if k not in ("assistant_guidance", "_meta")
        }
        return mcp_types.CallToolResult(
            content=list(result.content) if result.content else [],
            structuredContent=clean_structured,
            isError=result.isError,
            _meta=result.meta,
        )

    # Step 3: Serialize assistant_guidance to string
    if isinstance(assistant_guidance, str):
        guidance_str = assistant_guidance
    elif isinstance(assistant_guidance, dict):
        guidance_str = json.dumps(assistant_guidance, ensure_ascii=False, indent=2)
    else:
        guidance_str = str(assistant_guidance)

    # Step 4: Build new content
    # Safely extract existing text — guard for empty list and non-text first block
    existing_text = ""
    if result.content:
        first = result.content[0]
        if getattr(first, "text", None):
            existing_text = first.text

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

    # Compose content: guidance first (behavior), then summary (natural language), then data (raw facts)
    # This order produces better narration — Claude reads guidance before encountering JSON
    parts = [p for p in [guidance_str, existing_text, data_str] if p]
    new_text = "\n\n".join(parts)
    new_content = [mcp_types.TextContent(type="text", text=new_text)]

    # Step 5: Build clean structuredContent
    clean_structured = {
        k: v for k, v in result.structuredContent.items()
        if k not in ("assistant_guidance", "_meta")
    }

    # Step 6: Return new CallToolResult
    return mcp_types.CallToolResult(
        content=new_content,
        structuredContent=clean_structured,
        isError=result.isError,
        _meta=result.meta,
    )


def adapt_widget_tool_meta(result: mcp_types.CallToolResult) -> mcp_types.CallToolResult:
    """
    Add _meta.ui.resourceUri to widget tool results for display.

    MCP Apps standard: tool results with _meta.ui.resourceUri trigger
    the host to fetch and display the corresponding widget resource.
    Claude uses this pattern to show interactive UI after tool calls.

    Applies to: get_priorities, render_weekly_report

    Only adds metadata if the result is not an error.

    Args:
        result: The CallToolResult from a widget tool (already adapted)

    Returns:
        New CallToolResult with _meta.ui.resourceUri added
    """
    # Don't add widget link to error results — return new object for consistency
    if result.isError:
        return mcp_types.CallToolResult(
            content=result.content,
            structuredContent=result.structuredContent,
            isError=result.isError,
            _meta=result.meta,
        )

    # Build new _meta with ui.resourceUri and ui.domain — defensive merge preserves existing ui keys
    existing_meta = dict(result.meta) if result.meta else {}
    existing_ui = dict(existing_meta.get("ui", {}))
    existing_ui.update({"resourceUri": WIDGET_URI, "domain": WIDGET_APP_DOMAIN})
    new_meta = {**existing_meta, "ui": existing_ui}

    return mcp_types.CallToolResult(
        content=result.content,
        structuredContent=result.structuredContent,
        isError=result.isError,
        _meta=new_meta,
    )
