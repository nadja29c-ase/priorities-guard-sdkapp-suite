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
WIDGET_PATH = Path(__file__).parent.parent.joinpath("widgets/clarity-clusters.html")

# Fallback HTML if widget file cannot be loaded
WIDGET_FALLBACK_HTML = """<!DOCTYPE html>
<html><head><title>Clarity Widget</title></head>
<body style="font-family: system-ui; padding: 20px; text-align: center;">
<p style="color: #dc2626;">Widget failed to load. Please try again later.</p>
</body></html>"""

def _load_widget_html() -> str:
    """Load widget HTML with error handling."""
    try:
        return WIDGET_PATH.read_text()
    except FileNotFoundError:
        logger.error("widget.load.file_not_found", path=str(WIDGET_PATH))
        return WIDGET_FALLBACK_HTML
    except PermissionError:
        logger.error("widget.load.permission_denied", path=str(WIDGET_PATH))
        return WIDGET_FALLBACK_HTML
    except Exception as e:
        logger.error("widget.load.unexpected_error", path=str(WIDGET_PATH), error=str(e))
        return WIDGET_FALLBACK_HTML

WIDGET_HTML = _load_widget_html()


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
                "openai/widgetCSP": {
                    "connect_domains": [],
                    "resource_domains": [],
                },
                "openai/widgetDescription": "Shows all user's thought clusters. User decides which to prioritize.",
                "openai/widgetDomain": "https://clarity.priority-guard.com",
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
                "openai/widgetCSP": {
                    "connect_domains": [],
                    "resource_domains": [],
                },
                "openai/widgetDescription": "Shows all user's thought clusters. User decides which to prioritize.",
                "openai/widgetDomain": "https://clarity.priority-guard.com",
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
            "openai/widgetCSP": {
                "connect_domains": [],
                "resource_domains": [],
            },
            "openai/widgetDescription": "Shows all user's thought clusters. User decides which to prioritize.",
            "openai/widgetDomain": "https://clarity.priority-guard.com",
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
