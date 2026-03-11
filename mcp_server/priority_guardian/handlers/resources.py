"""
Resource handlers for Priority Guardian MCP.

Handles widget resource discovery and serving.
"""

from pathlib import Path
from typing import List
from urllib.parse import urlparse

import structlog
from mcp import types as mcp_types

from mcp_server.priority_guardian.config import BACKEND_URL, MCP_SERVER_URL

logger = structlog.get_logger(__name__)


def _extract_origin(url: str) -> str:
    """
    Extract pure origin (scheme + host) from URL.

    OpenAI Apps SDK requires ui.domain to be a pure origin without path.
    Example: https://pg-mcp.priority-guard.com (not https://pg-mcp.priority-guard.com/mcp)
    """
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


# Widget configuration
WIDGET_VERSION = ""
WIDGET_URI = "ui://widget/pg-dashboard-v8.html"
WIDGET_PATH = Path(__file__).parent.parent.joinpath("widgets/pg-dashboard.html")
WIDGET_DOMAIN = _extract_origin(MCP_SERVER_URL)
BACKEND_DOMAIN = _extract_origin(BACKEND_URL)

# Fallback HTML if widget file cannot be loaded
WIDGET_FALLBACK_HTML = """<!DOCTYPE html>
<html><head><title>Priority Guardian</title></head>
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
            name="pg_dashboard_widget",
            title="Priority Guardian Dashboard",
            uri=WIDGET_URI,
            description="Widget for viewing priorities and managing Google Calendar connection",
            mimeType="text/html;profile=mcp-app",
            _meta={
                "ui": {
                    "domain": WIDGET_DOMAIN,
                    "csp": {
                        "connectDomains": [],  # Widget uses callTool/postMessage, not HTTP
                        "resourceDomains": [],  # Self-contained HTML, no external assets
                    },
                },
                # Legacy ChatGPT extension — keep for openExternal support
                "openai/widgetCSP": {
                    "redirect_domains": [BACKEND_DOMAIN],
                },
                "openai/widgetDescription": "Shows user's priorities and Google Calendar connection status.",
            },
        )
    ]


async def list_resource_templates() -> List[mcp_types.ResourceTemplate]:
    """List resource templates (widget templates) for discovery."""
    return [
        mcp_types.ResourceTemplate(
            name="Priority Guardian Dashboard",
            title="Priority Guardian Dashboard",
            uriTemplate=WIDGET_URI,
            description="Widget for viewing priorities and managing Google Calendar connection",
            mimeType="text/html;profile=mcp-app",
            _meta={
                "ui": {
                    "domain": WIDGET_DOMAIN,
                    "csp": {
                        "connectDomains": [],
                        "resourceDomains": [],
                    },
                },
                "openai/widgetCSP": {
                    "redirect_domains": [BACKEND_DOMAIN],
                },
                "openai/widgetDescription": "Shows user's priorities and Google Calendar connection status.",
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

    # TEMP: INFO level to verify iOS loads v7 - revert to debug after confirmation
    logger.info("resource.read.requested", uri=uri_str, widget_version=WIDGET_VERSION)

    if uri_str == WIDGET_URI:
        logger.debug(
            "resource.read.serving_widget",
            uri=uri_str,
            html_length=len(WIDGET_HTML),
            widget_version=WIDGET_VERSION,
        )

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
            "openai/widgetCSP": {
                "redirect_domains": [BACKEND_DOMAIN],
            },
            "openai/widgetDescription": "Shows user's priorities and Google Calendar connection status.",
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
            title="Priority Guardian Dashboard",
        ),
    )
