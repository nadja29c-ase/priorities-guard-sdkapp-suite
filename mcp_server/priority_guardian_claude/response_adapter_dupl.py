# (duplicate) — exists only because tool responses embed ChatGPT-specific fields.
# Tool handlers in mcp_server/priority_guardian/tools/ are never modified.
# Post-OpenAI-approval refactor: move to mcp_server/shared/ and delete this file.

import json
from mcp import types as mcp_types


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
    existing_text = result.content[0].text if result.content else ""
    new_text = f"{guidance_str}\n\n{existing_text}".strip() if existing_text else guidance_str
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
