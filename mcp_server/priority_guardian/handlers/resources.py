"""
Resource handlers for Priority Guardian MCP.

Handles widget resource discovery and serving.
"""

from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

import structlog
from mcp import types as mcp_types

from mcp_server.priority_guardian.config import BACKEND_URL, MCP_SERVER_URL
from mcp_server.priority_guardian.mcp_auth import extract_or_generate_correlation_id
from mcp_server.priority_guardian.tools.widget_tools.constants import WIDGET_URI

logger = structlog.get_logger(__name__)


# ============================================================================
# URI Sanitization for Logging (inc_99)
# ============================================================================

# Maximum URI length to log — prevents pathological inputs from bloating logs
_MAX_URI_LOG_LENGTH = 512


def _sanitize_uri_for_logging(uri: str) -> str:
    """
    Sanitize URI for safe logging.

    inc_99: Defensive hygiene against pathological URIs from authenticated clients.
    - Strips query string and fragment (could contain tokens/PII)
    - Caps length to prevent log bloat
    - Preserves scheme, host, and path for diagnostic value

    Args:
        uri: Raw URI string from request

    Returns:
        Sanitized URI safe for production logs
    """
    try:
        parsed = urlparse(uri)
        # Reconstruct without query/fragment
        clean_uri = f"{parsed.scheme}://{parsed.netloc}{parsed.path}" if parsed.netloc else uri
    except Exception:
        # If parsing fails, just use the raw string (capped)
        clean_uri = uri

    # Cap length
    if len(clean_uri) > _MAX_URI_LOG_LENGTH:
        return clean_uri[:_MAX_URI_LOG_LENGTH] + "...[truncated]"
    return clean_uri


def _extract_origin(url: str) -> str:
    """
    Extract pure origin (scheme + host) from URL.

    OpenAI Apps SDK requires ui.domain to be a pure origin without path.
    Example: https://pg-mcp.priority-guard.com (not https://pg-mcp.priority-guard.com/mcp)
    """
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


# Widget configuration
# WIDGET_URI is imported from tools.widget_tools.constants — single source of truth.
# Do NOT redefine it here. If you need a different value, change constants.py.
WIDGET_VERSION = ""
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
                        "connectDomains": [BACKEND_DOMAIN],  # widget-error (Inc 83) + widget-diagnostic (Inc 89) endpoints
                        "resourceDomains": [],  # Self-contained HTML, no external assets
                    },
                },
                # Legacy ChatGPT extension — published apps need snake_case form
                "openai/widgetCSP": {
                    "connect_domains": [BACKEND_DOMAIN],
                    "resource_domains": [],
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
                        "connectDomains": [BACKEND_DOMAIN],  # widget-error + widget-diagnostic endpoints
                        "resourceDomains": [],
                    },
                },
                "openai/widgetCSP": {
                    "connect_domains": [BACKEND_DOMAIN],
                    "resource_domains": [],
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

    # inc_99: Extract correlation_id for log correlation with tools/call
    # This enables the binary verdict: correlate resources/read with tools/call in same session
    meta = getattr(req.params, '_meta', None) or getattr(req.params, 'meta', None)
    correlation_id = extract_or_generate_correlation_id(meta)

    # inc_99: Sanitize URI for logging (strip query/fragment, cap length)
    safe_uri = _sanitize_uri_for_logging(uri_str)

    # inc_98: Promoted to INFO for production observability.
    # inc_99: Added correlation_id + URI sanitization.
    # Enables binary verdict on widget render failures: if resources/read is absent
    # in session logs but tools/call is present → host-side issue (ChatGPT didn't fetch).
    logger.info(
        "resource.read.requested",
        uri=safe_uri,
        widget_version=WIDGET_VERSION,
        correlation_id=correlation_id,
    )

    if uri_str == WIDGET_URI:
        # inc_98: Promoted to INFO for production observability.
        # inc_99: Added correlation_id.
        # Logs html_length (not content) — no PII, GDPR-safe.
        logger.info(
            "resource.read.serving_widget",
            uri=safe_uri,
            html_length=len(WIDGET_HTML),
            widget_version=WIDGET_VERSION,
            correlation_id=correlation_id,
        )

        # Build _meta for the widget resource
        # Per OpenAI Apps SDK: resource _meta uses ui.domain, ui.csp, openai/widgetDescription
        # openai/toolInvocation/* belongs on tool descriptors, not resources
        resource_meta = {
            "ui": {
                "domain": WIDGET_DOMAIN,
                "csp": {
                    "connectDomains": [BACKEND_DOMAIN],  # widget-error + widget-diagnostic endpoints
                    "resourceDomains": [],
                },
            },
            "openai/widgetCSP": {
                "connect_domains": [BACKEND_DOMAIN],
                "resource_domains": [],
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

    # Unknown resource — inc_98: log at INFO for observability
    # inc_99: Added correlation_id + sanitized URI
    # If ChatGPT requests wrong URI, this log helps diagnose schema drift
    logger.info("resource.read.unknown_uri", uri=safe_uri, correlation_id=correlation_id)
    return mcp_types.ReadResourceResult(
        contents=[],
        _meta={"error": f"Unknown resource: {safe_uri}"},
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
