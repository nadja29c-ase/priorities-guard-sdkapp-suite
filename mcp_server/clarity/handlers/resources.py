"""
Resource handlers for Clarity MCP.

Handles widget resource discovery and serving.
"""

from pathlib import Path
from typing import List
from urllib.parse import urlparse

import structlog
from mcp import types as mcp_types

from ..config import MCP_SERVER_URL

logger = structlog.get_logger(__name__)


def _extract_origin(url: str) -> str:
    """
    Extract pure origin (scheme + host) from URL.

    OpenAI Apps SDK requires ui.domain to be a pure origin without path.
    Example: https://clarity-mcp.priority-guard.com (not https://clarity-mcp.priority-guard.com/mcp)
    """
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


# Widget configuration
WIDGET_VERSION = "1.1.4"
WIDGET_URI = f"ui://widget/clarity-clusters.html?v={WIDGET_VERSION}"
WIDGET_PATH = Path(__file__).parent.parent.joinpath("widgets/clarity-clusters.html")
WIDGET_DOMAIN = _extract_origin(MCP_SERVER_URL)

# Diagnostic widget configuration (inc_91 - size isolation test)
DIAGNOSTIC_WIDGET_VERSION = "1"
DIAGNOSTIC_WIDGET_URI = f"ui://widget/diagnostic-tiny.html?v={DIAGNOSTIC_WIDGET_VERSION}"
DIAGNOSTIC_WIDGET_PATH = Path(__file__).parent.parent.joinpath("widgets/diagnostic-tiny.html")

# Fallback HTML if widget file cannot be loaded
WIDGET_FALLBACK_HTML = """<!DOCTYPE html>
<html><head><title>Clarity Widget</title></head>
<body style="font-family: system-ui; padding: 20px; text-align: center;">
<p style="color: var(--color-danger);">Widget failed to load. Please try again later.</p>
</body></html>"""

def _load_widget_html(path: Path, name: str) -> str:
    """Load widget HTML with error handling."""
    try:
        return path.read_text()
    except FileNotFoundError:
        logger.error("widget.load.file_not_found", path=str(path), widget=name)
        return WIDGET_FALLBACK_HTML
    except PermissionError:
        logger.error("widget.load.permission_denied", path=str(path), widget=name)
        return WIDGET_FALLBACK_HTML
    except Exception as e:
        logger.error("widget.load.unexpected_error", path=str(path), widget=name, error=str(e))
        return WIDGET_FALLBACK_HTML

WIDGET_HTML = _load_widget_html(WIDGET_PATH, "clarity-clusters")
DIAGNOSTIC_WIDGET_HTML = _load_widget_html(DIAGNOSTIC_WIDGET_PATH, "diagnostic-tiny")


async def list_resources() -> List[mcp_types.Resource]:
    """List available resources (widgets) for discovery."""
    resources = [
        mcp_types.Resource(
            name="mindsort_clusters_widget",
            title="MindSort AI Clusters Widget",
            uri=WIDGET_URI,
            description="Widget for rendering clustered thoughts",
            mimeType="text/html;profile=mcp-app",
            _meta={
                "ui": {
                    "domain": WIDGET_DOMAIN,
                    "csp": {
                        "connectDomains": [],
                        "resourceDomains": [],
                    },
                },
                "openai/widgetDescription": "Shows all user's thought clusters. User decides which to prioritize.",
            },
        ),
        # inc_91 diagnostic widget - must be in list_resources for ChatGPT to fetch it
        mcp_types.Resource(
            name="_diagnostic_tiny_widget",
            title="Diagnostic Widget (Internal)",
            uri=DIAGNOSTIC_WIDGET_URI,
            description="Internal diagnostic widget for render testing - <10KB",
            mimeType="text/html;profile=mcp-app",
            _meta={
                "ui": {
                    "domain": WIDGET_DOMAIN,
                    "csp": {
                        "connectDomains": [],
                        "resourceDomains": [],
                    },
                },
                "openai/widgetDescription": "Diagnostic widget for render testing.",
            },
        ),
    ]
    # MCP request-type logging: resources/list
    # This event confirms ChatGPT called ListResourcesRequest
    logger.info("mcp.request.resources_list", resource_count=len(resources))
    return resources


async def list_resource_templates() -> List[mcp_types.ResourceTemplate]:
    """List resource templates (widget templates) for discovery."""
    templates = [
        mcp_types.ResourceTemplate(
            name="MindSort AI Clusters Widget",
            title="MindSort AI Clusters Widget",
            uriTemplate=WIDGET_URI,
            description="Widget for rendering clustered thoughts",
            mimeType="text/html;profile=mcp-app",
            _meta={
                "ui": {
                    "domain": WIDGET_DOMAIN,
                    "csp": {
                        "connectDomains": [],
                        "resourceDomains": [],
                    },
                },
                "openai/widgetDescription": "Shows all user's thought clusters. User decides which to prioritize.",
            },
        ),
        # inc_91 diagnostic widget template
        mcp_types.ResourceTemplate(
            name="Diagnostic Widget (Internal)",
            title="Diagnostic Widget (Internal)",
            uriTemplate=DIAGNOSTIC_WIDGET_URI,
            description="Internal diagnostic widget for render testing - <10KB",
            mimeType="text/html;profile=mcp-app",
            _meta={
                "ui": {
                    "domain": WIDGET_DOMAIN,
                    "csp": {
                        "connectDomains": [],
                        "resourceDomains": [],
                    },
                },
                "openai/widgetDescription": "Diagnostic widget for render testing.",
            },
        ),
    ]
    # MCP request-type logging: resources/templates/list
    logger.info("mcp.request.resources_templates_list", template_count=len(templates))
    return templates


async def handle_read_resource(req: mcp_types.ReadResourceRequest) -> mcp_types.ReadResourceResult:
    """
    Handle resource read requests.

    Called by ChatGPT to load widget HTML, hydrate UI after tool call,
    or restore a widget (scroll, fullscreen, etc.).
    """
    uri_str = str(req.params.uri)

    # MCP request-type logging: resources/read
    # INFO level so it appears in production logs (DEBUG was invisible)
    # This event is the key diagnostic: if absent, ChatGPT never fetched the resource
    logger.info("mcp.request.resources_read", uri=uri_str)

    if uri_str == WIDGET_URI:
        logger.info("mcp.request.resources_read.serving",
                   uri=uri_str,
                   html_length=len(WIDGET_HTML),
                   widget_version=WIDGET_VERSION)

        # Build _meta for the widget resource
        # Per OpenAI Apps SDK: resource _meta uses ui.domain, ui.csp, openai/widgetDescription
        # openai/toolInvocation/* belongs on tool descriptors, not resources
        resource_meta = {
            "ui": {
                "domain": WIDGET_DOMAIN,
                "csp": {
                    "connectDomains": [],
                    "resourceDomains": [],
                },
            },
            "openai/widgetDescription": "Shows all user's thought clusters. User decides which to prioritize.",
        }

        contents = [
            mcp_types.TextResourceContents(
                uri=WIDGET_URI,
                mimeType="text/html;profile=mcp-app",
                text=WIDGET_HTML,
                _meta=resource_meta,
            )
        ]
        return mcp_types.ReadResourceResult(contents=contents)

    # Diagnostic widget (inc_91 - size isolation test)
    if uri_str == DIAGNOSTIC_WIDGET_URI:
        logger.info("mcp.request.resources_read.serving",
                   uri=uri_str,
                   html_length=len(DIAGNOSTIC_WIDGET_HTML),
                   widget_version=DIAGNOSTIC_WIDGET_VERSION,
                   diagnostic=True)

        diagnostic_meta = {
            "ui": {
                "domain": WIDGET_DOMAIN,
                "csp": {
                    "connectDomains": [],
                    "resourceDomains": [],
                },
            },
            "openai/widgetDescription": "Diagnostic widget for render testing.",
        }

        contents = [
            mcp_types.TextResourceContents(
                uri=DIAGNOSTIC_WIDGET_URI,
                mimeType="text/html;profile=mcp-app",
                text=DIAGNOSTIC_WIDGET_HTML,
                _meta=diagnostic_meta,
            )
        ]
        return mcp_types.ReadResourceResult(contents=contents)

    # Unknown resource
    return mcp_types.ReadResourceResult(
        contents=[],
        _meta={"error": f"Unknown resource: {uri_str}"},
    )


def embedded_widget_resource() -> mcp_types.EmbeddedResource:
    """Create inline embedded widget resource."""
    return mcp_types.EmbeddedResource(
        type="resource",
        resource=mcp_types.TextResourceContents(
            uri=WIDGET_URI,
            mimeType="text/html;profile=mcp-app",
            text=WIDGET_HTML,
            title="MindSort AI Clusters Widget",
        ),
    )
