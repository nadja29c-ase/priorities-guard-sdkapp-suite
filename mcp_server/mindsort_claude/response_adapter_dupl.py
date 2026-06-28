# (duplicate) — exists only because tool responses embed ChatGPT-specific fields.
# Tool handlers in mcp_server/clarity/tools/ are never modified.
# Consolidate into shared/ ONLY if this file proves to churn — not preemptively.

from mcp import types as mcp_types


def _clean_top_meta(meta) -> dict | None:
    """
    Clean platform-specific keys from result _meta.

    1. Strip openai/* keys (namespace-prefixed vendor keys).
    2. Strip ui.resourceUri (generic key but platform-specific value — OpenAI widget URI).
    3. Collapse empty ui dict to absent (don't leave {"ui": {}}).
    4. Return None if empty.

    The adapter strips widget identity; the dispatcher injects Claude's.
    """
    if not meta:
        return None

    cleaned = {}
    for k, v in dict(meta).items():
        # Skip openai/* vendor-namespaced keys
        if k.startswith("openai/"):
            continue

        # Handle ui dict: strip resourceUri, collapse if empty
        if k == "ui" and isinstance(v, dict):
            ui_cleaned = {uk: uv for uk, uv in v.items() if uk != "resourceUri"}
            if ui_cleaned:  # only keep ui if non-empty after stripping
                cleaned[k] = ui_cleaned
            # else: drop ui entirely (don't leave {"ui": {}})
            continue

        cleaned[k] = v

    return cleaned or None


def _guidance_to_str(guidance) -> str:
    """Render guidance to string. Per §8.1: dict renders instruction only, drops action."""
    if isinstance(guidance, str):
        return guidance
    if isinstance(guidance, dict):
        # Per §8.1: render instruction only; action is an internal control token.
        instruction = guidance.get("instruction")
        if instruction is not None:
            return str(instruction)
        return str(guidance)  # defensive: dict without 'instruction'
    return str(guidance)


def adapt_tool_result(result: mcp_types.CallToolResult) -> mcp_types.CallToolResult:
    """
    Adapt a tool result for Claude.

    Transformation:
    1. Move assistant_guidance from structuredContent to content.
    2. Strip assistant_guidance and any inner _meta from structuredContent.
    3. Discriminate top-level _meta: keep non-openai/* keys, strip openai/* keys.
    4. Return a new CallToolResult (never mutate original).
    """
    # Step 1 — structuredContent is None: return new object with discriminated _meta
    if result.structuredContent is None:
        return mcp_types.CallToolResult(
            content=list(result.content) if result.content else [],
            structuredContent=None,
            isError=result.isError,
            _meta=_clean_top_meta(result.meta),
        )

    # Step 2 — extract guidance
    guidance = result.structuredContent.get("assistant_guidance")

    # Step 3 — build clean structuredContent (strip assistant_guidance + any inner _meta)
    clean_structured = {
        k: v for k, v in result.structuredContent.items()
        if k not in ("assistant_guidance", "_meta")
    }

    # Step 4 — build new content
    existing_text = ""
    if result.content:
        first = result.content[0]
        if getattr(first, "text", None):
            existing_text = first.text

    if guidance is not None:
        guidance_str = _guidance_to_str(guidance)
        parts = [p for p in [guidance_str, existing_text] if p]
        new_text = "\n\n".join(parts)
        new_content = [mcp_types.TextContent(type="text", text=new_text)]
    else:
        # No guidance — preserve existing content as-is (may be empty)
        new_content = list(result.content) if result.content else []

    # Step 5 — return new object with discriminated top-level _meta
    return mcp_types.CallToolResult(
        content=new_content,
        structuredContent=clean_structured,
        isError=result.isError,
        _meta=_clean_top_meta(result.meta),
    )
