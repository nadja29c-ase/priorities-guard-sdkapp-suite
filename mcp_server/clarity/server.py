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
import httpx
import uvicorn
import structlog
from mcp.server.fastmcp import FastMCP
from mcp import types as mcp_types
from pydantic import BaseModel, Field, ValidationError, model_validator
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from .tools import cluster_raw_thoughts
from mcp_server.clarity.config import (
    MCP_SERVER_URL,
    OAUTH_ISSUER_URL,
    BACKEND_URL,
    INTERNAL_API_SECRET,
)
from mcp_server.clarity.mcp_auth import (
    authenticate_request,
    UnauthorizedError,
    InsufficientScopeError,
    build_unauthorized_error,
    build_forbidden_error,
    build_invalid_params_error,
    cleanup_jwks_cache,
)
from mcp_server.clarity.discovery import oauth_protected_resource

# ============================================================================
# Configuration
# ============================================================================

# Configure structlog
logger = structlog.get_logger(__name__)

# Module-level HTTP client for backend calls (reused across requests)
_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    """Get or create module-level HTTP client for backend calls."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=10.0)
    return _http_client


async def _cleanup_http_client():
    """Clean up HTTP client on shutdown."""
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None

# Load widget HTML at startup
WIDGET_VERSION = ""
WIDGET_URI = "ui://widget/clarity-clusters.html"
WIDGET_HTML = Path(__file__).parent.joinpath("clarity-clusters.html").read_text()


# Create FastMCP instance
mcp = FastMCP("clarity-mcp", streamable_http_path="/mcp")


# ============================================================================
# MCPContentTypeFixMiddleware - Fix ChatGPT octet-stream Content-Type
# ============================================================================

class MCPContentTypeAndAcceptFixMiddleware:
    """
    Fix ChatGPT → FastMCP header mismatch:
    - ChatGPT sends Content-Type: application/octet-stream
    - ChatGPT sends Accept: */*
    FastMCP requires:
    - Content-Type: application/json
    - Accept: text/event-stream (for SSE handshake)
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("method") == "POST":
            if scope.get("path") == "/mcp":

                new_headers = []
                modified = False

                for name, value in scope["headers"]:
                    if name == b"content-type" and b"application/octet-stream" in value:
                        value = b"application/json"
                        modified = True

                    if name == b"accept":
                        value = b"text/event-stream, application/json"
                        modified = True

                    new_headers.append((name, value))

                if modified:
                    scope = dict(scope)
                    scope["headers"] = new_headers

        await self.app(scope, receive, send)

# ============================================================================
# Helper: MCP Tool Definitions (for list_tools handler)
# ============================================================================

CLUSTER_RAW_THOUGHTS_DESCRIPTION = """
Organize user's thoughts, ideas, tasks into visual clusters for cognitive ease and clarity what to focus on next.

WHEN TO CALL:
- Call EARLY: After user expresses 5+ thought items, call immediately - don't wait
- Content is PREDOMINANTLY business-related (NOT personal matters)
- Call REPEATEDLY as user adds more thoughts to update clusters

PROGRESSIVE CLUSTERING FLOW:
1. User shares thoughts → after 5+ items, call tool with thoughts_exhausted: false
2. Widget renders current clusters, evtl. subclusters, evtl. tags
3. Ask: "What else is on your mind?"
4. User adds more → ALWAYS re-call tool to update clusters with ALL user thoughts so far 
5. When user says "that's all" → call with thoughts_exhausted: true
6. Ask: "Do these clusters look accurate?" (correctly_clustered confirmation)

FIELD USAGE:
- thoughts_exhausted: false = user may have more, keep asking
- thoughts_exhausted: true = user confirmed done
- correctly_clustered: null on calls before final confirmation
- correctly_clustered: true/false after user reviews final clusters

CLUSTERING STRATEGY:
- Flat: thought_items only (simple clusters)
- Nested: subclusters only (complex groupings)
- Mixed: both (some ungrouped + some grouped)

BEHAVIORAL- HINT TAGS (optional, max 3 per cluster/subcluster):
Tags signal the cluster requires a different mental mode than normal execute-and-done work.
ONLY TAG WHEN: 
- user intent is NOT AMBIGOUS and DOMINANT within the cluster 
- user intent matches one of the available tags. 
- user thought items are BUSINESS-RELATED (NOT personal matters or household chores f.e. plan a date night, grocery shopping).

Available tags:
- "decide" → contains choices/tradeoffs needing resolution
- "research" → contains unknowns needing investigation
- "test" → contains assumptions/hypotheses to test
- "delegate" → contains work for others
- "automate" → contains repetitive work to systematize
- "learn" → contains skill gaps requiring knowledge acquisition
- "align" → contains items needing discussion/agreement with others
- "low value admin" → low-value administrative tasks to batch or eliminate

CRITICAL: NEVER return plain text lists - ALWAYS use the widget to visualize clusters.
"""
# ============================================================================
# Configuration MCP Tools:
# INPUT SCHEMAS: tells ChatGPT what to send back (or that your API/tool expects to receive).
# ============================================================================

# Pydantic data models/schemas that define the exact JSON structure you expect

# Behavioral tags - signal cluster requires different mental mode than execute-and-done
ALLOWED_TAGS = [
    "decide",          # contains choices/tradeoffs needing resolution
    "research",        # contains unknowns needing investigation
    "test",            # contains assumptions/hypotheses to test
    "delegate",        # contains work for others
    "automate",        # contains repetitive work to systematize
    "learn",           # contains skill gaps requiring knowledge acquisition
    "align",           # contains items needing discussion/agreement with others
    "low value admin", # low-value administrative tasks to batch or eliminate
]


class SubclusterInput(BaseModel):
    """Expected structure for each subcluster within a cluster."""
    subcluster_name: str
    thought_items: List[str]
    tags: List[str] = Field(default_factory=list)  # Optional behavioral tags, max 3

    @model_validator(mode="after")
    def validate_subcluster(self) -> "SubclusterInput":
        """Validate subcluster has items and valid tags."""
        if len(self.thought_items) == 0:
            raise ValueError(
                f"Subcluster '{self.subcluster_name}' has no thought_items. Subclusters must contain at least two thought items."
            )
        if len(self.tags) > 3:
            raise ValueError(
                f"Subcluster '{self.subcluster_name}' has {len(self.tags)} tags. Maximum is 3."
            )
        for tag in self.tags:
            if tag not in ALLOWED_TAGS:
                raise ValueError(
                    f"Invalid tag '{tag}'. Allowed: {', '.join(ALLOWED_TAGS)}"
                )
        return self


class ClusterInput(BaseModel):
    """Expected structure for each cluster from ChatGPT."""
    cluster_name: str
    thought_items: List[str] = Field(default_factory=list)  # Flat structure (used when no subclusters)
    subclusters: List[SubclusterInput] = Field(default_factory=list)  # Nested structure (optional groupings)
    tags: List[str] = Field(default_factory=list)  # Optional behavioral tags, max 3

    @model_validator(mode="after")
    def validate_cluster(self) -> "ClusterInput":
        """Validate cluster has content and valid tags."""
        has_items = len(self.thought_items) > 0
        has_subclusters = len(self.subclusters) > 0

        if not has_items and not has_subclusters:
            raise ValueError(
                f"Cluster '{self.cluster_name}' is empty. Must have thought_items or subclusters."
            )
        if len(self.tags) > 3:
            raise ValueError(
                f"Cluster '{self.cluster_name}' has {len(self.tags)} tags. Maximum is 3."
            )
        for tag in self.tags:
            if tag not in ALLOWED_TAGS:
                raise ValueError(
                    f"Invalid tag '{tag}'. Allowed: {', '.join(ALLOWED_TAGS)}"
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
                                },
                                "tags": {
                                    "type": "array",
                                    "items": {
                                        "type": "string",
                                        "enum": ["decide", "research", "test", "delegate", "automate", "learn", "align", "low value admin"]
                                    },
                                    "maxItems": 3,
                                    "description": "Optional behavioral tags (max 3). Only use when intent is clear."
                                }
                            },
                            "required": ["subcluster_name", "thought_items"]
                        }
                    },
                    "tags": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["decide", "research", "test", "delegate", "automate", "learn", "align", "low value admin"]
                        },
                        "maxItems": 3,
                        "description": "Optional behavioral tags (max 3). Only use when intent is clear."
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

    logger.debug("resource.read.requested", uri=uri_str, widget_version=WIDGET_VERSION)

    if uri_str == WIDGET_URI:
        logger.debug("resource.read.serving_widget",
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
    logger.debug("tools.list.called", widget_version=WIDGET_VERSION, widget_uri=WIDGET_URI)

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
    logger.debug("tools.list.returning", tool_count=len(all_tools))
    return all_tools

# ============================================================================
# OpenAI Widget Pattern: Override list_tools to include _meta for widget integration
# Reference: https://github.com/openai/openai-apps-sdk-examples/blob/main/pizzaz_server_python/main.py
# ============================================================================

# Helper to create INLINE embedded widget resource (pizzaz pattern)
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
    """Handle tool calls with authentication."""
    name = req.params.name
    arguments = req.params.arguments or {}
    meta = getattr(req.params, '_meta', None) or {}

    logger.debug("clarity.tool.call_received",
                tool_name=name,
                argument_keys=list(arguments.keys()),
                widget_version=WIDGET_VERSION)

    if name == "cluster_raw_thoughts":
        # ============================================================
        # AUTHENTICATION
        # ============================================================
        try:
            auth_context = await authenticate_request(name, meta)
            user_id = auth_context["user_id"]
            correlation_id = auth_context["correlation_id"]

            logger.info("clarity.tool.authenticated",
                        user_id=user_id,
                        correlation_id=correlation_id,
                        tool_name=name)

        except UnauthorizedError:
            logger.warning("clarity.tool.unauthorized", tool_name=name)
            return mcp_types.CallToolResult(
                content=[mcp_types.TextContent(
                    type="text",
                    text=json.dumps(build_unauthorized_error())
                )],
                isError=True,
            )
        except InsufficientScopeError as e:
            logger.warning("clarity.tool.forbidden", tool_name=name, required_scopes=e.required_scopes)
            return mcp_types.CallToolResult(
                content=[mcp_types.TextContent(
                    type="text",
                    text=json.dumps(build_forbidden_error(
                        required_scopes=e.required_scopes,
                        actual_scopes=e.actual_scopes
                    ))
                )],
                isError=True,
            )

        # ============================================================
        # VALIDATION + TOOL LOGIC
        # ============================================================
        validated_request = None

        try:
            # Pydantic validation (includes XOR validation via model_validator)
            validated_request = ClusterRequest.model_validate(arguments)

            # Count subclusters for logging
            subcluster_count = sum(len(c.subclusters) for c in validated_request.clusters)
            tag_count = sum(len(c.tags) for c in validated_request.clusters) + sum(
                len(sc.tags) for c in validated_request.clusters for sc in c.subclusters
            )

            logger.debug("clarity.tool.validation_success",
                        cluster_count=len(validated_request.clusters),
                        subcluster_count=subcluster_count,
                        tag_count=tag_count,
                        thoughts_exhausted=validated_request.thoughts_exhausted,
                        correctly_clustered=validated_request.correctly_clustered)

        except ValidationError as e:
            # ---------------------------------------------------------------
            # DESIGN NOTE: LLM Error Compensation
            # ---------------------------------------------------------------
            # This repair logic compensates for common LLM output errors
            # (e.g., returning `"[\"item\"]"` strings instead of arrays).
            #
            # This is a deliberate UX tradeoff that slightly blurs the
            # "tools only validate" boundary stated in the module docstring.
            #
            # FUTURE: When persistence is added, review this carefully to
            # ensure repaired/synthesized data is flagged or validated before
            # storage to avoid silently persisting malformed content.
            # ---------------------------------------------------------------
            logger.warning("clarity.tool.validation_failed_attempt_repair",
                          error=str(type(e).__name__),
                          details=str(e.errors()))

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
                logger.error("clarity.tool.repair_failed", reason="unrecognized_format")
                return mcp_types.CallToolResult(
                    content=[mcp_types.TextContent(
                        type="text",
                        text=json.dumps(build_invalid_params_error(
                            message="Invalid input format",
                            details="Expected 'clusters' array with cluster objects"
                        ))
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
                logger.debug("clarity.tool.repair_success",
                            cluster_count=len(validated_request.clusters))

            except ValidationError as repair_error:
                logger.error("clarity.tool.repair_failed",
                            reason="revalidation_failed",
                            details=str(repair_error.errors()))
                return mcp_types.CallToolResult(
                    content=[mcp_types.TextContent(
                        type="text",
                        text=json.dumps(build_invalid_params_error(
                            message="Invalid input format",
                            details="Could not parse input into valid cluster structure"
                        ))
                    )],
                    isError=True,
                )

        # From here on, validated_request is guaranteed valid
        clusters = [c.model_dump() for c in validated_request.clusters]
        result = cluster_raw_thoughts(clusters)

        # ============================================================
        # PERSISTENCE: Save cluster to backend (non-blocking)
        # ============================================================
        # Persistence failure must NOT fail the tool call.
        # User still sees their clusters even if backend is down.
        # ============================================================
        # Build logical cluster data (NO UI metadata like sum_thought_items)
        cluster_data_to_store = {
            "clusters": [
                {
                    "cluster_name": c.cluster_name,
                    "thought_items": c.thought_items,
                    "subclusters": [
                        {
                            "subcluster_name": sc.subcluster_name,
                            "thought_items": sc.thought_items,
                            "tags": sc.tags,
                        }
                        for sc in c.subclusters
                    ],
                    "tags": c.tags,
                }
                for c in validated_request.clusters
            ]
        }

        try:
            # Build headers with optional internal secret
            persist_headers = {"X-User-ID": user_id}
            if INTERNAL_API_SECRET:
                persist_headers["X-Internal-Secret"] = INTERNAL_API_SECRET

            client = _get_http_client()
            persist_response = await client.post(
                f"{BACKEND_URL}/api/clarity/clusters",
                headers=persist_headers,
                json={
                    "cluster_data": cluster_data_to_store,
                    "thoughts_exhausted": validated_request.thoughts_exhausted,
                    "correctly_clustered": validated_request.correctly_clustered,
                },
            )

            if persist_response.status_code == 201:
                cluster_id = persist_response.json().get("cluster_id")
                logger.info("clarity.tool.persisted",
                           cluster_id=cluster_id,
                           user_id=user_id)
            else:
                logger.warning("clarity.tool.persist_failed",
                              status=persist_response.status_code,
                              user_id=user_id,
                              response=persist_response.text[:200])

        except Exception as e:
            # Persistence failure should NOT fail the tool response
            logger.warning("clarity.tool.persist_error",
                          error=str(e),
                          user_id=user_id)

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
# OAuth Discovery Endpoints
# ============================================================================

async def wellknown_oauth_protected_resource(_request):
    """Starlette wrapper for discovery.oauth_protected_resource."""
    logger.debug("oauth.discovery.request")
    return JSONResponse(await oauth_protected_resource())


# ============================================================================
# App Startup
# ============================================================================

async def _cleanup_on_shutdown():
    """Clean up HTTP clients on shutdown."""
    logger.info("clarity.server.shutdown")
    await cleanup_jwks_cache()
    await _cleanup_http_client()


def create_app():
    """
    Create the ASGI application.

    FastMCP is the root app with:
    - CORS middleware for widget compatibility
    - Discovery routes for OAuth
    - Header fix middleware for ChatGPT
    - Shutdown handler for JWKS cache cleanup
    """
    fastmcp_app = mcp.streamable_http_app()

    # Add CORS
    # ---------------------------------------------------------------
    # SECURITY: Wide-open CORS for development only.
    # BEFORE PRODUCTION: Restrict allow_origins to specific domains
    # (e.g., ChatGPT plugin domains, your frontend domain).
    # See: https://owasp.org/www-community/attacks/CORS_OriginHeaderScrutiny
    # ---------------------------------------------------------------
    try:
        from starlette.middleware.cors import CORSMiddleware
        fastmcp_app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # TODO: Restrict before production
            allow_methods=["*"],
            allow_headers=["*"],
            allow_credentials=False,
        )
    except Exception:
        pass

    # Register shutdown handler for JWKS cache cleanup
    # Note: Using on_event for compatibility with FastMCP's Starlette wrapper
    # The deprecation warning is acceptable until FastMCP supports lifespan
    fastmcp_app.add_event_handler("shutdown", _cleanup_on_shutdown)

    # Discovery routes - only oauth-protected-resource (MCP is resource server, not auth server)
    # ChatGPT checks both root and /mcp suffixed versions
    discovery_routes = [
        Route("/oauth-protected-resource", wellknown_oauth_protected_resource, methods=["GET", "HEAD", "OPTIONS"]),
        Route("/oauth-protected-resource/mcp", wellknown_oauth_protected_resource, methods=["GET", "HEAD", "OPTIONS"]),
    ]
    discovery_app = Starlette(routes=discovery_routes)

    # Mount discovery routes
    fastmcp_app.mount("/.well-known", discovery_app)

    # Wrap with header-fix middleware
    return MCPContentTypeAndAcceptFixMiddleware(fastmcp_app)


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
