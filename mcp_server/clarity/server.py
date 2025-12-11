#!/usr/bin/env python3
"""
Clarity MCP Server - V5 (Widget Integration).

ChatGPT clusters and reasons BEFORE calling each tool.
Tools only format/validate - no AI logic here.
Widget renders clusters as visual cards.

Uses OpenAI's official pattern for _meta support:
- Override list_tools handler to construct Tool objects with _meta
- Register tool call handlers separately

Usage:
    python -m mcp_server.clarity.server

Or run directly:
    python mcp_server/clarity/server.py
"""

import os
import re
import json
from copy import deepcopy
from pathlib import Path
from typing import List
import uvicorn
import structlog
from mcp.server.fastmcp import FastMCP
from mcp import types as mcp_types
from pydantic import AnyUrl, BaseModel, ValidationError

from .tools import cluster_raw_thoughts


# ============================================================================
# Pydantic Validation Models - fail loudly on malformed input
# ============================================================================

class ClusterInput(BaseModel):
    """Expected structure for each cluster from ChatGPT."""
    name: str
    thought_items: List[str]


class ClusterRequest(BaseModel):
    """Expected top-level structure from ChatGPT."""
    clusters: List[ClusterInput]

# Configure structlog
logger = structlog.get_logger(__name__)

# Load widget HTML at startup
WIDGET_VERSION = ""
WIDGET_URI = "ui://widget/clarity-clusters.html"
WIDGET_HTML = Path(__file__).parent.joinpath("clarity-clusters.html").read_text()

# Create FastMCP instance - NO authentication (anonymous mode)
mcp = FastMCP("clarity-mcp", streamable_http_path="/mcp")

# list_resources handler for discovery
@mcp._mcp_server.list_resources()
async def _list_resources() -> List[mcp_types.Resource]:
    return [
        mcp_types.Resource(
            name="clarity_clusters_widget",
            title="Clarity Clusters Widget",
            uri=WIDGET_URI,
            description="Widget for rendering clustered thoughts",
            mimeType="text/html+skybridge",
            _meta={
                "openai/outputTemplate": WIDGET_URI,
                "openai/widgetAccessible": True,
                "openai/resultCanProduceWidget": True,
            },
        )
    ]


# list_resource_templates handler (pizzaz pattern)
@mcp._mcp_server.list_resource_templates()
async def _list_resource_templates() -> List[mcp_types.ResourceTemplate]:
    return [
        mcp_types.ResourceTemplate(
            name="Clarity Clusters Widget",
            title="Clarity Clusters Widget",
            uriTemplate=WIDGET_URI,
            description="Widget for rendering clustered thoughts",
            mimeType="text/html+skybridge",
            _meta={
                "openai/outputTemplate": WIDGET_URI,
                "openai/widgetAccessible": True,
                "openai/resultCanProduceWidget": True,
            },
        )
    ]

# Register widget resource
async def _handle_read_resource(req: mcp_types.ReadResourceRequest) -> mcp_types.ReadResourceResult:
    uri_str = str(req.params.uri)

    logger.info("resource.read.requested", uri=uri_str, widget_version=WIDGET_VERSION)

    if uri_str == WIDGET_URI:
        logger.info("resource.read.serving_widget",
                    uri=uri_str,
                    html_length=len(WIDGET_HTML),
                    widget_version=WIDGET_VERSION)

        # Build _meta exactly like Pizzaz does on TextResourceContents
        resource_meta = {
            "openai/outputTemplate": WIDGET_URI,
            "openai/toolInvocation/invoking": "Organizing your thoughts into clusters...",
            "openai/toolInvocation/invoked": "Here's your Clarity board.",
            "openai/widgetAccessible": True,
            "openai/resultCanProduceWidget": True,
        }

        contents = [
            mcp_types.TextResourceContents(
                uri=WIDGET_URI,
                mimeType="text/html+skybridge",
                text=WIDGET_HTML,
                _meta=resource_meta,
            )
        ]
        return mcp_types.ReadResourceResult(contents=contents)

    # Unknown resource
    return mcp_types.ReadResourceResult(
        contents=[],
        _meta={"error": f"Unknown resource: {uri_str}"},
    )

# Register the handler
mcp._mcp_server.request_handlers[mcp_types.ReadResourceRequest] = _handle_read_resource

# ============================================================================
# Tool Definitions (for list_tools handler)
# ============================================================================

CLUSTER_RAW_THOUGHTS_DESCRIPTION = """BEFORE calling clarity.cluster_raw_thoughts, ensure you have created clusters with the correct structure -
ALWAYS pass data in this exact structure:

{
  "clusters": [
    {
      "name": "<cluster name>",
      "thought_items": ["<item1>", "<item2>", ...]
    }
  ]
}


INPUT: Pass the clusters you identified as the 'clusters' argument
OUTPUT: Visual widget displaying the clusters

SEQUENCE:
1. User provides brain dump (thought_items)
2. You identify clusters (semantic grouping)
3. You CALL THIS TOOL with the clusters ← MANDATORY
4. Widget renders the clusters for user
5. Ask if accurate and complete

"""

#JSON Schema that tells the LLM what arguments to pass.
CLUSTER_RAW_THOUGHTS_SCHEMA = {
    "type": "object",
    "properties": {
        "clusters": {
            "type": "array",
            "description": "List of clusters with 'cluster name' and 'thought_items' fields",
            "items": { #JSON Schema keyword
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Cluster name"},
                    "thought_items": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of semantically similar thought_items in this cluster"
                    }
                },
                "required": ["name", "thought_items"]
            }
        }
    },
    "required": ["clusters"]
}


# ============================================================================
# Other tools using standard @mcp.tool() decorator (no _meta needed)
# ============================================================================
'''
#@mcp.tool(
    name="identify_most_relevant_clusters",
    description="""Filter to only the max 3 top clusters the USER selected as most relevant RIGHT NOW.
    Help the USER assess relevane if needed based of f.e. what is blocking most RIGHT NOW; what is most valuable for the business in short-term vs. long-term.

ONLY called after cluster_raw_thoughts in sequence.
ChatGPT MUST ask the user which clusters matter most BEFORE calling this tool."""
#)
#async def tool_identify_most_relevant_clusters(
    selected_cluster_names: list[str],
    clusters: list[dict],
#) -> dict:
    """
    Filter to only the clusters the user selected as most relevant.

    Args:
        selected_cluster_names: Names of clusters user selected.
        clusters: Enriched clusters from cluster_raw_thoughts output.

    Returns:
        Filtered top_clusters.
    """
    logger.info(
        "tool.identify_most_relevant_clusters.called",
        selected_count=len(selected_cluster_names),
        input_cluster_count=len(clusters),
    )

    result = identify_most_relevant_clusters(selected_cluster_names, clusters)

    logger.info(
        "tool.identify_most_relevant_clusters.complete",
        top_cluster_count=len(result["top_clusters"]),
    )

    return result


#@mcp.tool(
    name="specify_next_steps",
    description="""ASK the USER to generate next specifc steps (max. 5) from the user's TOP clusters. Make sure the next steps are specific enough so that they can be scheduled into the user's calendar and prompt the user to do that.

Only called after identify_most_relevant_clusters in sequence.
ChatGPT MUST have confirmed TOP max. 3 clusters with user BEFORE calling this tool."""
#)
#async def tool_specify_next_steps(top_clusters: list[dict]) -> dict:
    """
    Generate next steps from the user's top clusters.

    Args:
        top_clusters: Filtered clusters from identify_most_relevant_clusters.

    Returns:
        Next steps and clarity summary.
    """
    logger.info(
        "tool.specify_next_steps.called",
        top_cluster_count=len(top_clusters),
    )

    result = specify_next_steps(top_clusters)

    logger.info(
        "tool.specify_next_steps.complete",
        next_steps_count=len(result["next_steps"]),
    )

    return result

'''
# ============================================================================
# OpenAI Widget Pattern: Override list_tools to include _meta for widget integration
# Reference: https://github.com/openai/openai-apps-sdk-examples/blob/main/pizzaz_server_python/main.py
# ============================================================================

@mcp._mcp_server.list_tools()
async def _list_tools() -> List[mcp_types.Tool]:
    """
    Custom list_tools handler that constructs Tool objects with _meta.

    This follows the official OpenAI pattern for widget integration.
    """
    logger.info("tools.list.called", widget_version=WIDGET_VERSION, widget_uri=WIDGET_URI)

    # Get tools registered via @mcp.tool() decorator
    other_tools = await mcp.list_tools()

    # Create cluster_raw_thoughts tool with _meta for widget
    cluster_tool = mcp_types.Tool(
        name="cluster_raw_thoughts",
        description=CLUSTER_RAW_THOUGHTS_DESCRIPTION,
        inputSchema=deepcopy(CLUSTER_RAW_THOUGHTS_SCHEMA),
        _meta={
            "openai/outputTemplate": WIDGET_URI,
            "openai/toolInvocation/invoking": "Organizing your thoughts into clusters...",
            "openai/toolInvocation/invoked": "Here's your Clarity board.",
            "openai/widgetAccessible": True,
            "openai/resultCanProduceWidget": True,
            "annotations": {
                "destructiveHint": False,
                "openWorldHint": False,
                "readOnlyHint": True,
            }
        }
    )

    # Return cluster_raw_thoughts first, then other tools
    all_tools = [cluster_tool] + list(other_tools)
    logger.info("tools.list.returning", tool_count=len(all_tools))
    return all_tools


# Helper to create embedded widget resource (pizzaz pattern)
def _embedded_widget_resource() -> mcp_types.EmbeddedResource:
    return mcp_types.EmbeddedResource(
        type="resource",
        resource=mcp_types.TextResourceContents(
            uri=WIDGET_URI,
            mimeType="text/html+skybridge",
            text=WIDGET_HTML,
            title="Clarity Clusters Widget",
        ),
    )


# Handle tool calls - follows pizzaz request_handlers pattern
async def _call_tool_request(req: mcp_types.CallToolRequest) -> mcp_types.CallToolResult:
    """Handle tool calls - follows pizzaz pattern."""
    name = req.params.name
    arguments = req.params.arguments or {}

    logger.info("tool.call.received",
                tool_name=name,
                argument_keys=list(arguments.keys()),
                widget_version=WIDGET_VERSION)

    if name == "cluster_raw_thoughts":
        # ============================================================
        # 1. LOG RAW INPUT - see exactly what ChatGPT sent
        # ============================================================
        logger.info("TOOL INPUT RAW", raw=arguments)

        # ============================================================
        # 2. VALIDATE WITH PYDANTIC - fail loudly on wrong shape
        # ============================================================
        try:
            validated = ClusterRequest.model_validate(arguments)
            logger.info("tool.cluster_raw_thoughts.VALIDATION_SUCCESS",
                        validated_cluster_count=len(validated.clusters))
        except ValidationError as e:
            logger.error("VALIDATION ERROR in cluster_raw_thoughts", details=e.errors())
            # Return error to ChatGPT so it knows what went wrong
            return mcp_types.CallToolResult(
                content=[
                    mcp_types.TextContent(
                        type="text",
                        text=f"VALIDATION ERROR: {e.errors()}. Expected 'clusters' array with objects containing 'name' (string) and 'thought_items' (array of strings).",
                    )
                ],
                isError=True,
            )

        clusters = arguments.get("clusters", [])

        # Auto-wrap raw strings into a single cluster if ChatGPT sends wrong format
        if clusters and isinstance(clusters[0], str):
            logger.info("tool.cluster_raw_thoughts.AUTO_WRAP",
                        reason="ChatGPT sent raw strings instead of cluster objects",
                        raw_count=len(clusters))
            clusters = [
                {
                    "name": "Tasks",
                    "thought_items": clusters
                }
            ]

        # Auto-extract from content if ChatGPT sends empty clusters but has text
        if not clusters and arguments.get("content"):
            content = arguments["content"]
            # Extract items from text (split by newlines, commas, or bullet points)
            if isinstance(content, str):
                # Split on newlines, bullet points, numbered lists, or commas
                items = re.split(r'[\n•\-\*]|(?:\d+\.)', content)
                items = [item.strip() for item in items if item.strip()]
                if items:
                    logger.info("tool.cluster_raw_thoughts.AUTO_EXTRACT",
                                reason="ChatGPT sent empty clusters but content exists",
                                extracted_count=len(items))
                    clusters = [
                        {
                            "name": "Tasks",
                            "thought_items": items
                        }
                    ]

        # ============================================================
        # 3. LOG PARSED STRUCTURE - each cluster with item count
        # ============================================================
        logger.info("tool.cluster_raw_thoughts.PARSED_OVERVIEW",
                    cluster_count=len(clusters),
                    cluster_names=[c.get("name") for c in clusters])

        for i, cluster in enumerate(clusters):
            items = cluster.get("thought_items", [])
            logger.info("tool.cluster_raw_thoughts.CLUSTER_DETAIL",
                        cluster_index=i,
                        cluster_name=cluster.get("name", "NO_NAME"),
                        item_count=len(items) if isinstance(items, list) else "NOT_A_LIST",
                        items_preview=items[:3] if isinstance(items, list) else str(items),
                        has_name="name" in cluster,
                        has_thought_items="thought_items" in cluster,
                        cluster_keys=list(cluster.keys()) if isinstance(cluster, dict) else "NOT_A_DICT")

        result = cluster_raw_thoughts(clusters)

        logger.info("tool.cluster_raw_thoughts.output",
                    structured_content_keys=list(result["structuredContent"].keys()),
                    cluster_count=len(result["structuredContent"]["clusters"]))

        # Build _meta - reference widget by URI only (no inline HTML to avoid size limits)
        meta = {
            "openai/outputTemplate": WIDGET_URI,
            "openai/toolInvocation/invoking": "Organizing your thoughts into clusters...",
            "openai/toolInvocation/invoked": "Here's your Clarity board.",
            "openai/widgetAccessible": True,
            "openai/resultCanProduceWidget": True,
        }

        logger.info("tool.cluster_raw_thoughts.response_meta",
                    meta_keys=list(meta.keys()),
                    output_template=WIDGET_URI)

        call_result = mcp_types.CallToolResult(
            content=[
                mcp_types.TextContent(
                    type="text",
                    text=result["content"][0]["text"],
                )
            ],
            structuredContent=result["structuredContent"],
            _meta=meta,  # ← underscore required
        )

        # Log the FINAL outgoing tool result - no more guessing
        try:
            serialized = call_result.model_dump(mode="json")
            logger.info("TOOL OUTPUT FINAL",
                        result=serialized,
                        meta=meta)
            # Debug: Check what actually gets serialized with alias
            wire_format = call_result.model_dump(mode="json", by_alias=True)
            logger.info("WIRE FORMAT CHECK",
                        wire_meta_key="_meta" in str(wire_format),
                        first_keys=list(wire_format.keys())[:5])
        except Exception as e:
            logger.error("tool.cluster_raw_thoughts.serialize_error", error=str(e))

        return call_result

    return mcp_types.CallToolResult(
        content=[
            mcp_types.TextContent(
                type="text",
                text=f"Unknown tool: {name}",
            )
        ],
        isError=True,
    )

# Register handler
mcp._mcp_server.request_handlers[mcp_types.CallToolRequest] = _call_tool_request


def create_app():
    """
    Create the ASGI application.

    FastMCP is the root app with CORS middleware for widget compatibility.
    """
    app = mcp.streamable_http_app()

    try:
        from starlette.middleware.cors import CORSMiddleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
            allow_credentials=False,
        )
    except Exception:
        pass

    return app


# ASGI entrypoint
app = create_app()


if __name__ == "__main__":
    # Default to port 8002 for local dev (Focused uses 8001)
    port = int(os.getenv("PORT", "8002"))

    logger.info(
        "clarity.server.starting",
        host="127.0.0.1",
        port=port,
    )

    print("=" * 50)
    print("CLARITY MCP SERVER - V5 (Widget Integration)")
    print(f"Starting on http://127.0.0.1:{port}")
    print(f"MCP endpoint: http://127.0.0.1:{port}/mcp")
    print("=" * 50)

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
