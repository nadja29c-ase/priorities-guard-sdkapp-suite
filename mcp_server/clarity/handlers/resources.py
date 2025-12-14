"""
Resource handlers for Clarity MCP.

Handles widget resource discovery and serving.
"""

from pathlib import Path
from typing import List

import structlog
from mcp import types as mcp_types

logger = structlog.get_logger(__name__)

# Widget configuration
WIDGET_VERSION = ""
WIDGET_URI = "ui://widget/clarity-clusters.html"
WIDGET_HTML = Path(__file__).parent.parent.joinpath("widgets/clarity-clusters.html").read_text()


async def list_resources() -> List[mcp_types.Resource]:
    """List available resources (widgets) for discovery."""
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


async def list_resource_templates() -> List[mcp_types.ResourceTemplate]:
    """List resource templates (widget templates) for discovery."""
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


async def handle_read_resource(req: mcp_types.ReadResourceRequest) -> mcp_types.ReadResourceResult:
    """
    Handle resource read requests.

    Called by ChatGPT to load widget HTML, hydrate UI after tool call,
    or restore a widget (scroll, fullscreen, etc.).
    """
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


def embedded_widget_resource() -> mcp_types.EmbeddedResource:
    """Create inline embedded widget resource (pizzaz pattern)."""
    return mcp_types.EmbeddedResource(
        type="resource",
        resource=mcp_types.TextResourceContents(
            uri=WIDGET_URI,
            mimeType="text/html+skybridge",
            text=WIDGET_HTML,
            title="Clarity Clusters Widget",
        ),
    )
