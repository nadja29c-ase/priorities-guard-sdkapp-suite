"""
Resource handlers for Unpack MCP.

Handles widget resource discovery and serving.
"""

from pathlib import Path
from typing import List

import structlog
from mcp import types as mcp_types

logger = structlog.get_logger(__name__)

# Widget configuration
WIDGET_URI = "ui://widget/unpack-clusters.html"
WIDGET_PATH = Path(__file__).parent.parent.joinpath("widgets/unpack-clusters.html")

# Lazy-loaded cache
_widget_html_cache: str | None = None


def get_widget_html() -> str:
    """Load widget HTML lazily (not at import time)."""
    global _widget_html_cache
    if _widget_html_cache is None:
        if not WIDGET_PATH.exists():
            raise FileNotFoundError(f"Widget not found: {WIDGET_PATH}")
        _widget_html_cache = WIDGET_PATH.read_text()
        logger.debug("widget.loaded", path=str(WIDGET_PATH), size=len(_widget_html_cache))
    return _widget_html_cache


async def list_resources() -> List[mcp_types.Resource]:
    """List available resources (widgets) for discovery."""
    return [
        mcp_types.Resource(
            name="unpack_clusters_widget",
            title="Unpack Clusters Widget",
            uri=WIDGET_URI,
            description="Widget for displaying clustered questions",
            mimeType="text/html+skybridge",
            _meta={
                "openai/outputTemplate": WIDGET_URI,
                "openai/widgetAccessible": True,
                "openai/resultCanProduceWidget": True,
            },
        )
    ]


async def list_resource_templates() -> List[mcp_types.ResourceTemplate]:
    """List resource templates for discovery."""
    return [
        mcp_types.ResourceTemplate(
            name="Unpack Clusters Widget",
            title="Unpack Clusters Widget",
            uriTemplate=WIDGET_URI,
            description="Widget for displaying clustered questions",
            mimeType="text/html+skybridge",
            _meta={
                "openai/outputTemplate": WIDGET_URI,
                "openai/widgetAccessible": True,
                "openai/resultCanProduceWidget": True,
            },
        )
    ]


async def handle_read_resource(req: mcp_types.ReadResourceRequest) -> mcp_types.ReadResourceResult:
    """Handle resource read requests."""
    uri_str = str(req.params.uri)

    if uri_str == WIDGET_URI:
        try:
            html = get_widget_html()

            # Build _meta for TextResourceContents (required for widget rendering)
            resource_meta = {
                "openai/outputTemplate": WIDGET_URI,
                "openai/toolInvocation/invoking": "Clustering your questions...",
                "openai/toolInvocation/invoked": "Here's your Unpack summary.",
                "openai/widgetAccessible": True,
                "openai/resultCanProduceWidget": True,
            }

            return mcp_types.ReadResourceResult(
                contents=[
                    mcp_types.TextResourceContents(
                        uri=WIDGET_URI,
                        mimeType="text/html+skybridge",
                        text=html,
                        _meta=resource_meta,
                    )
                ]
            )
        except FileNotFoundError as e:
            logger.error("widget.not_found", error=str(e))
            return mcp_types.ReadResourceResult(
                contents=[],
                _meta={"error": str(e)},
            )

    return mcp_types.ReadResourceResult(contents=[])
