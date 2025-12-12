#!/usr/bin/env python3
"""
Clarity MCP Server.

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
from typing import List, Optional
import uvicorn
import structlog
from mcp.server.fastmcp import FastMCP
from mcp import types as mcp_types
from pydantic import AnyUrl, BaseModel, ValidationError, model_validator

from .tools import cluster_raw_thoughts

# ============================================================================
# Configuation 
# ============================================================================

# Configure structlog
logger = structlog.get_logger(__name__)

# Load widget HTML at startup
WIDGET_VERSION = ""
WIDGET_URI = "ui://widget/clarity-clusters.html"
WIDGET_HTML = Path(__file__).parent.joinpath("clarity-clusters.html").read_text()


# Create FastMCP instance - NO authentication (anonymous mode)
mcp = FastMCP("clarity-mcp", streamable_http_path="/mcp")

# ============================================================================
# Helper: MCP Tool Definitions (for list_tools handler)
# ============================================================================

CLUSTER_RAW_THOUGHTS_DESCRIPTION = """
Organize user's business-related thoughts into visual clusters for cognitive ease and clarity what to focus on.

WHEN TO CALL:
- User has cognitive load from too many thoughts/tasks/ideas
- Content is PREDOMINANTLY business-related (NOT personal matters like relationships, mental health issues, etc.)
- User has CONFIRMED ALL thoughts are captured (thoughts_exhausted: true)

CONFIRMATION FLOW:
1. First, help user exhaust their thoughts. Ask: "Is there anything else on your mind that needs to be organized?"
2. ONLY call this tool when user confirms they're done (set thoughts_exhausted: true)
3. On FIRST call: set correctly_clustered: null
4. After widget renders, ask: "Do these clusters look accurate?"
5. If user says NO: re-call with correctly_clustered: false and adjusted clusters
6. If user says YES: conversation continues (no re-call needed)

CLUSTERING STRATEGY:
- For simple clusters (few thought items): use thought_items directly (flat structure)
- For complex clusters (many thought items): group into subclusters (nested structure)

CRITICAL: NEVER return plain text lists - ALWAYS use the widget to visualize clusters and their content.
"""

# ============================================================================
# Configuration MCP Tools:
# INPUT SCHEMAS: tells ChatGPT what to send back (or that your API/tool expects to receive).
# ============================================================================

# Pydantic data models/schemas that define the exact JSON structure you expect

class SubclusterInput(BaseModel):
    """Expected structure for each subcluster within a cluster."""
    subcluster_name: str
    thought_items: List[str]

    @model_validator(mode="after")
    def validate_not_empty(self) -> "SubclusterInput":
        """Ensure subcluster has at least one thought item."""
        if len(self.thought_items) == 0:
            raise ValueError(
                f"Subcluster '{self.subcluster_name}' has no thought_items. Subclusters must contain at least two thought item."
            )
        return self


class ClusterInput(BaseModel):
    """Expected structure for each cluster from ChatGPT.
    """
    cluster_name: str
    thought_items: List[str] = []  # Flat structure (used when no subclusters)
    subclusters: List[SubclusterInput] = []  # Nested structure (optional groupings)

    @model_validator(mode="after")
    def validate_not_empty(self) -> "ClusterInput":
        """Ensure cluster has at least some content."""
        has_items = len(self.thought_items) > 0
        has_subclusters = len(self.subclusters) > 0

        if not has_items and not has_subclusters:
            raise ValueError(
                f"Cluster '{self.cluster_name}' is empty. Must have thought_items or subclusters."
            )
        return self


class ClusterRequest(BaseModel):
    """Expected top-level structure from ChatGPT."""
    thoughts_exhausted: bool  # Required. Gate for tool call.
    correctly_clustered: Optional[bool] = None  # Optional. null on first call, true/false on re-cluster.
    clusters: List[ClusterInput]

# JSON Schema that tells chat gpt what arguments to pass (Input Schema).
# JSON Schema (for ChatGPT / MCP discovery ONLY)
CLUSTER_RAW_THOUGHTS_SCHEMA = {
    "type": "object",
    "properties": {
        "thoughts_exhausted": {
            "type": "boolean",
            "description": "Must be true. Confirms user has shared all thoughts before clustering."
        },
        "correctly_clustered": {
            "type": ["boolean", "null"],
            "description": "null on first call. false if user says clusters are wrong (triggers re-cluster). true if confirmed accurate."
        },
        "clusters": {
            "type": "array",
            "description": "List of clusters. Each cluster can use thought_items (flat), subclusters (nested), or both (mixed).",
            "items": {
                "type": "object",
                "properties": {
                    "cluster_name": {
                        "type": "string",
                        "description": "Name of the cluster"
                    },
                    "thought_items": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Direct thought items (use for flat clusters without subclusters)"
                    },
                    "subclusters": {
                        "type": "array",
                        "description": "Nested groupings within cluster (use for complex clusters instead of thought_items)",
                        "items": {
                            "type": "object",
                            "properties": {
                                "subcluster_name": {
                                    "type": "string",
                                    "description": "Name of the subcluster"
                                },
                                "thought_items": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Thought items in this subcluster"
                                }
                            }, ## IF a subcluster exists, THEN these are required:
                            "required": ["subcluster_name", "thought_items"]
                        }
                    }
                },
                "required": ["cluster_name"]
            }
        }
    },
    "required": ["thoughts_exhausted", "clusters"]
}

# ============================================================================
# Resource handlers (show things - UI): Advertize widget HTML; Serve widget bundles (Skybridge HTML);
# They answer: “What UI can this app render, and where do I load it from?”
# Typical handlers: list_resources; list_resource_templates; read_resource
# 
# Let ChatGPT hydrate UI without guessing
# Visible to chat GPT: UI called ONLY in connection with a mcp tool. 
# There is no “UI-only refresh” initiated by ChatGPT.
# ============================================================================

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


# list_resource_templates handler.  (pizzaz pattern)
# This advertises widget templates to ChatGPT so the runtime knows which UI widgets your app can render and how to load them.
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

# This function handles ReadResourceRequest:
# That request is sent by ChatGPT, not by the user, when ChatGPT needs to: load a widget’s HTML;
# hydrate a UI after a tool call; restore a widget (scroll, fullscreen, etc.).
# The actual widget HTML must be fetched separately. That fetch happens via read_resource.

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

# Register the UI handler
mcp._mcp_server.request_handlers[mcp_types.ReadResourceRequest] = _handle_read_resource


# ============================================================================
# Tool Discovery Handler: Advertize ALL MCP capabilities to ChatGPT. 
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

# ============================================================================
# OpenAI Widget Pattern: Override list_tools to include _meta for widget integration
# Reference: https://github.com/openai/openai-apps-sdk-examples/blob/main/pizzaz_server_python/main.py
# ============================================================================


# Helper to create  INLINE embedded widget resource (pizzaz pattern)
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

# ============================================================================
# Handle mcp tool calls. Runtime execution after chat GPT decided to call the tool 
# (follows pizzaz request_handlers pattern for UI. Not decorator-based tools )
# ============================================================================
async def _call_tool_request(req: mcp_types.CallToolRequest) -> mcp_types.CallToolResult:
    """Handle tool calls - follows pizzaz pattern."""
    name = req.params.name # extract tool name
    arguments = req.params.arguments or {}

    logger.info("clarity.tool.call_received",
                tool_name=name,
                argument_keys=list(arguments.keys()),
                widget_version=WIDGET_VERSION)
    
# Handle "cluster_raw_thoughts" mcp tool specifically
    if name == "cluster_raw_thoughts":
        validated_request = None

        try:
            # Pydantic validation (includes XOR validation via model_validator)
            validated_request = ClusterRequest.model_validate(arguments)

            # Count subclusters for logging
            subcluster_count = sum(len(c.subclusters) for c in validated_request.clusters)

            logger.info("clarity.tool.validation_success",
                        cluster_count=len(validated_request.clusters),
                        subcluster_count=subcluster_count,
                        thoughts_exhausted=validated_request.thoughts_exhausted,
                        correctly_clustered=validated_request.correctly_clustered)

        except ValidationError as e:
            logger.info("clarity.tool.validation_failed_attempt_repair", error=str(type(e).__name__))

            # --- recovery: try to build valid structure from malformed input ---
            clusters_data = None
            thoughts_exhausted = arguments.get("thoughts_exhausted", True)  # Default to True for repair
            correctly_clustered = arguments.get("correctly_clustered", None)

            raw_clusters = arguments.get("clusters", [])

            # Repair: raw strings list -> wrap into single flat cluster
            if raw_clusters and isinstance(raw_clusters[0], str):
                clusters_data = [{
                    "cluster_name": "Tasks",
                    "thought_items": raw_clusters,
                    "subclusters": []
                }]

            # Repair: content field -> extract items into single flat cluster
            elif isinstance(arguments.get("content"), str):
                items = re.split(r'[\n•\-\*]|(?:\d+\.)', arguments["content"])
                items = [i.strip() for i in items if i.strip()]
                if items:
                    clusters_data = [{
                        "cluster_name": "Tasks",
                        "thought_items": items,
                        "subclusters": []
                    }]

            if clusters_data is None:
                logger.error("clarity.tool.repair_failed")
                return mcp_types.CallToolResult(
                    content=[mcp_types.TextContent(
                        type="text",
                        text="The tool could not understand the input."
                    )],
                    isError=True,
                )

            # Re-validate repaired structure
            try:
                validated_request = ClusterRequest.model_validate({
                    "thoughts_exhausted": thoughts_exhausted,
                    "correctly_clustered": correctly_clustered,
                    "clusters": clusters_data
                })
                logger.info("clarity.tool.repair_success",
                            cluster_count=len(validated_request.clusters))

            except ValidationError:
                logger.error("clarity.tool.repair_failed")
                return mcp_types.CallToolResult(
                    content=[mcp_types.TextContent(
                        type="text",
                        text="The tool could not understand the input."
                    )],
                    isError=True,
                )

        # From here on, validated_request is guaranteed valid
        clusters = [c.model_dump() for c in validated_request.clusters]
        result = cluster_raw_thoughts(clusters)

        logger.info("clarity.tool.complete",
                    cluster_count=len(result["structuredContent"]["clusters"]))

        # Build _meta - reference widget by URI only
        meta = {
            "openai/outputTemplate": WIDGET_URI,
            "openai/toolInvocation/invoking": "Organizing your thoughts into clusters...",
            "openai/toolInvocation/invoked": "Here's your Clarity board.",
            "openai/widgetAccessible": True,
            "openai/resultCanProduceWidget": True,
        }
        # Return response for the recognized tool "cluster_raw_thoughts" (happy path)
        return mcp_types.CallToolResult(
            content=[
                mcp_types.TextContent(
                    type="text",
                    text=result["content"][0]["text"],
                )
            ],
            structuredContent=result["structuredContent"],
            _meta=meta,
        )
    # Return response for an unrecognized tool (fallback)
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

# ============================================================================
# App Startup
# ============================================================================

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
