# (duplicate) — exists only because tool responses embed ChatGPT-specific fields.
# Tool handlers in mcp_server/clarity/tools/ are never modified.
# Consolidate into shared/ ONLY if this file proves to churn — not preemptively.

from mcp import types as mcp_types
from typing import Any, Optional

# Maximum items to include in compact projections (mirrors PG's MAX_LIST_ITEMS precedent)
MAX_PROJECTION_ITEMS = 10

# Group A tools: model MUST see board structure to act (surface compact projection)
# See inc_mindsort_claude_model_visible_channel.md for classification rationale
_GROUP_A_TOOLS = frozenset({
    "read_board_before_editing",
    "edit_board",
})


def _build_compact_board_projection(structured: dict) -> Optional[str]:
    """
    Build a compact, model-actionable board projection from structuredContent.

    Returns cluster/subcluster names with item counts, NOT full thought text.
    Bounded by MAX_PROJECTION_ITEMS to prevent token bloat on large boards.

    Args:
        structured: The structuredContent dict from a board-returning tool

    Returns:
        Compact projection string, or None if no board data present
    """
    # MindSort handlers put cluster_names at top level (not under "data")
    cluster_names = structured.get("cluster_names")
    clusters = structured.get("clusters")

    # Empty board or no data — no projection needed (guidance handles this)
    if not cluster_names and not clusters:
        return None

    lines = []

    # If we have cluster_names (the lightweight list), use it
    if cluster_names and isinstance(cluster_names, list):
        # Bound the projection
        names_to_show = cluster_names[:MAX_PROJECTION_ITEMS]
        truncated = len(cluster_names) > MAX_PROJECTION_ITEMS

        lines.append("Board structure:")
        for name in names_to_show:
            lines.append(f"  - {name}")
        if truncated:
            lines.append(f"  ... and {len(cluster_names) - MAX_PROJECTION_ITEMS} more clusters")

    # If we have full clusters, extract structure (names + item counts)
    elif clusters and isinstance(clusters, list):
        clusters_to_show = clusters[:MAX_PROJECTION_ITEMS]
        truncated = len(clusters) > MAX_PROJECTION_ITEMS

        lines.append("Board structure:")
        for cluster in clusters_to_show:
            cluster_name = cluster.get("name", "Unnamed")
            items = cluster.get("items", [])
            item_count = len(items) if isinstance(items, list) else 0

            # Check for subclusters
            subclusters = cluster.get("subclusters", [])
            if subclusters and isinstance(subclusters, list):
                subcluster_names = [s.get("name", "Unnamed") for s in subclusters[:5]]
                sub_str = ", ".join(subcluster_names)
                if len(subclusters) > 5:
                    sub_str += f", +{len(subclusters) - 5} more"
                lines.append(f"  - {cluster_name} ({item_count} items) → subclusters: {sub_str}")
            else:
                lines.append(f"  - {cluster_name} ({item_count} items)")

        if truncated:
            lines.append(f"  ... and {len(clusters) - MAX_PROJECTION_ITEMS} more clusters")

    return "\n".join(lines) if lines else None


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


def adapt_tool_result(
    result: mcp_types.CallToolResult,
    tool_name: Optional[str] = None,
) -> mcp_types.CallToolResult:
    """
    Adapt a tool result for Claude.

    Transformation:
    1. Move assistant_guidance from structuredContent to content.
    2. For Group A tools (read_board_before_editing, edit_board): surface a compact,
       bounded board projection into content so the model can see cluster names.
       (Platform divergence: Claude reads content only; structuredContent is widget-only.)
    3. Strip assistant_guidance and any inner _meta from structuredContent.
    4. Discriminate top-level _meta: keep non-openai/* keys, strip openai/* keys.
    5. Return a new CallToolResult (never mutate original).

    Args:
        result: The CallToolResult from the tool handler
        tool_name: The tool name (used to classify Group A vs Group B behavior)
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
    # IMPORTANT: Keep clusters, cluster_names, etc. for the widget — only content gets projection
    clean_structured = {
        k: v for k, v in result.structuredContent.items()
        if k not in ("assistant_guidance", "_meta")
    }

    # Step 4 — build compact board projection for Group A tools
    # Group A: model MUST see board structure to target edits by cluster name
    # Group B: widget-display only, guidance tells model not to re-list
    board_projection = None
    if tool_name in _GROUP_A_TOOLS:
        board_projection = _build_compact_board_projection(result.structuredContent)

    # Step 5 — build new content
    existing_text = ""
    if result.content:
        first = result.content[0]
        if getattr(first, "text", None):
            existing_text = first.text

    # Compose: guidance first, then existing summary, then board projection
    # This order matches PG-Claude and produces better narration
    if guidance is not None:
        guidance_str = _guidance_to_str(guidance)
        parts = [p for p in [guidance_str, existing_text, board_projection] if p]
        new_text = "\n\n".join(parts)
        new_content = [mcp_types.TextContent(type="text", text=new_text)]
    elif board_projection:
        # No guidance but we have projection — include it with existing text
        parts = [p for p in [existing_text, board_projection] if p]
        new_text = "\n\n".join(parts)
        new_content = [mcp_types.TextContent(type="text", text=new_text)]
    else:
        # No guidance, no projection — preserve existing content as-is (may be empty)
        new_content = list(result.content) if result.content else []

    # Step 6 — return new object with discriminated top-level _meta
    return mcp_types.CallToolResult(
        content=new_content,
        structuredContent=clean_structured,
        isError=result.isError,
        _meta=_clean_top_meta(result.meta),
    )
